"""
Phase 4: Executive Summary Generator
Generates concise, non-technical, decision-oriented summaries
for business leaders.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional


def _pct_change(a: float, b: float) -> float:
    """Percent change from b to a."""
    if b == 0:
        return 0.0
    return round(((a - b) / b) * 100, 1)


def generate_executive_summary(inv_result: dict, forecast_result: Optional[dict], alert_result: Optional[dict]) -> dict:
    """
    Produce a clean, executive-friendly summary.
    Returns structured summary with headline, bullets, and risk flags.
    """
    if not inv_result:
        return {'headline': 'No data available.', 'bullets': [], 'risk_flags': [], 'kpis': {}}

    inv_df   = inv_result.get('data', pd.DataFrame())
    inv_sum  = inv_result.get('summary', {})
    fc_sum   = forecast_result.get('summary', {}) if forecast_result else {}
    forecasts = forecast_result.get('forecasts', []) if forecast_result else []

    bullets     = []
    risk_flags  = []
    kpis        = {}

    # ── Inventory snapshot ──
    total_items = inv_sum.get('total_items', 0)
    total_value = inv_sum.get('total_value', 0)
    abc_counts  = inv_sum.get('abc_counts', {})
    a_count     = abc_counts.get('A', 0)
    b_count     = abc_counts.get('B', 0)
    c_count     = abc_counts.get('C', 0)

    kpis['total_items']  = total_items
    kpis['total_value']  = total_value
    kpis['a_items']      = a_count

    bullets.append(f"Inventory portfolio covers {total_items} materials valued at ₹{total_value:,.0f} annually.")
    if a_count:
        bullets.append(f"{a_count} high-priority (Class A) materials drive approximately 70% of total inventory value — these require closest management attention.")
    if b_count:
        bullets.append(f"{b_count} Class B materials contribute the next 20% of value; periodic reviews recommended.")
    if c_count:
        bullets.append(f"{c_count} low-value Class C materials can be managed with simplified replenishment policies.")

    # ── Forecast insights ──
    if fc_sum:
        peak_count  = fc_sum.get('peak_count', 0)
        low_count_f = fc_sum.get('low_count', 0)
        total_q_cost = fc_sum.get('total_next_quarter_cost', 0)
        cost_inc    = fc_sum.get('cost_increase_pct', 0)

        kpis['peak_materials']   = peak_count
        kpis['next_qtr_cost']    = total_q_cost
        kpis['cost_change_pct']  = cost_inc

        if peak_count:
            bullets.append(f"Demand is rising for {peak_count} materials — procurement teams should prepare for increased order volumes next quarter.")
        if low_count_f:
            bullets.append(f"{low_count_f} materials show declining demand — review for overstock risk and consider reducing future orders.")
        if total_q_cost:
            bullets.append(f"Estimated procurement spend for next quarter is ₹{total_q_cost:,.0f}.")
        if cost_inc > 5:
            risk_flags.append(f"Procurement costs are projected to rise by {cost_inc:.1f}% — budget planning should account for this increase.")
        elif cost_inc < -5:
            bullets.append(f"Procurement costs are expected to decrease by {abs(cost_inc):.1f}% next quarter — a favorable outlook for cost savings.")

    # ── Alert-based flags ──
    if alert_result:
        crit = alert_result.get('critical_count', 0)
        med  = alert_result.get('medium_count', 0)
        total_alerts = alert_result.get('total', 0)

        kpis['active_alerts']   = total_alerts
        kpis['critical_alerts'] = crit

        if crit:
            risk_flags.append(f"{crit} critical alert{'s' if crit > 1 else ''} require immediate management attention — review the Alerts section for details.")
        if med:
            risk_flags.append(f"{med} medium-priority issue{'s' if med > 1 else ''} identified — plan resolution within the next 2 weeks.")

    # ── Headline ──
    if risk_flags:
        headline = f"Action Required: {len(risk_flags)} risk area{'s' if len(risk_flags) > 1 else ''} identified requiring management decision."
    else:
        headline = "Inventory position is stable. No critical risks detected at this time."

    # ── Recommendations ──
    recommendations = _build_recommendations(inv_df, fc_sum, alert_result)

    return {
        'headline':        headline,
        'bullets':         bullets,
        'risk_flags':      risk_flags,
        'recommendations': recommendations,
        'kpis':            kpis,
        'generated_at':    datetime.now().strftime('%d %b %Y %H:%M'),
        'report_period':   _report_period(),
    }


def _build_recommendations(inv_df: pd.DataFrame, fc_sum: dict, alert_result: Optional[dict]) -> list:
    recs = []

    if not inv_df.empty and 'abc_class' in inv_df.columns:
        a_items = inv_df[inv_df['abc_class'] == 'A']
        if not a_items.empty:
            recs.append("Establish weekly stock reviews for all Class A materials to prevent supply disruption.")

    peak_count = fc_sum.get('peak_count', 0)
    if peak_count >= 3:
        recs.append("Advance purchase orders for peak-demand materials by 2–4 weeks to buffer against lead time uncertainty.")

    cost_inc = fc_sum.get('cost_increase_pct', 0)
    if cost_inc > 8:
        recs.append("Engage key suppliers now to negotiate pricing before anticipated cost increases take effect.")

    if alert_result and alert_result.get('critical_count', 0) > 0:
        recs.append("Trigger emergency procurement process for materials flagged as CRITICAL in the Alerts section.")

    if not recs:
        recs.append("Continue current inventory management practices and schedule next review in 30 days.")

    return recs


def _report_period() -> str:
    now = datetime.now()
    return f"{now.strftime('%B %Y')} Report"
