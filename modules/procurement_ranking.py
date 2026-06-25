"""
Phase 6: Procurement Priority Ranking + Top Risk Materials Panel
Extends existing intelligence pipeline without duplicating computations.
"""
import pandas as pd
import numpy as np
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Priority Score Engine
# ─────────────────────────────────────────────────────────────

def _abc_weight(abc_class: str) -> float:
    return {'A': 1.0, 'B': 0.6, 'C': 0.3}.get(str(abc_class).upper(), 0.3)


def _normalize_series(s: pd.Series) -> pd.Series:
    mn, mx = s.min(), s.max()
    if mx == mn:
        return pd.Series([0.5] * len(s), index=s.index)
    return (s - mn) / (mx - mn)


def compute_priority_scores(inv_df: pd.DataFrame, forecasts: list) -> pd.DataFrame:
    """
    Compute a composite procurement priority score (0–100) for each material.
    Inputs reuse already-computed inv_df columns and forecast list.
    """
    df = inv_df.copy()

    # ── Build forecast lookup keyed by material_code ──
    fc_map = {f['material_code']: f for f in (forecasts or [])}

    # ── Demand forecast factor (0–1): higher next-quarter demand → higher urgency ──
    def _forecast_demand(code):
        fc = fc_map.get(code, {})
        return fc.get('next_quarter_demand', 0) or 0

    df['_fc_demand'] = df['material_code'].apply(_forecast_demand)
    df['_fc_demand_norm'] = _normalize_series(df['_fc_demand'])

    # ── Reorder urgency: how close is current quantity to reorder_point ──
    # reorder_point column already exists; quantity = annual qty (proxy for stock level)
    if 'reorder_point' in df.columns and 'quantity' in df.columns:
        df['_rp_ratio'] = df['reorder_point'] / df['quantity'].replace(0, np.nan)
        df['_rp_ratio'] = df['_rp_ratio'].fillna(1.0).clip(0, 2)
        df['_rp_norm'] = _normalize_series(df['_rp_ratio'])   # higher ratio → more urgent
    else:
        df['_rp_norm'] = 0.5

    # ── ABC class weight ──
    df['_abc_w'] = df['abc_class'].apply(_abc_weight)

    # ── Procurement cost factor: annual_value normalised ──
    df['_cost_norm'] = _normalize_series(df['annual_value'])

    # ── Safety stock risk: ratio of safety_stock to avg_monthly_demand ──
    if 'safety_stock' in df.columns and 'avg_monthly_demand' in df.columns:
        df['_ss_ratio'] = df['safety_stock'] / df['avg_monthly_demand'].replace(0, np.nan)
        df['_ss_ratio'] = df['_ss_ratio'].fillna(0).clip(0, 5)
        # High SS vs demand means more exposure → higher risk
        df['_ss_norm'] = _normalize_series(df['_ss_ratio'])
    else:
        df['_ss_norm'] = 0.5

    # ── Composite score (weights sum to 1.0) ──
    df['priority_score'] = (
        df['_fc_demand_norm'] * 0.30   # forecast demand
        + df['_rp_norm']       * 0.25  # reorder urgency
        + df['_abc_w']         * 0.20  # ABC category
        + df['_cost_norm']     * 0.15  # procurement cost
        + df['_ss_norm']       * 0.10  # safety stock risk
    ) * 100

    df['priority_score'] = df['priority_score'].round(1)
    return df


def _priority_level(score: float) -> str:
    if score >= 70:
        return 'Critical'
    elif score >= 45:
        return 'Monitor'
    return 'Stable'


def _status_label(row) -> str:
    abc = str(row.get('abc_class', 'C')).upper()
    score = row.get('priority_score', 0)
    if score >= 70:
        return 'Critical Procurement'
    elif abc == 'A' and score >= 45:
        return 'High Attention'
    elif score >= 45:
        return 'Monitor Closely'
    return 'Stable'


