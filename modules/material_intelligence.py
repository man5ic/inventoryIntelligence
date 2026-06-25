"""
Material Intelligence Module
Provides per-material deep analysis: health score, order recommendations,
procurement estimator, and timeline chart data.
Reuses existing inventory_intelligence and forecasting calculations.
"""
import numpy as np
import json
import base64
from io import BytesIO


# ─────────────────────────────────────────────────────────────
# Material Health Score
# ─────────────────────────────────────────────────────────────

def compute_health_score(inv_row: dict, forecast_row: dict) -> dict:
    """
    Compute a 0–100 health score for a material.
    Factors:
      - Demand stability (coefficient of variation of historical series)
      - Forecast trend (pct_change direction)
      - Procurement risk (lead_time relative)
      - Inventory safety (safety_stock adequacy)
    """
    score = 100
    breakdown = {}

    # 1. Demand Stability (0–30 pts)
    hist = forecast_row.get('historical_series', [])
    if hist and len(hist) > 1:
        arr = np.array(hist)
        cv = (arr.std() / arr.mean() * 100) if arr.mean() > 0 else 50
        if cv <= 10:
            ds = 30
        elif cv <= 20:
            ds = 25
        elif cv <= 35:
            ds = 18
        elif cv <= 50:
            ds = 10
        else:
            ds = 4
    else:
        ds = 15
    breakdown['demand_stability'] = ds

    # 2. Forecast Trend (0–25 pts)
    pct = forecast_row.get('pct_change', 0)
    status = forecast_row.get('forecast_status', 'NORMAL')
    if status == 'PEAK':
        ft = 22 if pct < 30 else 15   # High growth is good but risky if extreme
    elif status == 'NORMAL':
        ft = 25
    else:  # LOW
        ft = 10 if pct > -20 else 4
    breakdown['forecast_trend'] = ft

    # 3. Procurement Risk (0–25 pts)
    lead_time = float(inv_row.get('lead_time', 30)) if 'lead_time' in inv_row else 30
    if lead_time <= 14:
        pr = 25
    elif lead_time <= 30:
        pr = 20
    elif lead_time <= 60:
        pr = 13
    else:
        pr = 6
    breakdown['procurement_risk'] = pr

    # 4. Inventory Safety (0–20 pts)
    ss = float(inv_row.get('safety_stock', 0))
    rop = float(inv_row.get('reorder_point', 0))
    qty = float(inv_row.get('quantity', 0))
    monthly_demand = qty / 12 if qty > 0 else 1
    # Safety adequacy: safety_stock vs ~2 weeks demand
    two_week = monthly_demand / 2
    if two_week > 0:
        ratio = ss / two_week
        if ratio >= 1.5:
            inv_s = 20
        elif ratio >= 1.0:
            inv_s = 16
        elif ratio >= 0.5:
            inv_s = 10
        else:
            inv_s = 4
    else:
        inv_s = 10
    breakdown['inventory_safety'] = inv_s

    total = ds + ft + pr + inv_s

    if total >= 90:
        label = 'Healthy'
        color = '#16A34A'
        icon = 'fa-circle-check'
    elif total >= 70:
        label = 'Monitor'
        color = '#D97706'
        icon = 'fa-triangle-exclamation'
    else:
        label = 'Critical'
        color = '#DC2626'
        icon = 'fa-circle-xmark'

    return {
        'score': total,
        'label': label,
        'color': color,
        'icon': icon,
        'breakdown': breakdown,
    }


# ─────────────────────────────────────────────────────────────
# Order Recommendation Engine
# ─────────────────────────────────────────────────────────────

def compute_order_recommendations(inv_row: dict, forecast_row: dict) -> dict:
    """
    Compute practical weekly and monthly order quantities.
    Uses safety stock, reorder point, forecast trend.
    """
    qty = float(inv_row.get('quantity', 0))
    eoq = float(inv_row.get('eoq', 0))
    safety_stock = float(inv_row.get('safety_stock', 0))
    reorder_point = float(inv_row.get('reorder_point', 0))

    next_month_qty = float(forecast_row.get('next_month_qty', qty / 12))
    next_quarter_qty = float(forecast_row.get('next_quarter_qty', qty / 4))
    pct_change = float(forecast_row.get('pct_change', 0))
    status = forecast_row.get('forecast_status', 'NORMAL')

    # Trend adjustment factor
    if status == 'PEAK':
        trend_adj = 1 + min(pct_change / 100, 0.30)
    elif status == 'LOW':
        trend_adj = max(1 + pct_change / 100, 0.75)
    else:
        trend_adj = 1.0

    # Weekly recommendation: based on forecast monthly demand + safety buffer
    weekly_base = next_month_qty / 4.33
    weekly_buffer = safety_stock / 4  # spread safety stock across 4 weeks
    weekly_recommended = round((weekly_base + weekly_buffer) * trend_adj, 0)

    # Monthly recommendation: forecast demand + safety restock
    monthly_recommended = round(next_month_qty * trend_adj + (safety_stock * 0.1), 0)

    # EOQ-based order frequency
    eoq_orders_per_year = (qty / eoq) if eoq > 0 else 12
    eoq_order_interval_days = round(365 / max(eoq_orders_per_year, 1), 0)

    # Urgency flag
    if reorder_point > 0 and qty <= reorder_point * 1.1:
        urgency = 'Reorder Now'
        urgency_color = '#DC2626'
    elif reorder_point > 0 and qty <= reorder_point * 1.5:
        urgency = 'Order Soon'
        urgency_color = '#D97706'
    else:
        urgency = 'Stock Adequate'
        urgency_color = '#16A34A'

    return {
        'weekly_qty': int(weekly_recommended),
        'monthly_qty': int(monthly_recommended),
        'eoq_qty': int(eoq),
        'eoq_order_interval_days': int(eoq_order_interval_days),
        'trend_adjustment': round((trend_adj - 1) * 100, 1),
        'urgency': urgency,
        'urgency_color': urgency_color,
        'basis': f"Based on {status} demand trend ({'+' if pct_change >= 0 else ''}{pct_change:.1f}%)",
    }


