"""
Phase 11: Executive Automation Layer
Central automation engine that coordinates:
- Alert priority classification
- Executive summary generation (enhanced)
- Automation status tracking
- Smart insight integration
- Proactive notification logic

Extends existing pipeline without rebuilding it.
"""
import os
import json
from datetime import datetime, timedelta
from typing import Optional

# ─────────────────────────────────────────────────────────────
# Automation Log (in-memory, lightweight)
# ─────────────────────────────────────────────────────────────

_automation_log: list = []

def _log_event(event_type: str, message: str, status: str = "info"):
    """Append event to automation log. Keeps last 100 entries."""
    _automation_log.append({
        "event_type": event_type,
        "message":    message,
        "status":     status,
        "timestamp":  datetime.now().strftime("%d %b %Y %H:%M"),
        "ts_raw":     datetime.now().isoformat(),
    })
    if len(_automation_log) > 100:
        _automation_log.pop(0)

def get_automation_log() -> list:
    return list(reversed(_automation_log))


# ─────────────────────────────────────────────────────────────
# Alert Priority Engine (Phase 11 extension of alert_engine)
# ─────────────────────────────────────────────────────────────

PRIORITY_WEIGHTS = {
    "CRITICAL": 3,
    "MEDIUM":   2,
    "LOW":      1,
}

CATEGORY_ICONS = {
    "restock":     "fas fa-boxes-stacked",
    "procurement": "fas fa-truck",
    "demand":      "fas fa-chart-line",
    "overstock":   "fas fa-warehouse",
    "dead_stock":  "fas fa-skull-crossbones",
    "forecast":    "fas fa-chart-bar",
}

CATEGORY_RECOMMENDATIONS = {
    "restock":     "Trigger emergency procurement. Contact primary supplier immediately.",
    "procurement": "Review supplier contracts and advance purchase orders.",
    "demand":      "Adjust procurement quantities to match updated demand forecast.",
    "overstock":   "Halt new orders for affected materials. Review liquidation options.",
    "dead_stock":  "Initiate write-off review or identify alternative use cases.",
    "forecast":    "Update procurement plan to align with revised forecast data.",
}

def enrich_alerts_for_dashboard(alert_result: dict) -> dict:
    """
    Enrich existing alert_result with dashboard-ready fields:
    - icons per category
    - recommended action per alert
    - severity score for sorting
    - color class for badge rendering
    """
    if not alert_result:
        return alert_result

    enriched_alerts = []
    for alert in alert_result.get("alerts", []):
        cat = alert.get("category", "")
        priority = alert.get("priority", "LOW")
        enriched = dict(alert)
        enriched["icon"]           = CATEGORY_ICONS.get(cat, "fas fa-bell")
        enriched["recommendation"] = CATEGORY_RECOMMENDATIONS.get(cat, "Review and take appropriate action.")
        enriched["severity_score"] = PRIORITY_WEIGHTS.get(priority, 1)
        enriched["badge_class"]    = {
            "CRITICAL": "badge-critical",
            "MEDIUM":   "badge-medium",
            "LOW":      "badge-info",
        }.get(priority, "badge-info")
        enriched["bg_class"] = {
            "CRITICAL": "alert-critical-bg",
            "MEDIUM":   "alert-medium-bg",
            "LOW":      "alert-low-bg",
        }.get(priority, "alert-low-bg")
        enriched_alerts.append(enriched)

    result = dict(alert_result)
    result["alerts"] = enriched_alerts
    return result


# ─────────────────────────────────────────────────────────────
# Executive Summary Generator (Phase 11 — enhanced)
# ─────────────────────────────────────────────────────────────