def _recommendation(row) -> str:
    score = row.get('priority_score', 0)
    abc = str(row.get('abc_class', 'C')).upper()
    if score >= 70:
        return 'Immediate procurement action required'
    elif score >= 55:
        return 'Expedite purchase order this week'
    elif score >= 45:
        return 'Review stock levels and reorder soon'
    elif abc == 'A':
        return 'Maintain safety stock buffer'
    return 'Continue standard replenishment cycle'


def get_procurement_ranking(inv_result: dict, forecast_result: Optional[dict], top_n: int = 10) -> dict:
    """
    Return the top N priority materials with rank, scores, labels, and recommendations.
    Reuses inv_result and forecast_result computed upstream.
    """
    if not inv_result:
        return {'rankings': [], 'summary': {}}

    inv_df = inv_result.get('data', pd.DataFrame())
    if inv_df.empty:
        return {'rankings': [], 'summary': {}}

    forecasts = (forecast_result or {}).get('forecasts', [])

    scored = compute_priority_scores(inv_df, forecasts)
    scored = scored.sort_values('priority_score', ascending=False).reset_index(drop=True)

    rankings = []
    for i, row in scored.head(top_n).iterrows():
        level = _priority_level(row['priority_score'])
        rankings.append({
            'rank':            i + 1,
            'material_code':   row.get('material_code', ''),
            'description':     row.get('description', ''),
            'priority_score':  row['priority_score'],
            'priority_level':  level,
            'status':          _status_label(row),
            'recommendation':  _recommendation(row),
            'abc_class':       row.get('abc_class', 'C'),
            'annual_value':    row.get('annual_value', 0),
            'reorder_point':   row.get('reorder_point', 0),
            'safety_stock':    row.get('safety_stock', 0),
        })

    critical_count = sum(1 for r in rankings if r['priority_level'] == 'Critical')
    monitor_count  = sum(1 for r in rankings if r['priority_level'] == 'Monitor')

    return {
        'rankings':       rankings,
        'critical_count': critical_count,
        'monitor_count':  monitor_count,
        'stable_count':   len(rankings) - critical_count - monitor_count,
        'summary': {
            'total_ranked':    len(scored),
            'top_n_shown':     len(rankings),
            'critical_count':  critical_count,
        }
    }


# ─────────────────────────────────────────────────────────────
# Risk Detection Engine
# ─────────────────────────────────────────────────────────────

def _demand_spike_pct(fc: dict) -> Optional[float]:
    """Compare next-quarter demand to current annual/4."""
    nqd = fc.get('next_quarter_demand', 0)
    ann = fc.get('annual_quantity', 0)
    baseline = ann / 4 if ann else 0
    if baseline <= 0:
        return None
    return round(((nqd - baseline) / baseline) * 100, 1)


