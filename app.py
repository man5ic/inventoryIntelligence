"""
Inventory Intelligence System
Phase 1  (Architecture)
Phase 2  (Inventory Intelligence)
Phase 3  (Forecasting)
Phase 4  (Automation, Alerts, Executive Assistance)
Phase 5  (Material Intelligence)
Phase 6  (Procurement Priority Ranking)
Phase 7  (Region/Plant/Period Filtering)
Phase 8  (Executive Reports)
Phase 9  (Dead Stock Detection)
Phase 11 (Executive Automation Layer — fully integrated into /alerts panel)
         All Phase 11 UI (automation banner, enriched alerts, automation status,
         manual trigger, automation log) lives in templates/alerts.html.
         The alerts_page() route computes all Phase 11 data.
         API endpoints /api/automation-status, /api/automation-summary,
         and /api/trigger-alert-check remain active.
"""
import os
import json
import pandas as pd
from io import BytesIO
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, send_file, session, flash
)

from modules.inventory_intelligence import run_inventory_intelligence
from modules.material_intelligence import get_material_intelligence, get_all_materials
from modules.forecasting import run_forecast_engine
from modules.chart_generator import generate_all_charts
from modules.report_export import generate_excel_report
from modules.alert_engine import run_alert_engine
from modules.executive_summary import generate_executive_summary
from modules.email_alerts import send_alert_email, is_email_configured
from modules.scheduler import init_scheduler, get_scheduler_status
from modules.procurement_ranking import (
    get_procurement_ranking, detect_top_risk_materials, generate_procurement_insights
)
from modules.filter_engine import (
    apply_filters, build_filter_context,
    generate_filter_insights, enrich_sample_with_filters,
    ALL_OPTION
)
from modules.dead_stock_detection import run_dead_stock_detection
from modules.material_report import generate_material_report
from modules.executive_report import generate_executive_report as generate_exec_report_p8

# ── Phase 11: Executive Automation Layer ──
from modules.automation_engine import (
    enrich_alerts_for_dashboard,
    generate_automation_summary,
    get_automation_status,
    classify_notification_urgency,
    get_automation_log,
)

# ─────────────────────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = 'inventory-intelligence-system-2025'