# ─────────────────────────────────────────────────────────────
# Future Procurement Estimator
# ─────────────────────────────────────────────────────────────

def compute_procurement_estimate(forecast_row: dict) -> dict:
    """Estimate next-quarter and next-year procurement cost."""
    unit_price = float(forecast_row.get('unit_price', 0))
    next_quarter_cost = float(forecast_row.get('next_quarter_cost', 0))
    next_year_cost = float(forecast_row.get('next_year_cost', 0))
    next_month_cost = float(forecast_row.get('next_month_cost', 0))

    def to_lakhs(val):
        return round(val / 100000, 2)

    return {
        'next_month_cost': round(next_month_cost, 0),
        'next_quarter_cost': round(next_quarter_cost, 0),
        'next_year_cost': round(next_year_cost, 0),
        'next_month_lakhs': to_lakhs(next_month_cost),
        'next_quarter_lakhs': to_lakhs(next_quarter_cost),
        'next_year_lakhs': to_lakhs(next_year_cost),
        'unit_price': unit_price,
    }


# ─────────────────────────────────────────────────────────────
# Timeline Chart (Plotly JSON)
# ─────────────────────────────────────────────────────────────

def build_timeline_chart_data(forecast_row: dict) -> dict:
    """
    Return Plotly-compatible JSON chart data for historical + forecast trend.
    """
    historical = forecast_row.get('historical_series', [])
    forecast_12 = forecast_row.get('forecast_12', [])
    material_code = forecast_row.get('material_code', '')
    description = forecast_row.get('description', '')

    n_hist = len(historical)
    import pandas as pd
    hist_months = pd.date_range(end='2024-12-31', periods=n_hist, freq='ME')
    hist_labels = [m.strftime('%b %Y') for m in hist_months]

    future_months = pd.date_range(start='2025-01-31', periods=12, freq='ME')
    future_labels = [m.strftime('%b %Y') for m in future_months]

    # Transition point: last historical value → first forecast
    transition_x = [hist_labels[-1]] + [future_labels[0]] if historical and forecast_12 else []
    transition_y = [historical[-1], forecast_12[0]] if historical and forecast_12 else []

    chart_data = {
        'data': [
            {
                'x': hist_labels,
                'y': [round(v, 1) for v in historical],
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'Historical Demand',
                'line': {'color': '#2563EB', 'width': 2},
                'marker': {'size': 4, 'color': '#2563EB'},
                'hovertemplate': '<b>%{x}</b><br>Demand: %{y:,.0f} units<extra></extra>',
            },
            {
                'x': transition_x,
                'y': [round(v, 1) for v in transition_y],
                'type': 'scatter',
                'mode': 'lines',
                'name': '',
                'line': {'color': '#16A34A', 'width': 2, 'dash': 'dot'},
                'showlegend': False,
                'hoverinfo': 'skip',
            },
            {
                'x': future_labels,
                'y': [round(v, 1) for v in forecast_12],
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'Forecast Demand',
                'line': {'color': '#16A34A', 'width': 2, 'dash': 'dash'},
                'marker': {'size': 5, 'color': '#16A34A', 'symbol': 'diamond'},
                'fill': 'tozeroy',
                'fillcolor': 'rgba(22,163,74,0.07)',
                'hovertemplate': '<b>%{x}</b><br>Forecast: %{y:,.0f} units<extra></extra>',
            },
        ],
        'layout': {
            'title': {
                'text': f'Demand Timeline — {material_code}',
                'font': {'size': 15, 'color': '#1E3A5F'},
                'x': 0.02,
            },
            'xaxis': {
                'title': '',
                'tickfont': {'size': 10},
                'showgrid': False,
                'tickangle': -30,
            },
            'yaxis': {
                'title': 'Units',
                'tickfont': {'size': 10},
                'gridcolor': '#F1F5F9',
            },
            'legend': {'orientation': 'h', 'y': -0.25, 'x': 0},
            'margin': {'l': 50, 'r': 20, 't': 50, 'b': 60},
            'plot_bgcolor': 'white',
            'paper_bgcolor': 'white',
            'hovermode': 'x unified',
            'shapes': [
                {
                    'type': 'line',
                    'x0': hist_labels[-1] if hist_labels else 0,
                    'x1': hist_labels[-1] if hist_labels else 0,
                    'y0': 0,
                    'y1': 1,
                    'yref': 'paper',
                    'line': {'color': '#94A3B8', 'width': 1, 'dash': 'dot'},
                }
            ] if hist_labels else [],
            'annotations': [
                {
                    'x': hist_labels[-1] if hist_labels else '',
                    'y': 1,
                    'yref': 'paper',
                    'text': 'Forecast →',
                    'showarrow': False,
                    'font': {'size': 10, 'color': '#64748B'},
                    'xanchor': 'left',
                    'xshift': 5,
                }
            ] if hist_labels else [],
        },
        'config': {
            'responsive': True,
            'displayModeBar': True,
            'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
            'displaylogo': False,
        }
    }
    return chart_data