def generate_automation_summary(
    inv_result: dict,
    forecast_result: Optional[dict],
    alert_result: Optional[dict],
    dead_stock_result: Optional[dict],
    scheduler_status: Optional[dict],
) -> dict:
    """
    Generate a concise, non-technical executive automation summary.
    Designed to sit at the top of the Executive Dashboard.
    Returns structured data for template rendering.
    """
    bullets   = []
    actions   = []
    warnings  = []
    positives = []

    now_label = datetime.now().strftime("%d %b %Y")

    # ── Inventory snapshot ──
    if inv_result:
        inv_sum = inv_result.get("summary", {})
        total   = inv_sum.get("total_items", 0)
        val     = inv_sum.get("total_value", 0)
        abc     = inv_sum.get("abc_counts", {})
        a_cnt   = abc.get("A", 0)

        bullets.append(f"Monitoring {total} materials with total annual value of ₹{val:,.0f}.")
        if a_cnt:
            bullets.append(f"{a_cnt} high-priority Class A materials require active oversight this week.")

    # ── Forecast signals ──
    if forecast_result:
        fc_sum     = forecast_result.get("summary", {})
        peak_count = fc_sum.get("peak_count", 0)
        low_count  = fc_sum.get("low_count", 0)
        cost_inc   = fc_sum.get("cost_increase_pct", 0)

        if peak_count >= 5:
            warnings.append(f"Demand surge detected — {peak_count} materials forecast for peak demand next quarter.")
        elif peak_count > 0:
            bullets.append(f"Forecast shows rising demand for {peak_count} material(s) — advance procurement recommended.")

        if low_count >= 3:
            bullets.append(f"{low_count} materials show declining demand — procurement volumes should be reviewed.")

        if cost_inc > 10:
            warnings.append(f"Procurement cost expected to rise {cost_inc:.1f}% next quarter — budget review required.")
        elif cost_inc > 0:
            bullets.append(f"Estimated next-quarter procurement cost increase: {cost_inc:.1f}%.")
        elif cost_inc < -5:
            positives.append(f"Procurement costs are trending down by {abs(cost_inc):.1f}% — favorable outlook.")

    # ── Alert signals ──
    if alert_result:
        crit = alert_result.get("critical_count", 0)
        med  = alert_result.get("medium_count",   0)
        low  = alert_result.get("low_count",      0)

        if crit:
            warnings.append(f"{crit} critical alert{'s' if crit > 1 else ''} require immediate action — procurement or stock shortage detected.")
            actions.append("Escalate critical alerts to procurement team immediately.")
        if med:
            bullets.append(f"{med} medium-priority issue{'s' if med > 1 else ''} identified — plan resolution within 7 days.")
        if not crit and not med:
            positives.append("No critical or medium-priority alerts — inventory position is stable.")

    # ── Dead stock signals ──
    if dead_stock_result and dead_stock_result.get("has_data"):
        dead_cnt  = dead_stock_result.get("dead_count", 0)
        over_cnt  = dead_stock_result.get("overstock_count", 0)
        flag_val  = dead_stock_result.get("total_flagged_value", 0)

        if dead_cnt:
            warnings.append(f"{dead_cnt} dead stock material{'s' if dead_cnt > 1 else ''} detected — capital is locked in non-moving inventory.")
            actions.append(f"Review {dead_cnt} dead stock items for write-off or repurposing.")
        if over_cnt:
            bullets.append(f"Overstock risk identified in {over_cnt} material{'s' if over_cnt > 1 else ''} — holding costs may be elevated.")
        if flag_val > 0:
            bullets.append(f"Total value tied up in flagged materials: ₹{flag_val:,.0f}.")

    # ── Scheduler status ──
    if scheduler_status:
        if scheduler_status.get("running"):
            positives.append("Automated monitoring is active — daily alerts and weekly forecasts are running.")
        else:
            bullets.append("Automated scheduler is not running. Start the app to enable background monitoring.")

    # ── Headline ──
    if warnings:
        headline = f"⚠ Action Required — {len(warnings)} issue{'s' if len(warnings) > 1 else ''} identified that need management attention."
        headline_class = "headline-warning"
    elif actions:
        headline = f"Review Recommended — {len(actions)} item{'s' if len(actions) > 1 else ''} pending action from the procurement team."
        headline_class = "headline-action"
    else:
        headline = "✓ Inventory Position Stable — No critical risks detected as of today."
        headline_class = "headline-ok"

    # ── Automation insights (for smart insight panel) ──
    automation_insights = []
    if alert_result and alert_result.get("critical_count", 0):
        automation_insights.append(f"Automated procurement alert triggered — {alert_result['critical_count']} critical issue(s) flagged.")
    if forecast_result and forecast_result.get("summary", {}).get("peak_count", 0) >= 3:
        automation_insights.append(f"Forecast anomaly detected — demand surge signals observed in {forecast_result['summary']['peak_count']} materials.")
    if dead_stock_result and dead_stock_result.get("dead_count", 0):
        automation_insights.append(f"Dead stock monitoring completed — {dead_stock_result['dead_count']} non-moving materials identified.")
    if scheduler_status and scheduler_status.get("running"):
        automation_insights.append("Inventory monitoring completed successfully — all scheduled jobs are active.")
    if not automation_insights:
        automation_insights.append("Automated system check completed — no anomalies detected.")

    _log_event("executive_summary", f"Executive automation summary generated — {len(warnings)} warnings, {len(actions)} actions.", "success")

    return {
        "headline":             headline,
        "headline_class":       headline_class,
        "bullets":              bullets,
        "warnings":             warnings,
        "positives":            positives,
        "actions":              actions,
        "automation_insights":  automation_insights,
        "generated_at":         now_label,
        "total_issues":         len(warnings) + len(actions),
    }