def detect_top_risk_materials(inv_result: dict, forecast_result: Optional[dict], top_n: int = 8) -> dict:
    """
    Detect materials with highest procurement risk using:
    - Abnormal demand spikes
    - Low safety stock vs demand
    - Rising procurement cost (high annual_value + peak trend)
    - Unstable forecast (high RMSE)
    - Reorder urgency (reorder_point close to stock level)
    """
    if not inv_result:
        return {'risks': [], 'alerts': []}

    inv_df    = inv_result.get('data', pd.DataFrame())
    forecasts = (forecast_result or {}).get('forecasts', [])
    fc_map    = {f['material_code']: f for f in forecasts}

    risks = []

    for _, row in inv_df.iterrows():
        code = row.get('material_code', '')
        desc = row.get('description', '')
        fc   = fc_map.get(code, {})

        risk_score  = 0
        risk_alerts = []

        # 1. Demand spike
        spike = _demand_spike_pct(fc)
        if spike is not None and spike >= 15:
            risk_score += min(spike / 2, 40)
            risk_alerts.append(f"Forecast demand increased by {spike:.0f}%")

        # 2. Safety stock critically low vs monthly demand
        ss  = row.get('safety_stock', 0)
        amd = row.get('avg_monthly_demand', 1)
        if amd > 0 and ss < amd * 0.5:
            risk_score += 25
            pct = round((ss / amd) * 100)
            risk_alerts.append(f"Safety stock critically low ({pct}% of monthly demand)")

        # 3. High annual value + rising trend → cost exposure
        av = row.get('annual_value', 0)
        trend = (fc.get('trend', 'normal') or 'normal').lower()
        if av > 0 and trend == 'peak':
            top_pct = av / max(inv_df['annual_value'].max(), 1)
            if top_pct > 0.5:
                risk_score += 20
                risk_alerts.append("Procurement cost rising rapidly for high-value item")

        # 4. Unstable forecast (high forecast error)
        rmse = fc.get('rmse', 0) or 0
        mean_d = fc.get('mean_demand', 1) or 1
        cv = rmse / mean_d if mean_d else 0
        if cv > 0.25:
            risk_score += 15
            risk_alerts.append(f"Unstable forecasting trend detected (CV: {cv:.1f})")

        # 5. Reorder urgency – reorder_point > 30% of annual qty
        rp  = row.get('reorder_point', 0)
        qty = row.get('quantity', 1)
        if qty > 0 and rp / qty > 0.40:
            risk_score += 15
            risk_alerts.append("Reorder point exceeds 40% of annual quantity — replenishment overdue")

        # 6. Unusual consumption (high EOQ vs safety_stock mismatch)
        eoq = row.get('eoq', 0)
        if eoq > 0 and ss > 0 and eoq / ss > 8:
            risk_score += 10
            risk_alerts.append("Unusual consumption pattern detected")

        if risk_alerts:
            risks.append({
                'material_code': code,
                'description':   desc,
                'risk_score':    round(min(risk_score, 100), 1),
                'abc_class':     row.get('abc_class', 'C'),
                'annual_value':  av,
                'alerts':        risk_alerts,
                'trend':         trend,
            })

    # Sort by risk score descending
    risks.sort(key=lambda x: x['risk_score'], reverse=True)
    top_risks = risks[:top_n]

    # Build executive-friendly alert strings
    exec_alerts = []
    for r in top_risks[:5]:
        for alert_msg in r['alerts'][:1]:   # top alert per material
            exec_alerts.append({
                'material': r['description'] or r['material_code'],
                'message':  alert_msg,
                'severity': 'high' if r['risk_score'] >= 50 else 'medium',
            })

    return {
        'risks':           top_risks,
        'exec_alerts':     exec_alerts,
        'high_risk_count': sum(1 for r in risks if r['risk_score'] >= 50),
        'medium_risk_count': sum(1 for r in risks if 25 <= r['risk_score'] < 50),
    }


# ─────────────────────────────────────────────────────────────
# Smart Insight Integration
# ─────────────────────────────────────────────────────────────

def generate_procurement_insights(ranking_result: dict, risk_result: dict,
                                   inv_result: dict, forecast_result: Optional[dict]) -> list:
    """
    Generate executive-friendly procurement smart insights.
    Integrated into the existing Smart Insight Engine pattern.
    """
    insights = []
    critical = ranking_result.get('critical_count', 0)
    monitor  = ranking_result.get('monitor_count', 0)
    high_risk = risk_result.get('high_risk_count', 0)
    med_risk  = risk_result.get('medium_risk_count', 0)

    if critical:
        insights.append(
            f"{critical} material{'s' if critical > 1 else ''} require immediate procurement attention"
        )
    if monitor:
        insights.append(
            f"{monitor} material{'s' if monitor > 1 else ''} should be monitored closely this week"
        )
    if high_risk:
        insights.append(
            f"Procurement risk detected in {high_risk} high-value material{'s' if high_risk > 1 else ''}"
        )
    if med_risk:
        insights.append(
            f"{med_risk} material{'s' if med_risk > 1 else ''} showing elevated supply risk — review recommended"
        )

    # Forecast trend insight
    fc_sum = (forecast_result or {}).get('summary', {})
    peak = fc_sum.get('peak_count', 0)
    if peak:
        insights.append(
            f"Forecast demand expected to rise for {peak} material{'s' if peak > 1 else ''} next quarter"
        )

    # Cost insight
    cost_inc = fc_sum.get('cost_increase_pct', 0)
    if cost_inc > 5:
        insights.append(
            f"Total procurement cost projected to increase by {cost_inc:.1f}% — budget revision advised"
        )

    return insights