# ── Phase 4: Email config (set via environment variables or here) ──
app.config['MAIL_SERVER']         = os.getenv('MAIL_SERVER',   'smtp.gmail.com')
app.config['MAIL_PORT']           = int(os.getenv('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS']        = True
app.config['MAIL_USERNAME']       = os.getenv('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD']       = os.getenv('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', '')
app.config['ALERT_RECIPIENT']     = os.getenv('ALERT_RECIPIENT', '')

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

DATASET_FILE    = os.path.join(DATA_DIR, 'inventory_dataset.csv')
COLUMN_MAP_FILE = os.path.join(DATA_DIR, 'column_map.json')


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def load_dataset() -> pd.DataFrame:
    if os.path.exists(DATASET_FILE):
        try:
            return pd.read_csv(DATASET_FILE)
        except Exception:
            pass
    return pd.DataFrame()


def save_dataset(df: pd.DataFrame):
    df.to_csv(DATASET_FILE, index=False)


def load_column_map() -> dict:
    if os.path.exists(COLUMN_MAP_FILE):
        try:
            with open(COLUMN_MAP_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_column_map(mapping: dict):
    with open(COLUMN_MAP_FILE, 'w') as f:
        json.dump(mapping, f)


def parse_upload(file) -> pd.DataFrame:
    filename = file.filename.lower()
    if filename.endswith('.csv'):
        return pd.read_csv(file)
    elif filename.endswith(('.xlsx', '.xls')):
        return pd.read_excel(file)
    else:
        raise ValueError(f"Unsupported file format: {filename}")


def get_intelligence_data(plant=ALL_OPTION, region=ALL_OPTION, period=ALL_OPTION):
    """Run full Phase 2–6 pipeline with optional Plant/Region/Period filtering."""
    df = load_dataset()
    if df.empty:
        return None, None, None, None, None, None, None

    column_map = load_column_map()

    # ── Phase 7: Apply filters before all computations ──
    filtered_df = apply_filters(df, column_map, plant=plant, region=region, period=period)
    if filtered_df.empty:
        filtered_df = df   # graceful fallback — never crash on empty filter

    inv_result   = run_inventory_intelligence(filtered_df, column_map)
    inv_df       = inv_result['data']

    forecast_result = run_forecast_engine(inv_df)
    charts          = generate_all_charts(forecast_result)

    # Phase 4
    alert_result = run_alert_engine(inv_result, forecast_result)
    exec_summary = generate_executive_summary(inv_result, forecast_result, alert_result)

    # Phase 6
    ranking_result = get_procurement_ranking(inv_result, forecast_result, top_n=10)
    risk_result    = detect_top_risk_materials(inv_result, forecast_result, top_n=8)

    proc_insights = generate_procurement_insights(ranking_result, risk_result, inv_result, forecast_result)

    # Phase 7: Filter-aware smart insights
    filter_insights = generate_filter_insights(inv_result, forecast_result, plant, region, period)
    exec_summary['procurement_insights'] = filter_insights + proc_insights

    # Phase 9: Low-Movement & Dead Stock Detection
    dead_stock_result = run_dead_stock_detection(inv_result, forecast_result)
    if dead_stock_result.get('smart_insights'):
        exec_summary['procurement_insights'] = (
            dead_stock_result['smart_insights'] + exec_summary['procurement_insights']
        )

    # ── Phase 11: Enrich alerts with icons, recommendations, badge classes ──
    alert_result = enrich_alerts_for_dashboard(alert_result)

    return inv_result, forecast_result, charts, alert_result, exec_summary, ranking_result, risk_result, dead_stock_result

# ─────────────────────────────────────────────────────────────
# Routes – Phases 1-3 (unchanged interface)
# ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    df         = load_dataset()
    column_map = load_column_map()
    has_data   = not df.empty
    return render_template('index.html',
                           has_data=has_data,
                           row_count=len(df) if has_data else 0,
                           col_count=len(df.columns) if has_data else 0,
                           columns=df.columns.tolist() if has_data else [],
                           column_map=column_map)


@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    file = request.files['file']
    if not file.filename:
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    mode = request.form.get('mode', 'replace')
    try:
        new_df = parse_upload(file)
        if mode == 'append' and os.path.exists(DATASET_FILE):
            existing_df = load_dataset()
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            save_dataset(combined_df)
            flash(f'Appended {len(new_df)} rows. Total: {len(combined_df)} rows', 'success')
        else:
            save_dataset(new_df)
            flash(f'Dataset uploaded: {len(new_df)} rows, {len(new_df.columns)} columns', 'success')
    except Exception as e:
        flash(f'Upload error: {str(e)}', 'error')
    return redirect(url_for('column_mapping'))


@app.route('/column-mapping', methods=['GET', 'POST'])
def column_mapping():
    df = load_dataset()
    if df.empty:
        flash('Please upload a dataset first', 'warning')
        return redirect(url_for('index'))
    columns        = df.columns.tolist()
    required_fields  = ['material_code', 'description', 'quantity', 'unit_price',
                         'lead_time', 'category']
    optional_fields  = ['plant', 'region', 'date', 'month', 'year']
    all_fields       = required_fields + optional_fields
    if request.method == 'POST':
        mapping = {f: request.form.get(f, '') for f in all_fields if request.form.get(f)}
        save_column_map(mapping)
        flash('Column mapping saved successfully', 'success')
        return redirect(url_for('dashboard'))
    return render_template('column_mapping.html',
                           columns=columns,
                           required_fields=required_fields,
                           optional_fields=optional_fields,
                           current_map=load_column_map())


@app.route('/dashboard')
def dashboard():
    df = load_dataset()
    if df.empty:
        flash('Please upload a dataset first', 'warning')
        return redirect(url_for('index'))

    # ── Phase 7: Read filter params from query string ──
    column_map     = load_column_map()
    sel_plant      = request.args.get('plant',  ALL_OPTION)
    sel_region     = request.args.get('region', ALL_OPTION)
    sel_period     = request.args.get('period', ALL_OPTION)

    inv_result, forecast_result, charts, alert_result, exec_summary, ranking_result, risk_result, dead_stock_result = \
        get_intelligence_data(plant=sel_plant, region=sel_region, period=sel_period)

    if inv_result is None:
        flash('Could not process data', 'error')
        return redirect(url_for('index'))

    inv_df       = inv_result['data']
    display_cols = ['material_code', 'description', 'quantity', 'unit_price',
                    'annual_value', 'eoq', 'safety_stock', 'reorder_point',
                    'abc_class', 'recommendation']
    available_cols = [c for c in display_cols if c in inv_df.columns]
    table_data     = inv_df[available_cols].head(50).to_dict(orient='records')
    forecast_table = forecast_result.get('forecasts', [])[:30]

    scheduler_status = get_scheduler_status()

    # Build filter context (dropdown options + selections)
    filter_ctx = build_filter_context(df, column_map, sel_plant, sel_region, sel_period)

    return render_template('dashboard.html',
                           inv_result=inv_result,
                           forecast_result=forecast_result,
                           forecast_summary=forecast_result.get('summary', {}),
                           exec_insights=forecast_result.get('exec_insights', []),
                           table_data=table_data,
                           forecast_table=forecast_table,
                           charts=charts,
                           # Phase 4
                           alert_result=alert_result,
                           exec_summary=exec_summary,
                           scheduler_status=scheduler_status,
                           email_configured=is_email_configured(app.config),
                           # Phase 6
                           ranking_result=ranking_result,
                           risk_result=risk_result,
                           # Phase 7
                           filter_ctx=filter_ctx,
                           # Phase 9
                           dead_stock_result=dead_stock_result,
                           now=datetime.now().strftime('%d %b %Y'))


@app.route('/forecast')
def forecast_page():
    df = load_dataset()
    if df.empty:
        flash('Please upload a dataset first', 'warning')
        return redirect(url_for('index'))
    inv_result, forecast_result, charts, alert_result, exec_summary, ranking_result, risk_result, _ds = get_intelligence_data()
    if forecast_result is None:
        flash('Could not generate forecasts', 'error')
        return redirect(url_for('dashboard'))
    return render_template('forecast.html',
                           forecast_result=forecast_result,
                           forecast_summary=forecast_result.get('summary', {}),
                           exec_insights=forecast_result.get('exec_insights', []),
                           forecasts=forecast_result.get('forecasts', []),
                           charts=charts,
                           alert_result=alert_result,
                           now=datetime.now().strftime('%d %b %Y'))


# ─────────────────────────────────────────────────────────────
# Phase 4 Routes
# ─────────────────────────────────────────────────────────────

@app.route('/alerts')
def alerts_page():
    df = load_dataset()
    if df.empty:
        flash('Please upload a dataset first', 'warning')
        return redirect(url_for('index'))
    inv_result, forecast_result, _, alert_result, exec_summary, _r, _rk, _ds = get_intelligence_data()

    # ── Phase 11: Compute all automation data for the Alerts panel ──
    scheduler_status     = get_scheduler_status()
    automation_summary   = generate_automation_summary(
        inv_result, forecast_result, alert_result, _ds, scheduler_status
    )
    automation_status    = get_automation_status(scheduler_status, alert_result, is_email_configured(app.config))
    notification_urgency = classify_notification_urgency(alert_result, forecast_result, _ds)
    automation_log       = get_automation_log()[:8]

    return render_template('alerts.html',
                           alert_result=alert_result,
                           exec_summary=exec_summary,
                           email_configured=is_email_configured(app.config),
                           # Phase 11
                           automation_summary=automation_summary,
                           automation_status=automation_status,
                           notification_urgency=notification_urgency,
                           automation_log=automation_log,
                           now=datetime.now().strftime('%d %b %Y'))


@app.route('/api/alerts')
def api_alerts():
    inv_result, forecast_result, _, alert_result, exec_summary, _r, _rk, _ds = get_intelligence_data()
    if alert_result is None:
        return jsonify({'error': 'No data'}), 404
    return jsonify(alert_result)


@app.route('/api/procurement-ranking')
def api_procurement_ranking():
    inv_result, forecast_result, _, _, _, ranking_result, risk_result, _ds = get_intelligence_data()
    if ranking_result is None:
        return jsonify({'error': 'No data'}), 404
    return jsonify({'ranking': ranking_result, 'risks': risk_result})


@app.route('/api/filter-options')
def api_filter_options():
    """Return available plant/region/time filter options for the current dataset."""
    df         = load_dataset()
    column_map = load_column_map()
    if df.empty:
        return jsonify({'plants': [], 'regions': [], 'month_labels': [],
                        'quarter_options': [], 'year_options': []})
    from modules.filter_engine import get_filter_options, get_quarter_options
    opts = get_filter_options(df, column_map)
    quarters = get_quarter_options(opts.get('years', []))
    years    = [{'value': y, 'label': f"Full Year {y}"} for y in opts.get('years', [])]
    return jsonify({
        'plants':           opts.get('plants', []),
        'regions':          opts.get('regions', []),
        'month_labels':     opts.get('month_labels', []),
        'quarter_options':  quarters,
        'year_options':     years,
        'has_plant':        opts.get('has_plant', False),
        'has_region':       opts.get('has_region', False),
    })


@app.route('/api/dashboard-data')
def api_dashboard_data():
    """JSON endpoint for filtered dashboard data — used by JS for live updates."""
    sel_plant  = request.args.get('plant',  ALL_OPTION)
    sel_region = request.args.get('region', ALL_OPTION)
    sel_period = request.args.get('period', ALL_OPTION)

    inv_result, forecast_result, _, alert_result, exec_summary, ranking_result, risk_result, _ds = \
        get_intelligence_data(plant=sel_plant, region=sel_region, period=sel_period)

    if inv_result is None:
        return jsonify({'error': 'No data'}), 404

    return jsonify({
        'summary': {
            **inv_result.get('summary', {}),
            'forecast': forecast_result.get('summary', {}),
            'alerts':   {'total': alert_result.get('total', 0),
                         'critical': alert_result.get('critical_count', 0)},
        },
        'ranking':  ranking_result,
        'risks':    risk_result,
        'insights': exec_summary.get('procurement_insights', []),
        'kpis':     exec_summary.get('kpis', {}),
    })


@app.route('/api/executive-summary')
def api_exec_summary():
    inv_result, forecast_result, _, alert_result, exec_summary, _r, _rk, _ds = get_intelligence_data()
    if exec_summary is None:
        return jsonify({'error': 'No data'}), 404
    return jsonify(exec_summary)


@app.route('/send-alert-email', methods=['POST'])
def send_alert_email_route():
    inv_result, forecast_result, _, alert_result, exec_summary, _r, _rk, _ds = get_intelligence_data()
    if alert_result is None:
        flash('No data to send alert for', 'error')
        return redirect(url_for('alerts_page'))

    result = send_alert_email(alert_result, exec_summary, app.config)
    if result['success']:
        flash(result['message'], 'success')
    else:
        flash(result['message'], 'error')
    return redirect(url_for('alerts_page'))


@app.route('/api/scheduler-status')
def api_scheduler_status():
    return jsonify(get_scheduler_status())


# ─────────────────────────────────────────────────────────────
# API (Phase 3 unchanged)
# ─────────────────────────────────────────────────────────────

@app.route('/api/forecast-chart/<material_code>')
def api_forecast_chart(material_code):
    from modules.chart_generator import chart_forecast_line
    inv_result, forecast_result, _, _, _, _r, _rk, _ds = get_intelligence_data()
    if forecast_result is None:
        return jsonify({'error': 'No data'}), 404
    forecasts = forecast_result.get('forecasts', [])
    mat = next((f for f in forecasts if f['material_code'] == material_code), None)
    if not mat:
        return jsonify({'error': 'Material not found'}), 404
    img = chart_forecast_line(mat)
    return jsonify({'image': img, 'material': mat})


@app.route('/api/summary')
def api_summary():
    inv_result, forecast_result, _, alert_result, exec_summary, _r, _rk, _ds = get_intelligence_data()
    if inv_result is None:
        return jsonify({'error': 'No data'}), 404
    return jsonify({
        'inventory': inv_result.get('summary', {}),
        'forecast':  forecast_result.get('summary', {}) if forecast_result else {},
        'alerts':    {'total': alert_result.get('total', 0),
                      'critical': alert_result.get('critical_count', 0)} if alert_result else {},
    })


# ─────────────────────────────────────────────────────────────
# Download / Export (Phase 4 enhanced)
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# Phase 5: Material Intelligence Routes
# ─────────────────────────────────────────────────────────────

@app.route('/material-intelligence')
def material_intelligence():
    df = load_dataset()
    if df.empty:
        flash('Please upload a dataset first', 'warning')
        return redirect(url_for('index'))

    inv_result, forecast_result, _, _, _, _r, _rk, _ds = get_intelligence_data()
    if inv_result is None:
        flash('Could not process data', 'error')
        return redirect(url_for('index'))

    materials = get_all_materials(inv_result)
    selected_code = request.args.get('material', '')
    material_data = None

    if selected_code:
        material_data = get_material_intelligence(selected_code, inv_result, forecast_result)

    return render_template(
        'material_intelligence.html',
        materials=materials,
        selected_code=selected_code,
        material_data=material_data,
        now=datetime.now().strftime('%d %b %Y'),
    )


@app.route('/api/material-intelligence/<material_code>')
def api_material_intelligence(material_code):
    inv_result, forecast_result, _, _, _, _r, _rk, _ds = get_intelligence_data()
    if inv_result is None:
        return jsonify({'error': 'No data'}), 404
    data = get_material_intelligence(material_code, inv_result, forecast_result)
    if data is None:
        return jsonify({'error': 'Material not found'}), 404
    return jsonify(data)


@app.route('/api/materials-list')
def api_materials_list():
    inv_result, _, _, _, _, _r, _rk, _ds = get_intelligence_data()
    if inv_result is None:
        return jsonify([])
    return jsonify(get_all_materials(inv_result))


@app.route('/download/report')
def download_report():
    inv_result, forecast_result, _, alert_result, exec_summary, _r, _rk, _ds = get_intelligence_data()
    if inv_result is None:
        flash('No data to export', 'error')
        return redirect(url_for('dashboard'))
    try:
        output   = generate_excel_report(inv_result, forecast_result, alert_result, exec_summary)
        filename = f"inventory_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return send_file(output, as_attachment=True, download_name=filename,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        flash(f'Export error: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


# ─────────────────────────────────────────────────────────────
# Phase 8: Material Report Download
# ─────────────────────────────────────────────────────────────

@app.route('/download/material-report/<material_code>')
def download_material_report(material_code):
    """Generate and download a professional Excel report for a single material."""
    inv_result, forecast_result, _, _, _, _r, _rk, _ds = get_intelligence_data()
    if inv_result is None:
        flash('No data available', 'error')
        return redirect(url_for('material_intelligence'))

    from modules.material_intelligence import get_material_intelligence
    material_data = get_material_intelligence(material_code, inv_result, forecast_result)

    if material_data is None:
        flash(f'Material {material_code} not found', 'error')
        return redirect(url_for('material_intelligence'))

    try:
        output = generate_material_report(material_data)
        safe_code = material_code.replace('/', '_').replace('\\', '_')
        filename = f"material_report_{safe_code}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return send_file(output, as_attachment=True, download_name=filename,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        flash(f'Report generation error: {str(e)}', 'error')
        return redirect(url_for('material_intelligence'))


@app.route('/api/material-report-ready/<material_code>')
def api_material_report_ready(material_code):
    """Quick check – returns the download URL if the material exists."""
    inv_result, forecast_result, _, _, _, _r, _rk, _ds = get_intelligence_data()
    if inv_result is None:
        return jsonify({'ready': False, 'error': 'No data'}), 404
    from modules.material_intelligence import get_material_intelligence
    data = get_material_intelligence(material_code, inv_result, forecast_result)
    if data is None:
        return jsonify({'ready': False, 'error': 'Material not found'}), 404
    return jsonify({
        'ready': True,
        'material_code': material_code,
        'description': data.get('description', ''),
        'download_url': url_for('download_material_report', material_code=material_code),
    })


# ─────────────────────────────────────────────────────────────
# Phase 8: Filtered Executive Report Download
# ─────────────────────────────────────────────────────────────

@app.route('/download/executive-report')
def download_executive_report():
    """Generate and download the filtered executive Excel report."""
    sel_plant  = request.args.get('plant',  ALL_OPTION)
    sel_region = request.args.get('region', ALL_OPTION)
    sel_period = request.args.get('period', ALL_OPTION)

    inv_result, forecast_result, _, alert_result, exec_summary, ranking_result, risk_result, _ds = \
        get_intelligence_data(plant=sel_plant, region=sel_region, period=sel_period)

    if inv_result is None:
        flash('No data available for export', 'error')
        return redirect(url_for('dashboard'))

    try:
        output = generate_exec_report_p8(
            inv_result, forecast_result, alert_result, exec_summary,
            ranking_result, risk_result,
            plant=sel_plant, region=sel_region, period=sel_period,
        )
        # Build a descriptive filename
        parts = []
        if sel_plant  != ALL_OPTION: parts.append(sel_plant.replace(' ', '_'))
        if sel_region != ALL_OPTION: parts.append(sel_region.replace(' ', '_'))
        if sel_period != ALL_OPTION: parts.append(sel_period.replace(' ', '_'))
        scope = '_'.join(parts) if parts else 'all'
        filename = f"executive_report_{scope}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return send_file(output, as_attachment=True, download_name=filename,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        flash(f'Executive report error: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


@app.route('/api/automation-status')
def api_automation_status():
    """Phase 11: Return full automation status as JSON."""
    inv_result, forecast_result, _, alert_result, _, _, _, dead_stock_result = get_intelligence_data()
    scheduler_status = get_scheduler_status()
    status = get_automation_status(scheduler_status, alert_result, is_email_configured(app.config))
    urgency = classify_notification_urgency(alert_result, forecast_result, dead_stock_result)
    return jsonify({**status, 'notification_urgency': urgency, 'log': get_automation_log()[:10]})


@app.route('/api/automation-summary')
def api_automation_summary():
    """Phase 11: Return executive automation summary as JSON."""
    inv_result, forecast_result, _, alert_result, _, _, _, dead_stock_result = get_intelligence_data()
    scheduler_status = get_scheduler_status()
    summary = generate_automation_summary(inv_result, forecast_result, alert_result, dead_stock_result, scheduler_status)
    return jsonify(summary)


@app.route('/api/trigger-alert-check', methods=['POST'])
def trigger_alert_check():
    """Phase 11: Manually trigger alert check and optionally send email."""
    inv_result, forecast_result, _, alert_result, exec_summary, _, _, dead_stock_result = get_intelligence_data()
    if alert_result is None:
        return jsonify({'success': False, 'message': 'No data available'}), 404

    urgency = classify_notification_urgency(alert_result, forecast_result, dead_stock_result)
    email_sent = False
    email_msg  = 'Email not configured or no critical alerts.'

    if urgency in ('CRITICAL', 'MEDIUM') and is_email_configured(app.config):
        result    = send_alert_email(alert_result, exec_summary, app.config)
        email_sent = result['success']
        email_msg  = result['message']

    from modules.automation_engine import _log_event
    _log_event('manual_trigger', f'Manual alert check completed. Urgency: {urgency}. Email: {email_msg}', 'success')

    return jsonify({
        'success':        True,
        'urgency':        urgency,
        'total_alerts':   alert_result.get('total', 0),
        'critical_count': alert_result.get('critical_count', 0),
        'email_sent':     email_sent,
        'email_message':  email_msg,
    })


# ─────────────────────────────────────────────────────────────
# Utility Routes
# ─────────────────────────────────────────────────────────────

@app.route('/clear-data', methods=['POST'])
def clear_data():
    if os.path.exists(DATASET_FILE):
        os.remove(DATASET_FILE)
    if os.path.exists(COLUMN_MAP_FILE):
        os.remove(COLUMN_MAP_FILE)
    flash('All data cleared', 'info')
    return redirect(url_for('index'))


@app.route('/load-sample')
def load_sample():
    import numpy as np
    np.random.seed(7)
    n = 40
    categories = ['Raw Material', 'Packaging', 'Spare Parts', 'Consumables', 'Chemicals']
    plants     = ['Plant 1', 'Plant 2', 'Plant 3', 'Plant 4']
    regions    = ['Region North', 'Region South', 'Region East', 'Region West']
    sample = pd.DataFrame({
        'Material Code':        [f'MAT-{1000 + i:04d}' for i in range(n)],
        'Material Description': [f'{categories[i%len(categories)]} Item {i+1}' for i in range(n)],
        'Annual Quantity':       np.random.randint(500, 50000, n),
        'Unit Rate (INR)':       np.round(np.random.uniform(10, 5000, n), 2),
        'Lead Time (Days)':      np.random.randint(7, 90, n),
        'Category':              [categories[i % len(categories)] for i in range(n)],
        'Plant':                 [plants[i % len(plants)] for i in range(n)],
        'Region':                [regions[i % len(regions)] for i in range(n)],
    })
    save_dataset(sample)
    save_column_map({
        'material_code': 'Material Code',
        'description':   'Material Description',
        'quantity':      'Annual Quantity',
        'unit_price':    'Unit Rate (INR)',
        'lead_time':     'Lead Time (Days)',
        'category':      'Category',
        'plant':         'Plant',
        'region':        'Region',
    })
    flash(f'Sample dataset loaded: {n} materials (with Plant & Region)', 'success')
    return redirect(url_for('dashboard'))


# ─────────────────────────────────────────────────────────────
# Start
# ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_scheduler(app)
    app.run(debug=True, port=5000)
