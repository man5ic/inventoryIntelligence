"""
Phase 3: Chart Generation for Forecast Visualizations
Generates base64-encoded chart images using matplotlib
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import io
import base64
from typing import List, Optional


PALETTE = {
    'primary': '#2563EB',
    'secondary': '#16A34A',
    'accent': '#DC2626',
    'warning': '#D97706',
    'neutral': '#6B7280',
    'bg': '#F8FAFC',
    'peak': '#16A34A',
    'normal': '#2563EB',
    'low': '#DC2626',
}

STATUS_COLOR = {
    'PEAK': PALETTE['peak'],
    'NORMAL': PALETTE['normal'],
    'LOW': PALETTE['low'],
}


def fig_to_base64(fig) -> str:
    """Convert matplotlib figure to base64 PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=110,
                facecolor=PALETTE['bg'], edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def chart_forecast_line(forecast_data: dict) -> str:
    """
    Monthly forecast line chart for a single material.
    Shows historical (last 12 months) + 12-month forecast.
    """
    historical = np.array(forecast_data.get('historical_series', []))[-12:]
    forecast_12 = np.array(forecast_data.get('forecast_12', []))
    material = forecast_data.get('material_code', '')
    desc = forecast_data.get('description', '')[:35]
    status = forecast_data.get('forecast_status', 'NORMAL')

    fig, ax = plt.subplots(figsize=(9, 4), facecolor=PALETTE['bg'])
    ax.set_facecolor(PALETTE['bg'])

    n_hist = len(historical)
    x_hist = np.arange(n_hist)
    x_fore = np.arange(n_hist, n_hist + len(forecast_12))

    ax.plot(x_hist, historical, color=PALETTE['neutral'], linewidth=2,
            marker='o', markersize=4, label='Historical (12 mo)', zorder=3)
    ax.plot(x_fore, forecast_12, color=STATUS_COLOR.get(status, PALETTE['primary']),
            linewidth=2.5, marker='s', markersize=4, linestyle='--',
            label=f'Forecast – {status}', zorder=3)

    # Confidence band
    std = np.std(historical) if len(historical) > 1 else 0
    ax.fill_between(x_fore,
                    np.clip(forecast_12 - std, 0, None),
                    forecast_12 + std,
                    alpha=0.18, color=STATUS_COLOR.get(status, PALETTE['primary']))

    ax.axvline(x=n_hist - 0.5, color='#94A3B8', linestyle=':', linewidth=1.2)
    ax.set_title(f'{material} – {desc}', fontsize=11, fontweight='bold', color='#1E293B', pad=10)
    ax.set_xlabel('Month Index', fontsize=9, color='#475569')
    ax.set_ylabel('Quantity', fontsize=9, color='#475569')
    ax.legend(fontsize=8, framealpha=0.85)
    ax.grid(axis='y', color='#E2E8F0', linewidth=0.8, linestyle='--')
    ax.spines[['top', 'right']].set_visible(False)

    plt.tight_layout()
    return fig_to_base64(fig)


def chart_demand_overview(forecasts: List[dict], top_n: int = 10) -> str:
    """
    Horizontal bar chart: top N materials by next-quarter demand.
    Color-coded by forecast status.
    """
    top = sorted(forecasts, key=lambda x: x.get('next_quarter_qty', 0), reverse=True)[:top_n]
    if not top:
        return ''

    labels = [f"{f['material_code']}" for f in top]
    values = [f.get('next_quarter_qty', 0) for f in top]
    colors = [STATUS_COLOR.get(f.get('forecast_status', 'NORMAL'), PALETTE['primary']) for f in top]

    fig, ax = plt.subplots(figsize=(9, max(4, len(top) * 0.55)), facecolor=PALETTE['bg'])
    ax.set_facecolor(PALETTE['bg'])

    bars = ax.barh(labels[::-1], values[::-1], color=colors[::-1], height=0.65, zorder=3)
    for bar, val in zip(bars, values[::-1]):
        ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                f'{val:,.0f}', va='center', fontsize=8, color='#374151')

    legend_patches = [
        mpatches.Patch(color=PALETTE['peak'], label='PEAK'),
        mpatches.Patch(color=PALETTE['normal'], label='NORMAL'),
        mpatches.Patch(color=PALETTE['low'], label='LOW'),
    ]
    ax.legend(handles=legend_patches, fontsize=8, loc='lower right', framealpha=0.85)
    ax.set_title(f'Top {top_n} Materials – Next Quarter Forecast (Qty)', fontsize=11,
                 fontweight='bold', color='#1E293B', pad=10)
    ax.set_xlabel('Forecasted Quantity', fontsize=9, color='#475569')
    ax.grid(axis='x', color='#E2E8F0', linewidth=0.8, linestyle='--', zorder=0)
    ax.spines[['top', 'right']].set_visible(False)

    plt.tight_layout()
    return fig_to_base64(fig)