# ─────────────────────────────────────────────────────────────
# Automation Status Panel Data
# ─────────────────────────────────────────────────────────────

def get_automation_status(scheduler_status: dict, alert_result: dict, email_configured: bool) -> dict:
    """
    Build a rich automation status payload for the dashboard panel.
    """
    jobs = scheduler_status.get("jobs", []) if scheduler_status else []
    log  = scheduler_status.get("log", [])  if scheduler_status else []

    tasks = [
        {
            "name":        "Daily Alert Monitoring",
            "description": "Checks inventory for critical shortages and procurement risks.",
            "frequency":   "Every day at 07:00 UTC",
            "icon":        "fas fa-bell",
            "status":      "active" if scheduler_status and scheduler_status.get("running") else "idle",
            "job_id":      "alert_check",
        },
        {
            "name":        "Weekly Forecast Refresh",
            "description": "Updates demand forecasts and identifies trend changes.",
            "frequency":   "Every Monday at 02:00 UTC",
            "icon":        "fas fa-chart-line",
            "status":      "active" if scheduler_status and scheduler_status.get("running") else "idle",
            "job_id":      "weekly_forecast",
        },
        {
            "name":        "Monthly Executive Report",
            "description": "Generates and saves full inventory Excel report to /exports/.",
            "frequency":   "1st of every month at 03:00 UTC",
            "icon":        "fas fa-file-excel",
            "status":      "active" if scheduler_status and scheduler_status.get("running") else "idle",
            "job_id":      "monthly_report",
        },
    ]

    # Enrich tasks with next_run from scheduler
    job_map = {j["id"]: j for j in jobs}
    for task in tasks:
        sched_job = job_map.get(task["job_id"])
        task["next_run"] = sched_job["next_run"] if sched_job else "Scheduler not running"

    email_status = "configured" if email_configured else "not_configured"

    return {
        "scheduler_running": scheduler_status.get("running", False) if scheduler_status else False,
        "scheduler_available": scheduler_status.get("available", False) if scheduler_status else False,
        "tasks":              tasks,
        "email_status":       email_status,
        "email_configured":   email_configured,
        "recent_log":         log[:8],
        "automation_log":     get_automation_log()[:10],
        "total_alerts":       alert_result.get("total", 0)       if alert_result else 0,
        "critical_alerts":    alert_result.get("critical_count", 0) if alert_result else 0,
    }


# ─────────────────────────────────────────────────────────────
# Proactive Notification Classifier
# ─────────────────────────────────────────────────────────────

def classify_notification_urgency(alert_result: dict, forecast_result: dict, dead_stock_result: dict) -> str:
    """
    Returns: 'CRITICAL' | 'MEDIUM' | 'LOW' | 'NONE'
    Used to decide whether to trigger an automated email.
    """
    if not alert_result:
        return "NONE"

    if alert_result.get("critical_count", 0) > 0:
        return "CRITICAL"

    if alert_result.get("medium_count", 0) >= 2:
        return "MEDIUM"

    if dead_stock_result and dead_stock_result.get("dead_count", 0) >= 3:
        return "MEDIUM"

    if forecast_result:
        fc = forecast_result.get("summary", {})
        if fc.get("peak_count", 0) >= 5 or fc.get("cost_increase_pct", 0) > 15:
            return "MEDIUM"

    if alert_result.get("total", 0) > 0:
        return "LOW"

    return "NONE"
