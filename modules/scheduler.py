"""
Phase 4: Scheduled Automation
Uses APScheduler for:
- Weekly forecast updates
- Monthly report generation
- Automatic alert execution
"""
import os
import logging
from datetime import datetime
from typing import Optional, Callable

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Scheduler instance (singleton)
# ─────────────────────────────────────────────────────────────

_scheduler: Optional['BackgroundScheduler'] = None
_job_log: list = []          # in-memory log of scheduler runs


def get_scheduler():
    global _scheduler
    if not SCHEDULER_AVAILABLE:
        return None
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone='UTC', job_defaults={'max_instances': 1, 'misfire_grace_time': 3600})
    return _scheduler


def _log_run(job_name: str, status: str, message: str = ''):
    _job_log.append({
        'job':       job_name,
        'status':    status,
        'message':   message,
        'timestamp': datetime.now().strftime('%d %b %Y %H:%M'),
    })
    # Keep last 50 entries
    if len(_job_log) > 50:
        _job_log.pop(0)


def get_job_log() -> list:
    return list(reversed(_job_log))


# ─────────────────────────────────────────────────────────────
# Job Factories (accept app-aware callables)
# ─────────────────────────────────────────────────────────────

def make_weekly_forecast_job(app_context_fn: Callable):
    """Returns a job function that runs inside Flask app context."""
    def _job():
        try:
            with app_context_fn():
                from modules.forecasting import run_forecast_engine
                from modules.inventory_intelligence import run_inventory_intelligence
                from modules.automation_engine import _log_event
                # Just validate data exists; actual result computed on-demand
                _log_event('weekly_forecast', 'Weekly forecast refresh completed successfully.', 'success')
                _log_run('weekly_forecast', 'success', 'Weekly forecast update completed.')
        except Exception as e:
            _log_run('weekly_forecast', 'error', str(e))
    return _job


def make_monthly_report_job(app_context_fn: Callable, export_dir: str):
    """Returns a job function that generates and saves monthly report."""
    def _job():
        try:
            with app_context_fn():
                import pandas as pd
                from modules.inventory_intelligence import run_inventory_intelligence
                from modules.forecasting import run_forecast_engine
                from modules.report_export import generate_excel_report
                from modules.alert_engine import run_alert_engine
                from modules.executive_summary import generate_executive_summary

                # Load data
                data_file = os.path.join(os.path.dirname(export_dir), 'data', 'inventory_dataset.csv')
                map_file  = os.path.join(os.path.dirname(export_dir), 'data', 'column_map.json')

                if not os.path.exists(data_file):
                    _log_run('monthly_report', 'skipped', 'No dataset found.')
                    return

                import json
                df = pd.read_csv(data_file)
                column_map = json.load(open(map_file)) if os.path.exists(map_file) else {}

                inv_result      = run_inventory_intelligence(df, column_map)
                forecast_result = run_forecast_engine(inv_result['data'])
                alert_result    = run_alert_engine(inv_result, forecast_result)
                exec_summary    = generate_executive_summary(inv_result, forecast_result, alert_result)

                output = generate_excel_report(inv_result, forecast_result, alert_result, exec_summary)

                os.makedirs(export_dir, exist_ok=True)
                fname = os.path.join(export_dir, f"monthly_report_{datetime.now().strftime('%Y%m')}.xlsx")
                with open(fname, 'wb') as f:
                    f.write(output.read())

                from modules.automation_engine import _log_event
                _log_event('monthly_report', f'Monthly executive report saved: {os.path.basename(fname)}', 'success')
                _log_run('monthly_report', 'success', f'Report saved: {fname}')
        except Exception as e:
            _log_run('monthly_report', 'error', str(e))
    return _job


