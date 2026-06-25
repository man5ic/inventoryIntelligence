"""
Low-Movement & Dead Stock Detection Engine
Detects: slow-moving inventory, dead stock, overstock risk
Designed to extend existing Phase 2-8 analytics without duplication.
"""
import pandas as pd
import numpy as np
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Status Constants
# ─────────────────────────────────────────────────────────────

STATUS_DEAD       = 'DEAD STOCK'
STATUS_LOW        = 'LOW MOVEMENT'
STATUS_OVERSTOCK  = 'OVERSTOCK RISK'
STATUS_NORMAL     = 'NORMAL'

RISK_CRITICAL = 'CRITICAL'
RISK_HIGH     = 'HIGH'
RISK_MEDIUM   = 'MEDIUM'
RISK_LOW      = 'LOW'

# Color mapping (used in template badges)
STATUS_COLORS = {
    STATUS_DEAD:      'red',
    STATUS_LOW:       'yellow',
    STATUS_OVERSTOCK: 'blue',
    STATUS_NORMAL:    'green',
}

# ─────────────────────────────────────────────────────────────
# Thresholds  (tunable)
# ─────────────────────────────────────────────────────────────

# Monthly demand below which a material is "very low movement"
LOW_MOVEMENT_MONTHLY_THRESHOLD  = 5.0   # units / month

# Monthly demand below which a material is considered "dead"
DEAD_STOCK_MONTHLY_THRESHOLD    = 1.0   # units / month

# If forecast qty for next quarter ÷ avg monthly demand > this → overstock
OVERSTOCK_RATIO_THRESHOLD       = 6.0   # months of stock

# Percentage decline in quarterly trend to flag LOW movement
DECLINING_TREND_PCT_THRESHOLD   = -20.0  # percent


# ─────────────────────────────────────────────────────────────
# Core Classification
# ─────────────────────────────────────────────────────────────

def _classify_material(
    avg_monthly_demand: float,
    quarterly_trend_pct: float,
    qty_on_hand: float,
    forecast_next_quarter: float,
) -> tuple:
    """
    Returns (status, risk_level).
    Priority: dead stock > low movement > overstock risk > normal.
    """
    # Dead Stock: near-zero monthly demand
    if avg_monthly_demand <= DEAD_STOCK_MONTHLY_THRESHOLD:
        risk = RISK_CRITICAL if qty_on_hand > 0 else RISK_HIGH
        return STATUS_DEAD, risk

    # Low Movement: very low recent demand OR severe declining trend
    if avg_monthly_demand <= LOW_MOVEMENT_MONTHLY_THRESHOLD:
        risk = RISK_HIGH if quarterly_trend_pct < DECLINING_TREND_PCT_THRESHOLD else RISK_MEDIUM
        return STATUS_LOW, risk

    # Low movement by trend alone (demand was OK but dropping fast)
    if quarterly_trend_pct < DECLINING_TREND_PCT_THRESHOLD and avg_monthly_demand <= 20:
        return STATUS_LOW, RISK_MEDIUM

    # Overstock Risk: projected stock significantly exceeds expected demand
    if avg_monthly_demand > 0:
        months_cover = forecast_next_quarter / avg_monthly_demand if avg_monthly_demand > 0 else 0
        if months_cover >= OVERSTOCK_RATIO_THRESHOLD:
            return STATUS_OVERSTOCK, RISK_MEDIUM

    return STATUS_NORMAL, RISK_LOW


def _generate_recommendation(status: str, risk: str, avg_monthly_demand: float, material_code: str) -> str:
    """Generate a concise, executive-friendly recommendation."""
    if status == STATUS_DEAD:
        return "Potential dead inventory identified — review for write-off or disposal"
    if status == STATUS_LOW:
        if risk == RISK_HIGH:
            return "Reduce procurement immediately — declining demand trend detected"
        return "Reduce procurement next cycle — low demand movement"
    if status == STATUS_OVERSTOCK:
        return "Overstock risk detected — review warehouse holding and pause orders"
    return "Normal movement — continue standard replenishment"


# ─────────────────────────────────────────────────────────────
# Main Engine
# ─────────────────────────────────────────────────────────────