def chart_status_donut(summary: dict) -> str:
    """Donut chart for PEAK / NORMAL / LOW distribution."""
    peak = summary.get('peak_count', 0)
    normal = summary.get('normal_count', 0)
    low = summary.get('low_count', 0)

    values = [peak, normal, low]
    labels = ['PEAK', 'NORMAL', 'LOW']
    colors = [PALETTE['peak'], PALETTE['normal'], PALETTE['low']]

    # Remove zero slices
    filtered = [(v, l, c) for v, l, c in zip(values, labels, colors) if v > 0]
    if not filtered:
        return ''
    values, labels, colors = zip(*filtered)

    fig, ax = plt.subplots(figsize=(5, 4), facecolor=PALETTE['bg'])
    ax.set_facecolor(PALETTE['bg'])

    wedges, texts, autotexts = ax.pie(
        values, labels=labels, colors=colors,
        autopct='%1.0f%%', startangle=90,
        wedgeprops=dict(width=0.55, edgecolor='white', linewidth=2),
        textprops={'fontsize': 9},
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_color('white')
        at.set_fontweight('bold')

    ax.set_title('Forecast Status Distribution', fontsize=11, fontweight='bold',
                 color='#1E293B', pad=10)
    plt.tight_layout()
    return fig_to_base64(fig)


def chart_procurement_trend(forecasts: List[dict], top_n: int = 8) -> str:
    """
    Stacked monthly procurement cost chart for top materials.
    """
    top = sorted(forecasts, key=lambda x: x.get('next_year_cost', 0), reverse=True)[:top_n]
    if not top:
        return ''

    months = [f['month'] for f in top[0].get('monthly_forecast', [])]
    if not months:
        return ''

    fig, ax = plt.subplots(figsize=(10, 4.5), facecolor=PALETTE['bg'])
    ax.set_facecolor(PALETTE['bg'])

    cmap = plt.cm.get_cmap('tab10', len(top))
    bottoms = np.zeros(len(months))
    x = np.arange(len(months))

    for i, mat in enumerate(top):
        costs = [m['forecast_cost'] for m in mat.get('monthly_forecast', [])]
        if len(costs) == len(months):
            ax.bar(x, costs, bottom=bottoms, label=mat['material_code'],
                   color=cmap(i), zorder=3, alpha=0.88)
            bottoms += np.array(costs)

    ax.set_xticks(x)
    ax.set_xticklabels(months, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('Procurement Cost (₹)', fontsize=9, color='#475569')
    ax.set_title('Monthly Procurement Cost Forecast (Top Materials)', fontsize=11,
                 fontweight='bold', color='#1E293B', pad=10)
    ax.legend(fontsize=7, loc='upper left', framealpha=0.85, ncol=2)
    ax.grid(axis='y', color='#E2E8F0', linewidth=0.8, linestyle='--', zorder=0)
    ax.spines[['top', 'right']].set_visible(False)

    plt.tight_layout()
    return fig_to_base64(fig)


def chart_model_comparison(forecasts: List[dict]) -> str:
    """Compare RMSE of Linear vs Holt across materials."""
    items = [f for f in forecasts if f.get('lr_metrics') and f.get('holt_metrics')][:15]
    if not items:
        return ''

    labels = [f['material_code'] for f in items]
    lr_rmse = [f['lr_metrics']['rmse'] for f in items]
    holt_rmse = [f['holt_metrics']['rmse'] for f in items]

    x = np.arange(len(labels))
    w = 0.38

    fig, ax = plt.subplots(figsize=(10, 4), facecolor=PALETTE['bg'])
    ax.set_facecolor(PALETTE['bg'])

    ax.bar(x - w / 2, lr_rmse, w, label='Linear Regression RMSE',
           color=PALETTE['primary'], alpha=0.85, zorder=3)
    ax.bar(x + w / 2, holt_rmse, w, label="Holt's Exp. Smoothing RMSE",
           color=PALETTE['secondary'], alpha=0.85, zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('RMSE', fontsize=9, color='#475569')
    ax.set_title('Model Comparison – RMSE by Material', fontsize=11,
                 fontweight='bold', color='#1E293B', pad=10)
    ax.legend(fontsize=9, framealpha=0.85)
    ax.grid(axis='y', color='#E2E8F0', linewidth=0.8, linestyle='--', zorder=0)
    ax.spines[['top', 'right']].set_visible(False)

    plt.tight_layout()
    return fig_to_base64(fig)


def generate_all_charts(forecast_result: dict) -> dict:
    """Generate all dashboard charts. Returns dict of base64 images."""
    forecasts = forecast_result.get('forecasts', [])
    summary = forecast_result.get('summary', {})

    charts = {}

    charts['demand_overview'] = chart_demand_overview(forecasts)
    charts['status_donut'] = chart_status_donut(summary)
    charts['procurement_trend'] = chart_procurement_trend(forecasts)
    charts['model_comparison'] = chart_model_comparison(forecasts)

    # Individual forecast charts for top 5 materials
    top5 = sorted(forecasts, key=lambda x: x.get('next_quarter_cost', 0), reverse=True)[:5]
    charts['individual'] = []
    for mat in top5:
        img = chart_forecast_line(mat)
        charts['individual'].append({
            'material_code': mat['material_code'],
            'description': mat.get('description', ''),
            'image': img,
        })

    return charts
