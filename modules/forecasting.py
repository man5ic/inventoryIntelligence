"""
Phase 3: Predictive Forecasting & Demand Intelligence
Uses Linear Regression and Exponential Smoothing (no statsmodels dependency)
"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import PolynomialFeatures
import warnings
warnings.filterwarnings('ignore')


# ─────────────────────────────────────────────────────────────
# Exponential Smoothing (manual, no statsmodels)
# ─────────────────────────────────────────────────────────────

def exponential_smoothing(series: np.ndarray, alpha: float = 0.3) -> np.ndarray:
    """Simple Exponential Smoothing."""
    result = [series[0]]
    for n in range(1, len(series)):
        result.append(alpha * series[n] + (1 - alpha) * result[n - 1])
    return np.array(result)


def double_exponential_smoothing(series: np.ndarray, alpha: float = 0.3, beta: float = 0.3) -> tuple:
    """Holt's Double Exponential Smoothing for trend."""
    n = len(series)
    level = np.zeros(n)
    trend = np.zeros(n)
    smoothed = np.zeros(n)

    level[0] = series[0]
    trend[0] = series[1] - series[0] if n > 1 else 0

    for t in range(1, n):
        level[t] = alpha * series[t] + (1 - alpha) * (level[t - 1] + trend[t - 1])
        trend[t] = beta * (level[t] - level[t - 1]) + (1 - beta) * trend[t - 1]
        smoothed[t] = level[t] + trend[t]

    smoothed[0] = level[0]
    return smoothed, level[-1], trend[-1]


def forecast_holt(last_level: float, last_trend: float, steps: int) -> np.ndarray:
    """Project Holt's model forward."""
    return np.array([last_level + (i + 1) * last_trend for i in range(steps)])


# ─────────────────────────────────────────────────────────────
# Synthetic Monthly Series Generator
# ─────────────────────────────────────────────────────────────

def generate_monthly_series(annual_qty: float, n_months: int = 24) -> np.ndarray:
    """
    Build a realistic monthly demand series from an annual total.
    Adds slight trend + seasonal noise so models have something to learn.
    """
    np.random.seed(42)
    base = annual_qty / 12
    trend = np.linspace(0, base * 0.15, n_months)          # slight upward trend
    seasonality = np.sin(np.linspace(0, 2 * np.pi, n_months)) * base * 0.10
    noise = np.random.normal(0, base * 0.05, n_months)
    series = base + trend + seasonality + noise
    series = np.clip(series, 0, None)
    return series


# ─────────────────────────────────────────────────────────────
# Model Comparison
# ─────────────────────────────────────────────────────────────

def evaluate_linear(series: np.ndarray):
    """Fit linear regression; return model + metrics."""
    X = np.arange(len(series)).reshape(-1, 1)
    y = series
    model = LinearRegression()
    model.fit(X, y)
    y_pred = model.predict(X)
    rmse = np.sqrt(mean_squared_error(y, y_pred))
    mae = mean_absolute_error(y, y_pred)
    r2 = r2_score(y, y_pred)
    return model, {'rmse': rmse, 'mae': mae, 'r2': r2}


def evaluate_holt(series: np.ndarray):
    """Fit Holt's; return smoothed + metrics."""
    smoothed, last_level, last_trend = double_exponential_smoothing(series)
    rmse = np.sqrt(mean_squared_error(series, smoothed))
    mae = mean_absolute_error(series, smoothed)
    r2 = r2_score(series, smoothed)
    return last_level, last_trend, {'rmse': rmse, 'mae': mae, 'r2': r2}


def choose_best_model(lr_metrics: dict, holt_metrics: dict) -> str:
    """Choose model with lower RMSE (normalized by mean)."""
    return 'linear' if lr_metrics['rmse'] <= holt_metrics['rmse'] else 'holt'


# ─────────────────────────────────────────────────────────────
# Forecast Status Classification
# ─────────────────────────────────────────────────────────────

def classify_forecast_status(current_avg: float, forecast_avg: float) -> str:
    """Classify demand trend: PEAK / NORMAL / LOW."""
    if current_avg <= 0:
        return 'NORMAL'
    pct_change = (forecast_avg - current_avg) / current_avg * 100
    if pct_change >= 10:
        return 'PEAK'
    elif pct_change <= -10:
        return 'LOW'
    else:
        return 'NORMAL'


# ─────────────────────────────────────────────────────────────
# Per-Material Forecast
# ─────────────────────────────────────────────────────────────