def run_dead_stock_detection(
    inv_result: dict,
    forecast_result: Optional[dict] = None,
) -> dict:
    """
    Main entry point. Reuses inv_result (Phase 2) and forecast_result (Phase 3).
    Returns structured detection results ready for dashboard consumption.
    """
    inv_df    = inv_result.get('data', pd.DataFrame()) if inv_result else pd.DataFrame()
    forecasts = forecast_result.get('forecasts', []) if forecast_result else []

    if inv_df.empty:
        return _empty_result()

    # Build a forecast lookup keyed by material_code
    forecast_map = {f['material_code']: f for f in forecasts}

    flagged = []

    for _, row in inv_df.iterrows():
        material_code = str(row.get('material_code', 'Unknown'))
        description   = str(row.get('description', ''))
        qty_on_hand   = float(row.get('quantity', 0))
        unit_price    = float(row.get('unit_price', 0))

        # avg_monthly_demand from inventory intelligence
        avg_monthly_demand = float(row.get('avg_monthly_demand', qty_on_hand / 12))

        # quarterly trend from forecast output (pct_change over 3-month horizon)
        fc = forecast_map.get(material_code, {})
        quarterly_trend_pct  = float(fc.get('pct_change', 0))
        forecast_next_quarter = float(fc.get('next_quarter_qty', avg_monthly_demand * 3))

        status, risk = _classify_material(
            avg_monthly_demand,
            quarterly_trend_pct,
            qty_on_hand,
            forecast_next_quarter,
        )

        if status == STATUS_NORMAL:
            continue   # only surface flagged materials

        recommendation = _generate_recommendation(status, risk, avg_monthly_demand, material_code)

        flagged.append({
            'material_code':       material_code,
            'description':         description,
            'status':              status,
            'risk_level':          risk,
            'avg_monthly_demand':  round(avg_monthly_demand, 1),
            'quarterly_trend_pct': round(quarterly_trend_pct, 1),
            'qty_on_hand':         round(qty_on_hand, 0),
            'unit_price':          round(unit_price, 2),
            'forecast_q_qty':      round(forecast_next_quarter, 1),
            'recommendation':      recommendation,
            'color':               STATUS_COLORS[status],
        })

    # Sort: dead → low → overstock, then by avg_monthly_demand asc
    priority_order = {STATUS_DEAD: 0, STATUS_LOW: 1, STATUS_OVERSTOCK: 2}
    flagged.sort(key=lambda x: (priority_order.get(x['status'], 3), x['avg_monthly_demand']))

    # Counts
    dead_items      = [m for m in flagged if m['status'] == STATUS_DEAD]
    low_items       = [m for m in flagged if m['status'] == STATUS_LOW]
    overstock_items = [m for m in flagged if m['status'] == STATUS_OVERSTOCK]

    # Smart insights for Smart Insight Engine
    smart_insights = _generate_smart_insights(dead_items, low_items, overstock_items, inv_df)

    # Summary stats
    total_flagged_value = sum(
        m['qty_on_hand'] * m['unit_price'] for m in flagged
    )

    return {
        'flagged':         flagged,
        'dead_items':      dead_items,
        'low_items':       low_items,
        'overstock_items': overstock_items,
        'dead_count':      len(dead_items),
        'low_count':       len(low_items),
        'overstock_count': len(overstock_items),
        'total_flagged':   len(flagged),
        'total_flagged_value': round(total_flagged_value, 2),
        'smart_insights':  smart_insights,
        'has_data':        len(flagged) > 0,
    }


# ─────────────────────────────────────────────────────────────
# Smart Insights Generator
# ─────────────────────────────────────────────────────────────

def _generate_smart_insights(
    dead_items: list,
    low_items: list,
    overstock_items: list,
    inv_df: pd.DataFrame,
) -> list:
    """
    Returns executive-ready insight strings for the Smart Insight panel.
    Integrated into existing procurement_insights list in exec_summary.
    """
    insights = []

    if dead_items:
        insights.append(
            f"{len(dead_items)} material{'s' if len(dead_items)>1 else ''} identified as potential dead stock — "
            f"review for disposal or write-off to free warehouse capacity"
        )

    if low_items:
        insights.append(
            f"{len(low_items)} material{'s' if len(low_items)>1 else ''} flagged as low movement inventory — "
            f"reduce procurement quantities in the next procurement cycle"
        )

    if overstock_items:
        insights.append(
            f"{len(overstock_items)} material{'s' if len(overstock_items)>1 else ''} at overstock risk — "
            f"projected stock exceeds demand; pause or reduce incoming orders"
        )

    # Plant-level dead stock signal (if plant column present)
    if dead_items and 'plant' in inv_df.columns:
        try:
            dead_codes = [m['material_code'] for m in dead_items]
            dead_rows  = inv_df[inv_df['material_code'].isin(dead_codes)]
            if not dead_rows.empty:
                top_plant = dead_rows['plant'].value_counts().idxmax()
                insights.append(
                    f"Dead stock risk concentrated in Plant {top_plant} — prioritize site-level review"
                )
        except Exception:
            pass

    # Overstock accumulation trend
    total_flagged = len(dead_items) + len(low_items) + len(overstock_items)
    if total_flagged > 5:
        insights.append(
            f"Overstock accumulation risk increasing — {total_flagged} slow/dead materials require inventory policy review"
        )

    return insights


# ─────────────────────────────────────────────────────────────
# Empty result guard
# ─────────────────────────────────────────────────────────────

def _empty_result() -> dict:
    return {
        'flagged':            [],
        'dead_items':         [],
        'low_items':          [],
        'overstock_items':    [],
        'dead_count':         0,
        'low_count':          0,
        'overstock_count':    0,
        'total_flagged':      0,
        'total_flagged_value': 0,
        'smart_insights':     [],
        'has_data':           False,
    }
