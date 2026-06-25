"""
Phase 4: Alert Priority Engine
Classifies alerts into CRITICAL / MEDIUM / LOW
Detects restock risks, procurement risks, overstock, demand spikes
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Alert Priority Constants
# ─────────────────────────────────────────────────────────────

PRIORITY_CRITICAL = 'CRITICAL'
PRIORITY_MEDIUM   = 'MEDIUM'
PRIORITY_LOW      = 'LOW'

PRIORITY_COLORS = {
    PRIORITY_CRITICAL: {'bg': 'FEE2E2', 'text': '991B1B', 'badge': 'bg-red-100 text-red-800'},
    PRIORITY_MEDIUM:   {'bg': 'FEF3C7', 'text': '92400E', 'badge': 'bg-amber-100 text-amber-800'},
    PRIORITY_LOW:      {'bg': 'DBEAFE', 'text': '1E40AF', 'badge': 'bg-blue-100 text-blue-800'},
}


def _alert(priority: str, category: str, title: str, message: str, materials: list = None) -> dict:
    return {
        'id': f"{category}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'priority': priority,
        'category': category,
        'title': title,
        'message': message,
        'materials': materials or [],
        'timestamp': datetime.now().strftime('%d %b %Y %H:%M'),
        'color': PRIORITY_COLORS[priority],
    }


# ─────────────────────────────────────────────────────────────
# Restock Alerts
# ─────────────────────────────────────────────────────────────

def detect_restock_alerts(inv_df: pd.DataFrame) -> list:
    alerts = []
    if inv_df is None or inv_df.empty:
        return alerts

    # Critical: Class A items that are below safety stock threshold
    if 'abc_class' in inv_df.columns and 'safety_stock' in inv_df.columns:
        critical_items = inv_df[
            (inv_df['abc_class'] == 'A') &
            (inv_df['quantity'] < inv_df['reorder_point'] * 1.1)
        ]
        if not critical_items.empty:
            mats = critical_items['material_code'].tolist()[:5] if 'material_code' in critical_items.columns else []
            alerts.append(_alert(
                PRIORITY_CRITICAL,
                'restock',
                'Critical Restock Required',
                f"{len(critical_items)} high-value Class A materials are at or below reorder point. "
                f"Immediate procurement action required.",
                mats
            ))

        # Medium: Class B items near reorder
        medium_items = inv_df[
            (inv_df['abc_class'] == 'B') &
            (inv_df['quantity'] < inv_df['reorder_point'] * 1.2)
        ]
        if not medium_items.empty:
            alerts.append(_alert(
                PRIORITY_MEDIUM,
                'restock',
                'Restock Advisory – Class B Materials',
                f"{len(medium_items)} medium-priority materials approaching reorder level. "
                f"Plan procurement within 2 weeks.",
                medium_items['material_code'].tolist()[:5] if 'material_code' in medium_items.columns else []
            ))

        # Low: overstock warning (holding excess)
        overstock = inv_df[
            inv_df['quantity'] > inv_df['eoq'] * 3
        ] if 'eoq' in inv_df.columns else pd.DataFrame()
        if not overstock.empty:
            alerts.append(_alert(
                PRIORITY_LOW,
                'overstock',
                'Overstock Warning',
                f"{len(overstock)} materials are holding more than 3× their Economic Order Quantity. "
                f"Review excess stock to reduce holding costs.",
                overstock['material_code'].tolist()[:5] if 'material_code' in overstock.columns else []
            ))

    return alerts


# ─────────────────────────────────────────────────────────────
# Procurement Risk Alerts
# ─────────────────────────────────────────────────────────────

def detect_procurement_risks(inv_df: pd.DataFrame, forecast_result: Optional[dict]) -> list:
    alerts = []
    if inv_df is None or inv_df.empty:
        return alerts

    # High-cost materials
    if 'unit_price' in inv_df.columns:
        price_threshold = inv_df['unit_price'].quantile(0.90)
        expensive = inv_df[inv_df['unit_price'] >= price_threshold]
        if not expensive.empty:
            alerts.append(_alert(
                PRIORITY_MEDIUM,
                'procurement',
                'High-Cost Material Exposure',
                f"{len(expensive)} materials in the top 10% price bracket account for significant "
                f"procurement spend. Monitor supplier pricing closely.",
                expensive['material_code'].tolist()[:5] if 'material_code' in expensive.columns else []
            ))

    # Forecast-based risk: rapidly rising demand
    if forecast_result:
        forecasts = forecast_result.get('forecasts', [])
        peak_items = [f for f in forecasts if f.get('status') == 'PEAK']
        if len(peak_items) >= 5:
            alerts.append(_alert(
                PRIORITY_CRITICAL,
                'procurement',
                'Procurement Surge Risk',
                f"{len(peak_items)} materials show rapidly rising demand forecasts. "
                f"Advance procurement planning required to avoid supply shortfall.",
                [p['material_code'] for p in peak_items[:5]]
            ))

        # Rising total cost forecast
        summary = forecast_result.get('summary', {})
        cost_increase_pct = summary.get('cost_increase_pct', 0)
        if cost_increase_pct > 10:
            alerts.append(_alert(
                PRIORITY_MEDIUM,
                'procurement',
                'Procurement Cost Rising',
                f"Forecasted procurement cost is expected to increase by {cost_increase_pct:.1f}% "
                f"next quarter. Budget adjustment may be required.",
            ))
        elif cost_increase_pct > 5:
            alerts.append(_alert(
                PRIORITY_LOW,
                'procurement',
                'Moderate Cost Increase Projected',
                f"Next quarter procurement cost is projected to rise by {cost_increase_pct:.1f}%. "
                f"Monitor supplier contracts.",
            ))

    return alerts


# ─────────────────────────────────────────────────────────────
# Demand Spike Alerts
# ─────────────────────────────────────────────────────────────

def detect_demand_alerts(forecast_result: Optional[dict]) -> list:
    alerts = []
    if not forecast_result:
        return alerts

    forecasts = forecast_result.get('forecasts', [])
    summary   = forecast_result.get('summary', {})

    peak_count = summary.get('peak_count', 0)
    if peak_count >= 10:
        alerts.append(_alert(
            PRIORITY_CRITICAL,
            'demand',
            'Mass Demand Surge Detected',
            f"{peak_count} materials show peak demand forecasts. This may strain procurement "
            f"capacity and supplier lead times. Review sourcing strategy immediately.",
        ))
    elif peak_count >= 5:
        alerts.append(_alert(
            PRIORITY_MEDIUM,
            'demand',
            'Elevated Demand Forecast',
            f"{peak_count} materials are forecast to see demand peaks in the next quarter. "
            f"Prepare procurement plans accordingly.",
        ))

    # Low demand / slow-moving risk
    low_items = [f for f in forecasts if f.get('status') == 'LOW']
    if len(low_items) >= 5:
        alerts.append(_alert(
            PRIORITY_LOW,
            'demand',
            'Slow-Moving Materials Identified',
            f"{len(low_items)} materials show declining demand. Consider reducing procurement "
            f"quantities or liquidating excess inventory.",
            [l['material_code'] for l in low_items[:5]]
        ))

    return alerts


# ─────────────────────────────────────────────────────────────
# Master Alert Runner
# ─────────────────────────────────────────────────────────────

def run_alert_engine(inv_result: dict, forecast_result: Optional[dict]) -> dict:
    """Run all alert detectors and return prioritized alert list."""
    inv_df = inv_result.get('data', pd.DataFrame()) if inv_result else pd.DataFrame()

    all_alerts = []
    all_alerts += detect_restock_alerts(inv_df)
    all_alerts += detect_procurement_risks(inv_df, forecast_result)
    all_alerts += detect_demand_alerts(forecast_result)

    # Sort: CRITICAL first, then MEDIUM, then LOW
    order = {PRIORITY_CRITICAL: 0, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 2}
    all_alerts.sort(key=lambda a: order.get(a['priority'], 9))

    critical_count = sum(1 for a in all_alerts if a['priority'] == PRIORITY_CRITICAL)
    medium_count   = sum(1 for a in all_alerts if a['priority'] == PRIORITY_MEDIUM)
    low_count      = sum(1 for a in all_alerts if a['priority'] == PRIORITY_LOW)

    return {
        'alerts': all_alerts,
        'total': len(all_alerts),
        'critical_count': critical_count,
        'medium_count': medium_count,
        'low_count': low_count,
        'has_critical': critical_count > 0,
        'generated_at': datetime.now().strftime('%d %b %Y %H:%M'),
    }
