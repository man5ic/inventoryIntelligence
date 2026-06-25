"""
Phase 7: Region / Plant Filter + Month / Time Period Filter
Extends existing intelligence pipeline with dynamic dataset filtering.
All computations reuse existing modules — this layer only slices the data.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

PLANT_COL   = 'plant'
REGION_COL  = 'region'
MONTH_COL   = 'month'      # expected format: 'YYYY-MM' or month number
YEAR_COL    = 'year'

PLANTS_KEY  = 'plant'      # column_map key for plant
REGION_KEY  = 'region'     # column_map key for region

ALL_OPTION  = '__all__'


# ─────────────────────────────────────────────────────────────
# Discover filter options from dataset
# ─────────────────────────────────────────────────────────────

def get_filter_options(df: pd.DataFrame, column_map: dict) -> dict:
    """
    Scan the dataset and return available plants, regions, and time periods.
    Works with both mapped column names and raw column names.
    Returns dict with keys: plants, regions, months, years, has_plant, has_region, has_time.
    """
    options = {
        'plants':     [],
        'regions':    [],
        'months':     [],
        'years':      [],
        'has_plant':  False,
        'has_region': False,
        'has_time':   False,
    }

    if df.empty:
        return options

    # Build reverse map: raw_col → logical_key
    rev_map = {v: k for k, v in column_map.items() if v}

    # Normalise column names (lowercase, strip)
    col_lower = {c: c.lower().strip() for c in df.columns}

    # Columns already claimed by the column_map (don't reuse them for plant/region)
    claimed_cols = set(v for v in column_map.values() if v)

    def _find_col(logical_key: str, aliases: list) -> Optional[str]:
        """Find first matching column by logical key or alias."""
        # 1. Check column_map explicit mapping
        mapped = column_map.get(logical_key, '')
        if mapped and mapped in df.columns:
            return mapped
        # 2. Fuzzy alias match — skip columns already mapped to core fields,
        #    and skip columns whose values look purely numeric (prices, quantities)
        for alias in aliases:
            for raw, low in col_lower.items():
                if raw in claimed_cols:
                    continue
                if alias in low:
                    # Guard: if >80% of non-null values are numeric, skip
                    col_vals = df[raw].dropna()
                    if len(col_vals) > 0:
                        num_count = pd.to_numeric(col_vals, errors='coerce').notna().sum()
                        if num_count / len(col_vals) > 0.8:
                            continue
                    return raw
        return None

    plant_col  = _find_col('plant',  ['plant', 'location', 'site', 'facility'])
    region_col = _find_col('region', ['region', 'zone', 'area', 'territory', 'division'])
    month_col  = _find_col('month',  ['month', 'period', 'mnth'])
    year_col   = _find_col('year',   ['year', 'yr', 'fy'])
    date_col   = _find_col('date',   ['date', 'transaction_date', 'posting_date', 'doc_date'])

    # Plants
    if plant_col:
        vals = df[plant_col].dropna().astype(str).str.strip()
        vals = sorted(set(v for v in vals if v and v.lower() not in ('nan', 'none', '')))
        options['plants']    = vals
        options['has_plant'] = bool(vals)
        options['_plant_col'] = plant_col

    # Regions
    if region_col:
        vals = df[region_col].dropna().astype(str).str.strip()
        vals = sorted(set(v for v in vals if v and v.lower() not in ('nan', 'none', '')))
        options['regions']    = vals
        options['has_region'] = bool(vals)
        options['_region_col'] = region_col

    # Time periods — try dedicated month/year cols, then parse date col
    months_found = []
    years_found  = []

    if date_col:
        try:
            dates = pd.to_datetime(df[date_col], errors='coerce').dropna()
            months_found = sorted(set(dates.dt.to_period('M').astype(str).tolist()))
            years_found  = sorted(set(dates.dt.year.astype(str).tolist()))
        except Exception:
            pass
    elif month_col and year_col:
        try:
            m = df[month_col].dropna().astype(int)
            y = df[year_col].dropna().astype(int)
            # combine
            combined = (y.astype(str) + '-' + m.astype(str).str.zfill(2)).unique()
            months_found = sorted(set(combined))
            years_found  = sorted(set(y.astype(str).tolist()))
        except Exception:
            pass
    elif month_col:
        try:
            vals = df[month_col].dropna().astype(str).unique()
            months_found = sorted(vals)
        except Exception:
            pass

    # If no real time columns, generate synthetic months from a default year
    # (so month filter always works even for basic datasets)
    if not months_found:
        base_year = datetime.now().year
        months_found = [f"{base_year}-{str(m).zfill(2)}" for m in range(1, 13)]
        # Add previous year too
        prev_year = base_year - 1
        months_found = [f"{prev_year}-{str(m).zfill(2)}" for m in range(1, 13)] + months_found
        years_found  = [str(prev_year), str(base_year)]

    options['months']   = months_found
    options['years']    = years_found
    options['has_time'] = True

    # Format months as human-readable labels
    options['month_labels'] = _format_month_labels(months_found)

    return options


def _format_month_labels(months: list) -> list:
    """Convert YYYY-MM strings to human-readable labels like 'Jan 2026'."""
    labels = []
    for m in months:
        try:
            dt = datetime.strptime(m, '%Y-%m')
            labels.append({'value': m, 'label': dt.strftime('%b %Y')})
        except Exception:
            labels.append({'value': m, 'label': m})
    return labels


def get_quarter_options(years: list) -> list:
    """Generate quarter options like Q1 2026."""
    quarters = []
    for y in sorted(years):
        for q in range(1, 5):
            quarters.append({'value': f"Q{q}-{y}", 'label': f"Q{q} {y}"})
    return quarters


# ─────────────────────────────────────────────────────────────
# Apply filters to raw DataFrame
# ─────────────────────────────────────────────────────────────

def apply_filters(df: pd.DataFrame, column_map: dict,
                  plant: str = ALL_OPTION,
                  region: str = ALL_OPTION,
                  period: str = ALL_OPTION) -> pd.DataFrame:
    """
    Apply plant/region and time-period filters to the raw DataFrame.
    Returns a filtered copy. Falls back gracefully if columns are absent.
    Synthetic month filtering: splits annual quantities proportionally per month.
    """
    if df.empty:
        return df

    filtered = df.copy()
    options  = get_filter_options(df, column_map)

    # ── Plant filter ──
    plant_col = options.get('_plant_col')
    if plant and plant != ALL_OPTION and plant_col and plant_col in filtered.columns:
        filtered = filtered[filtered[plant_col].astype(str).str.strip() == plant]

    # ── Region filter ──
    region_col = options.get('_region_col')
    if region and region != ALL_OPTION and region_col and region_col in filtered.columns:
        filtered = filtered[filtered[region_col].astype(str).str.strip() == region]

    # ── Time / period filter ──
    filtered = _apply_period_filter(filtered, column_map, options, period)

    # Ensure we never return an empty df in a way that breaks downstream
    return filtered if not filtered.empty else df.head(0)


def _apply_period_filter(df: pd.DataFrame, column_map: dict,
                          options: dict, period: str) -> pd.DataFrame:
    """
    Apply month/quarter/year filter.
    For datasets without real date columns, scales annual quantities synthetically.
    """
    if not period or period == ALL_OPTION:
        return df

    # Determine period type
    is_quarter = period.startswith('Q') and '-' in period   # e.g. Q1-2026
    is_year    = len(period) == 4 and period.isdigit()       # e.g. 2026
    is_month   = '-' in period and not is_quarter             # e.g. 2026-03

    # Try real date column first
    date_col = None
    col_lower = {c: c.lower().strip() for c in df.columns}
    for raw, low in col_lower.items():
        if any(alias in low for alias in ['date', 'transaction_date', 'posting_date']):
            date_col = raw
            break

    if date_col:
        try:
            dates = pd.to_datetime(df[date_col], errors='coerce')
            if is_month:
                target = pd.Period(period, 'M')
                mask = dates.dt.to_period('M') == target
                return df[mask]
            elif is_quarter:
                q, y = period.split('-')
                qnum  = int(q[1])
                year  = int(y)
                target = pd.Period(f"{year}Q{qnum}", 'Q')
                mask = dates.dt.to_period('Q') == target
                return df[mask]
            elif is_year:
                mask = dates.dt.year == int(period)
                return df[mask]
        except Exception:
            pass

    # ── Synthetic scaling for annual-quantity datasets ──
    # When no date column exists, we scale the annual quantity proportionally
    qty_col = column_map.get('quantity', '')
    if not qty_col or qty_col not in df.columns:
        # Try to find a quantity column
        for c in df.columns:
            if 'quantity' in c.lower() or 'qty' in c.lower() or 'annual' in c.lower():
                qty_col = c
                break

    if not qty_col:
        return df   # can't scale, return as-is

    result = df.copy()
    qty_numeric = pd.to_numeric(result[qty_col], errors='coerce').fillna(0)

    if is_month:
        # 1 month out of 12
        scale = 1 / 12
        result[qty_col] = (qty_numeric * scale).round(2)
    elif is_quarter:
        # 3 months out of 12
        scale = 3 / 12
        result[qty_col] = (qty_numeric * scale).round(2)
    elif is_year:
        # Full year — no scaling
        pass

    return result


# ─────────────────────────────────────────────────────────────
# Build filter context for templates
# ─────────────────────────────────────────────────────────────

def build_filter_context(df: pd.DataFrame, column_map: dict,
                          selected_plant: str = ALL_OPTION,
                          selected_region: str = ALL_OPTION,
                          selected_period: str = ALL_OPTION) -> dict:
    """
    Returns the full filter context dict for template rendering.
    Includes available options + current selections + active label.
    """
    options = get_filter_options(df, column_map)

    # Quarter options
    quarter_opts = get_quarter_options(options.get('years', []))

    # Year options formatted
    year_opts = [{'value': y, 'label': f"Full Year {y}"} for y in options.get('years', [])]

    # Determine active filter label for display
    active_label = _build_active_label(selected_plant, selected_region, selected_period)

    return {
        'plants':           options.get('plants', []),
        'regions':          options.get('regions', []),
        'month_labels':     options.get('month_labels', []),
        'quarter_options':  quarter_opts,
        'year_options':     year_opts,
        'has_plant':        options.get('has_plant', False),
        'has_region':       options.get('has_region', False),
        'selected_plant':   selected_plant,
        'selected_region':  selected_region,
        'selected_period':  selected_period,
        'active_label':     active_label,
        'is_filtered':      any(x != ALL_OPTION for x in [selected_plant, selected_region, selected_period]),
    }


def _build_active_label(plant: str, region: str, period: str) -> str:
    parts = []
    if plant and plant != ALL_OPTION:
        parts.append(f"Plant: {plant}")
    if region and region != ALL_OPTION:
        parts.append(f"Region: {region}")
    if period and period != ALL_OPTION:
        # Pretty-print period
        if period.startswith('Q') and '-' in period:
            q, y = period.split('-')
            parts.append(f"{q} {y}")
        elif len(period) == 4:
            parts.append(f"Year {period}")
        else:
            try:
                dt = datetime.strptime(period, '%Y-%m')
                parts.append(dt.strftime('%b %Y'))
            except Exception:
                parts.append(period)
    return ' · '.join(parts) if parts else 'All Plants · All Regions · Full Period'


# ─────────────────────────────────────────────────────────────
# Smart Insight Generation (filter-aware)
# ─────────────────────────────────────────────────────────────

def generate_filter_insights(inv_result: dict, forecast_result: dict,
                              selected_plant: str, selected_region: str,
                              selected_period: str) -> list:
    """
    Generate contextual insights that mention the active filter selection.
    Appended to procurement insights so they appear in the Smart Insights banner.
    """
    insights = []
    inv_sum  = (inv_result or {}).get('summary', {})
    fc_sum   = (forecast_result or {}).get('summary', {})

    plant_label  = selected_plant  if selected_plant  != ALL_OPTION else None
    region_label = selected_region if selected_region != ALL_OPTION else None
    period_label = None
    if selected_period and selected_period != ALL_OPTION:
        if selected_period.startswith('Q') and '-' in selected_period:
            q, y = selected_period.split('-')
            period_label = f"{q} {y}"
        elif len(selected_period) == 4:
            period_label = f"Year {selected_period}"
        else:
            try:
                dt = datetime.strptime(selected_period, '%Y-%m')
                period_label = dt.strftime('%b %Y')
            except Exception:
                period_label = selected_period

    ctx = plant_label or region_label or ''

    total_items = inv_sum.get('total_items', 0)
    total_value = inv_sum.get('total_value', 0)
    peak_count  = fc_sum.get('peak_count', 0)
    cost_inc    = fc_sum.get('cost_increase_pct', 0)

    if ctx and total_items:
        insights.append(f"{ctx} inventory view: {total_items} materials, ₹{total_value:,.0f} total value")

    if plant_label and peak_count:
        insights.append(f"{plant_label} shows highest demand in {peak_count} materials")

    if region_label and cost_inc > 3:
        insights.append(f"Region {region_label} shows rising forecast trend (+{cost_inc:.1f}%)")

    if period_label:
        abc = inv_sum.get('abc_counts', {})
        a_ct = abc.get('A', 0)
        if a_ct:
            insights.append(f"In {period_label}: {a_ct} Class A materials require priority procurement")

    if plant_label and period_label:
        insights.append(f"Combined filter active: {plant_label} · {period_label}")

    return insights


# ─────────────────────────────────────────────────────────────
# Enhance sample dataset with Plant / Region columns
# ─────────────────────────────────────────────────────────────

def enrich_sample_with_filters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add Plant and Region columns to a basic sample dataset so filters work
    immediately when users click 'Load Sample Data'.
    """
    np.random.seed(42)
    n = len(df)
    plants  = ['Plant 1', 'Plant 2', 'Plant 3', 'Plant 4']
    regions = ['Region North', 'Region South', 'Region East', 'Region West']
    df = df.copy()
    df['Plant']  = [plants[i % len(plants)] for i in range(n)]
    df['Region'] = [regions[i % len(regions)] for i in range(n)]
    return df
