"""
Phase 1 & 2: Inventory Intelligence Module
Handles EOQ, Safety Stock, Reorder Point, ABC Classification
"""
import pandas as pd
import numpy as np
from typing import Optional


def calculate_eoq(annual_demand: float, ordering_cost: float, holding_cost: float) -> float:
    """Calculate Economic Order Quantity."""
    if holding_cost <= 0 or annual_demand <= 0 or ordering_cost <= 0:
        return 0
    return round(np.sqrt((2 * annual_demand * ordering_cost) / holding_cost), 2)


def calculate_safety_stock(demand_std: float, lead_time: float, service_level: float = 1.645) -> float:
    """Calculate Safety Stock."""
    return round(service_level * demand_std * np.sqrt(lead_time), 2)


def calculate_reorder_point(avg_demand: float, lead_time: float, safety_stock: float) -> float:
    """Calculate Reorder Point."""
    return round((avg_demand * lead_time) + safety_stock, 2)


def abc_classify(df: pd.DataFrame, value_col: str = 'annual_value') -> pd.DataFrame:
    """Classify materials using ABC analysis."""
    df = df.copy()
    df = df.sort_values(value_col, ascending=False)
    df['cumulative_pct'] = df[value_col].cumsum() / df[value_col].sum() * 100
    df['abc_class'] = df['cumulative_pct'].apply(
        lambda x: 'A' if x <= 70 else ('B' if x <= 90 else 'C')
    )
    return df


def run_inventory_intelligence(df: pd.DataFrame, column_map: dict) -> dict:
    """Run full inventory intelligence on mapped dataframe."""
    result_df = df.copy()

    # Rename columns using map
    rename = {v: k for k, v in column_map.items() if v and v in df.columns}
    result_df = result_df.rename(columns=rename)

    required = ['material_code', 'description', 'quantity', 'unit_price']
    for col in required:
        if col not in result_df.columns:
            result_df[col] = 0 if col in ['quantity', 'unit_price'] else f'Unknown_{col}'

    result_df['quantity'] = pd.to_numeric(result_df.get('quantity', 0), errors='coerce').fillna(0)
    result_df['unit_price'] = pd.to_numeric(result_df.get('unit_price', 0), errors='coerce').fillna(0)
    result_df['annual_value'] = result_df['quantity'] * result_df['unit_price']

    # EOQ, Safety Stock, ROP
    ordering_cost = 500
    holding_rate = 0.20
    lead_time = 2  # months
    service_level_z = 1.645

    result_df['avg_monthly_demand'] = result_df['quantity'] / 12
    result_df['demand_std'] = result_df['avg_monthly_demand'] * 0.2
    result_df['holding_cost'] = result_df['unit_price'] * holding_rate
    result_df['eoq'] = result_df.apply(
        lambda r: calculate_eoq(r['quantity'], ordering_cost, r['holding_cost']) if r['holding_cost'] > 0 else 0,
        axis=1
    )
    result_df['safety_stock'] = result_df.apply(
        lambda r: calculate_safety_stock(r['demand_std'], lead_time, service_level_z), axis=1
    )
    result_df['reorder_point'] = result_df.apply(
        lambda r: calculate_reorder_point(r['avg_monthly_demand'], lead_time, r['safety_stock']), axis=1
    )

    # ABC Classification
    result_df = abc_classify(result_df, 'annual_value')

    # Recommendation
    def get_recommendation(row):
        if row['abc_class'] == 'A':
            return 'High Priority – Monitor Closely'
        elif row['abc_class'] == 'B':
            return 'Medium Priority – Regular Review'
        else:
            return 'Low Priority – Periodic Check'

    result_df['recommendation'] = result_df.apply(get_recommendation, axis=1)

    # Summary stats
    total_value = result_df['annual_value'].sum()
    abc_counts = result_df['abc_class'].value_counts().to_dict()
    avg_eoq = result_df['eoq'].mean()

    insights = [
        f"Total Inventory Value: ₹{total_value:,.0f}",
        f"Class A Items: {abc_counts.get('A', 0)} items (70% of value)",
        f"Class B Items: {abc_counts.get('B', 0)} items (20% of value)",
        f"Class C Items: {abc_counts.get('C', 0)} items (10% of value)",
        f"Average EOQ: {avg_eoq:,.0f} units",
        f"Total Materials Analyzed: {len(result_df)} items",
    ]

    return {
        'data': result_df,
        'insights': insights,
        'summary': {
            'total_value': total_value,
            'total_items': len(result_df),
            'abc_counts': abc_counts,
        }
    }