# ─────────────────────────────────────────────────────────────
# Master Material Intelligence Function
# ─────────────────────────────────────────────────────────────

def get_material_intelligence(material_code: str, inv_result: dict, forecast_result: dict) -> dict | None:
    """
    Pull together all intelligence for a single material.
    Returns a comprehensive dict or None if material not found.
    """
    inv_df = inv_result.get('data')
    if inv_df is None or inv_df.empty:
        return None

    # Find inventory row
    inv_rows = inv_df[inv_df['material_code'] == material_code]
    if inv_rows.empty:
        return None
    inv_row = inv_rows.iloc[0].to_dict()

    # Find forecast row
    forecasts = forecast_result.get('forecasts', [])
    forecast_row = next((f for f in forecasts if f['material_code'] == material_code), None)
    if not forecast_row:
        return None

    # Compute all intelligence layers
    health = compute_health_score(inv_row, forecast_row)
    orders = compute_order_recommendations(inv_row, forecast_row)
    procurement = compute_procurement_estimate(forecast_row)
    chart_data = build_timeline_chart_data(forecast_row)

    # Inventory status label
    abc = inv_row.get('abc_class', 'C')
    status_map = {'A': 'High Value', 'B': 'Medium Value', 'C': 'Standard'}

    # Demand stability label from CV
    hist = forecast_row.get('historical_series', [])
    if hist:
        arr = np.array(hist)
        cv = (arr.std() / arr.mean() * 100) if arr.mean() > 0 else 50
        if cv <= 15:
            demand_stability = 'Stable'
        elif cv <= 30:
            demand_stability = 'Moderate'
        else:
            demand_stability = 'Volatile'
    else:
        demand_stability = 'Unknown'

    return {
        'material_code': material_code,
        'description': inv_row.get('description', ''),
        'category': inv_row.get('category', ''),
        'total_demand': round(float(inv_row.get('quantity', 0)), 0),
        'forecast_demand': forecast_row.get('next_year_qty', 0),
        'safety_stock': round(float(inv_row.get('safety_stock', 0)), 1),
        'reorder_point': round(float(inv_row.get('reorder_point', 0)), 1),
        'eoq': round(float(inv_row.get('eoq', 0)), 1),
        'abc_class': abc,
        'annual_value': round(float(inv_row.get('annual_value', 0)), 0),
        'unit_price': float(inv_row.get('unit_price', 0)),
        'lead_time': float(inv_row.get('lead_time', 30)),
        'avg_monthly_demand': round(float(inv_row.get('avg_monthly_demand', 0)), 1),
        'inventory_status': status_map.get(abc, 'Standard'),
        'recommendation': inv_row.get('recommendation', ''),
        'forecast_status': forecast_row.get('forecast_status', 'NORMAL'),
        'pct_change': forecast_row.get('pct_change', 0),
        'best_model': forecast_row.get('best_model', 'linear'),
        'insight': forecast_row.get('insight', ''),
        'demand_stability': demand_stability,
        'health': health,
        'orders': orders,
        'procurement': procurement,
        'chart_data': chart_data,
        'monthly_forecast': forecast_row.get('monthly_forecast', []),
    }


def get_all_materials(inv_result: dict) -> list:
    """Return list of (material_code, description) tuples for dropdown."""
    inv_df = inv_result.get('data')
    if inv_df is None or inv_df.empty:
        return []
    materials = []
    for _, row in inv_df.iterrows():
        code = str(row.get('material_code', ''))
        desc = str(row.get('description', ''))
        if code:
            materials.append({'code': code, 'description': desc, 'label': f"{code} – {desc}"})
    return sorted(materials, key=lambda x: x['code'])