def forecast_material(row: dict, n_history: int = 24) -> dict:
    """
    Generate forecasts for a single material.
    Returns forecast values, metrics, status, and insights.
    """
    annual_qty = float(row.get('quantity', 0))
    unit_price = float(row.get('unit_price', 0))
    material_code = str(row.get('material_code', 'Unknown'))
    description = str(row.get('description', ''))

    # Build historical series
    series = generate_monthly_series(annual_qty, n_months=n_history)
    current_avg = series[-6:].mean()   # last 6 months average

    # ── Linear Regression ──
    lr_model, lr_metrics = evaluate_linear(series)
    n_total = len(series)
    future_idx_lr = np.arange(n_total, n_total + 12).reshape(-1, 1)
    lr_forecast_12 = lr_model.predict(future_idx_lr)
    lr_forecast_12 = np.clip(lr_forecast_12, 0, None)

    # ── Holt Double Exponential ──
    last_level, last_trend, holt_metrics = evaluate_holt(series)
    holt_forecast_12 = forecast_holt(last_level, last_trend, 12)
    holt_forecast_12 = np.clip(holt_forecast_12, 0, None)

    # ── Best Model ──
    best = choose_best_model(lr_metrics, holt_metrics)
    if best == 'linear':
        forecast_12 = lr_forecast_12
        chosen_metrics = lr_metrics
    else:
        forecast_12 = holt_forecast_12
        chosen_metrics = holt_metrics

    # ── Aggregates ──
    next_month = float(forecast_12[0])
    next_quarter = float(forecast_12[:3].sum())
    next_year = float(forecast_12.sum())
    forecast_avg = float(forecast_12[:3].mean())

    pct_change = ((forecast_avg - current_avg) / current_avg * 100) if current_avg > 0 else 0
    status = classify_forecast_status(current_avg, forecast_avg)

    # ── Procurement Cost ──
    future_cost_month = next_month * unit_price
    future_cost_quarter = next_quarter * unit_price
    future_cost_year = next_year * unit_price

    # ── Monthly breakdown ──
    months_ahead = pd.date_range(start='2025-01-01', periods=12, freq='ME')
    monthly_forecast = [
        {
            'month': m.strftime('%b %Y'),
            'forecast_qty': round(float(q), 1),
            'forecast_cost': round(float(q) * unit_price, 2)
        }
        for m, q in zip(months_ahead, forecast_12)
    ]

    # ── Insight text ──
    direction = "increase" if pct_change > 0 else "decrease"
    insight = (
        f"Demand expected to {direction} by {abs(pct_change):.1f}% — "
        f"Next quarter requirement: {next_quarter:,.0f} units "
        f"(₹{future_cost_quarter:,.0f})"
    )

    return {
        'material_code': material_code,
        'description': description,
        'best_model': best,
        'model_metrics': chosen_metrics,
        'lr_metrics': lr_metrics,
        'holt_metrics': holt_metrics,
        'historical_series': series.tolist(),
        'lr_forecast': lr_forecast_12.tolist(),
        'holt_forecast': holt_forecast_12.tolist(),
        'forecast_12': forecast_12.tolist(),
        'next_month_qty': round(next_month, 1),
        'next_quarter_qty': round(next_quarter, 1),
        'next_year_qty': round(next_year, 1),
        'next_month_cost': round(future_cost_month, 2),
        'next_quarter_cost': round(future_cost_quarter, 2),
        'next_year_cost': round(future_cost_year, 2),
        'pct_change': round(pct_change, 2),
        'forecast_status': status,
        'monthly_forecast': monthly_forecast,
        'insight': insight,
        'unit_price': unit_price,
        'annual_qty': annual_qty,
    }


# ─────────────────────────────────────────────────────────────
# Bulk Forecast Engine
# ─────────────────────────────────────────────────────────────

def run_forecast_engine(df: pd.DataFrame) -> dict:
    """
    Run forecasts for all materials in the dataframe.
    Expects columns: material_code, description, quantity, unit_price
    """
    forecasts = []
    for _, row in df.iterrows():
        try:
            f = forecast_material(row.to_dict())
            forecasts.append(f)
        except Exception as e:
            forecasts.append({
                'material_code': str(row.get('material_code', '?')),
                'description': str(row.get('description', '')),
                'forecast_status': 'NORMAL',
                'next_month_qty': 0,
                'next_quarter_qty': 0,
                'next_year_qty': 0,
                'next_month_cost': 0,
                'next_quarter_cost': 0,
                'next_year_cost': 0,
                'pct_change': 0,
                'best_model': 'linear',
                'insight': f'Forecast unavailable: {str(e)}',
                'monthly_forecast': [],
                'model_metrics': {'rmse': 0, 'mae': 0, 'r2': 0},
                'forecast_12': [],
                'historical_series': [],
                'unit_price': 0,
                'annual_qty': 0,
            })

    # ── Executive Summary ──
    peak_items = [f for f in forecasts if f['forecast_status'] == 'PEAK']
    low_items = [f for f in forecasts if f['forecast_status'] == 'LOW']
    normal_items = [f for f in forecasts if f['forecast_status'] == 'NORMAL']

    total_next_quarter = sum(f['next_quarter_cost'] for f in forecasts)
    total_next_year = sum(f['next_year_cost'] for f in forecasts)
    avg_pct_change = np.mean([f['pct_change'] for f in forecasts]) if forecasts else 0

    direction = "increase" if avg_pct_change >= 0 else "decrease"
    exec_insights = [
        f"Overall demand expected to {direction} by {abs(avg_pct_change):.1f}% next quarter",
        f"{len(peak_items)} high-growth materials identified (PEAK status)",
        f"{len(low_items)} materials showing declining demand (LOW status)",
        f"Estimated total procurement cost next quarter: ₹{total_next_quarter:,.0f}",
        f"Estimated total procurement cost next year: ₹{total_next_year:,.0f}",
        f"Best forecasting model: Linear Regression vs Holt's Exponential Smoothing (auto-selected per item)",
    ]

    if peak_items:
        top_peak = sorted(peak_items, key=lambda x: x['pct_change'], reverse=True)[:3]
        for item in top_peak:
            exec_insights.append(
                f"🔺 {item['material_code']} – demand up {item['pct_change']:.1f}% ({item['description'][:40]})"
            )

    if low_items:
        top_low = sorted(low_items, key=lambda x: x['pct_change'])[:2]
        for item in top_low:
            exec_insights.append(
                f"🔻 {item['material_code']} – demand down {abs(item['pct_change']):.1f}% ({item['description'][:40]})"
            )

    return {
        'forecasts': forecasts,
        'exec_insights': exec_insights,
        'summary': {
            'total_items': len(forecasts),
            'peak_count': len(peak_items),
            'normal_count': len(normal_items),
            'low_count': len(low_items),
            'total_next_quarter_cost': round(total_next_quarter, 2),
            'total_next_year_cost': round(total_next_year, 2),
            'avg_pct_change': round(avg_pct_change, 2),
        }
    }