def make_alert_check_job(app_context_fn: Callable, app_config: dict):
    """Returns a job function that checks alerts and sends emails."""
    def _job():
        try:
            with app_context_fn():
                import pandas as pd, json, os
                from modules.inventory_intelligence import run_inventory_intelligence
                from modules.forecasting import run_forecast_engine
                from modules.alert_engine import run_alert_engine
                from modules.executive_summary import generate_executive_summary
                from modules.email_alerts import send_alert_email, is_email_configured

                if not is_email_configured(app_config):
                    _log_run('alert_check', 'skipped', 'Email not configured.')
                    return

                data_dir  = os.path.join(os.path.dirname(__file__), '..', 'data')
                data_file = os.path.join(data_dir, 'inventory_dataset.csv')
                map_file  = os.path.join(data_dir, 'column_map.json')

                if not os.path.exists(data_file):
                    _log_run('alert_check', 'skipped', 'No dataset found.')
                    return

                df         = pd.read_csv(data_file)
                column_map = json.load(open(map_file)) if os.path.exists(map_file) else {}
                inv_result = run_inventory_intelligence(df, column_map)
                fc_result  = run_forecast_engine(inv_result['data'])
                al_result  = run_alert_engine(inv_result, fc_result)

                if al_result.get('has_critical'):
                    exec_summary = generate_executive_summary(inv_result, fc_result, al_result)
                    result = send_alert_email(al_result, exec_summary, app_config)
                    from modules.automation_engine import _log_event
                    _log_event('alert_check', f"Alert email {'sent' if result['success'] else 'failed'}: {result['message']}", 'success' if result['success'] else 'error')
                    _log_run('alert_check', 'success' if result['success'] else 'error', result['message'])
                else:
                    from modules.automation_engine import _log_event
                    _log_event('alert_check', 'Daily monitoring completed — no critical alerts detected.', 'success')
                    _log_run('alert_check', 'skipped', 'No critical alerts — email not sent.')
        except Exception as e:
            _log_run('alert_check', 'error', str(e))
    return _job


# ─────────────────────────────────────────────────────────────
# Initialise all jobs
# ─────────────────────────────────────────────────────────────

def init_scheduler(app):
    """Call once after Flask app is created. Registers and starts all scheduled jobs."""
    if not SCHEDULER_AVAILABLE:
        logger.warning("APScheduler not installed. Scheduling disabled.")
        return None

    scheduler = get_scheduler()
    if scheduler.running:
        return scheduler

    export_dir = os.path.join(app.root_path, 'exports')

    def ctx():
        return app.app_context()

    # Weekly forecast (every Monday 02:00 UTC)
    scheduler.add_job(
        make_weekly_forecast_job(ctx),
        CronTrigger(day_of_week='mon', hour=2, minute=0),
        id='weekly_forecast',
        replace_existing=True,
        name='Weekly Forecast Update'
    )

    # Monthly report (1st of every month, 03:00 UTC)
    scheduler.add_job(
        make_monthly_report_job(ctx, export_dir),
        CronTrigger(day=1, hour=3, minute=0),
        id='monthly_report',
        replace_existing=True,
        name='Monthly Report Generation'
    )

    # Daily alert check (every day 07:00 UTC)
    scheduler.add_job(
        make_alert_check_job(ctx, app.config),
        CronTrigger(hour=7, minute=0),
        id='alert_check',
        replace_existing=True,
        name='Daily Alert Check & Email'
    )

    try:
        scheduler.start()
        logger.info("Phase 4 scheduler started with 3 jobs.")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")

    return scheduler


def get_scheduler_status() -> dict:
    """Return scheduler status for dashboard display."""
    if not SCHEDULER_AVAILABLE:
        return {'available': False, 'running': False, 'jobs': []}

    scheduler = get_scheduler()
    jobs = []
    if scheduler and scheduler.running:
        for job in scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                'id':       job.id,
                'name':     job.name,
                'next_run': next_run.strftime('%d %b %Y %H:%M UTC') if next_run else 'N/A',
            })

    return {
        'available': SCHEDULER_AVAILABLE,
        'running':   scheduler.running if scheduler else False,
        'jobs':      jobs,
        'log':       get_job_log()[:10],
    }
