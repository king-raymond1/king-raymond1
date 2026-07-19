"""
Order analysis: order trends, monthly orders, average order value, order frequency, large/small orders,
cancelled orders (if available), order status distribution, and visualizations.

Usage:
    python scripts/order_analysis.py --input-dir data/processed_data --output-dir visualizations --large_pct 0.90 --small_pct 0.10

Outputs (written to output-dir and analysis/):
- analysis/orders_summary.csv
- analysis/monthly_orders.csv
- analysis/daily_orders.csv
- analysis/large_orders.csv
- analysis/small_orders.csv
- analysis/order_status_distribution.csv
- visualizations/figures/monthly_orders.png
- visualizations/figures/daily_orders.png
- visualizations/figures/aov_by_month.png
- visualizations/figures/order_size_distribution.png
- visualizations/figures/order_status_distribution.png
- documentation/order_analysis_report.md

Notes:
- Script prefers transformed_orders.csv; falls back to cleaned_orders.csv if not present.
- If order status or cancellation fields are not present, the report notes it.
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def safe_read(path: Path, parse_dates=None):
    if not path.exists():
        logger.warning('File not found: %s', path)
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=parse_dates, infer_datetime_format=True)


def save_fig(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info('Saved %s', path)


def main(input_dir: str, output_dir: str, large_pct: float, small_pct: float):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    figs = output_dir / 'figures'
    analysis_dir = output_dir.parent / 'analysis'
    figs.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)

    orders_path = input_dir / 'transformed_orders.csv'
    if not orders_path.exists():
        orders_path = input_dir / 'cleaned_orders.csv'

    orders = safe_read(orders_path, parse_dates=['order_date'])
    if orders.empty:
        logger.error('No orders file found. Place cleaned_orders.csv or transformed_orders.csv in data/processed_data')
        return

    # ensure date
    if 'order_date' in orders.columns:
        orders['order_date'] = pd.to_datetime(orders['order_date'], errors='coerce')
    else:
        # try transaction_date fallback
        if 'transaction_date' in orders.columns:
            orders['order_date'] = pd.to_datetime(orders['transaction_date'], errors='coerce')

    # Basic metrics
    total_revenue = orders['total_amount'].sum() if 'total_amount' in orders.columns else 0
    total_orders = orders['order_id'].nunique() if 'order_id' in orders.columns else len(orders)
    unique_customers = orders['customer_id'].nunique() if 'customer_id' in orders.columns else orders['customer_id'].nunique() if 'customer_id' in orders.columns else 0
    aov = total_revenue / total_orders if total_orders>0 else np.nan

    # Order size (quantity) distribution
    if 'quantity' in orders.columns:
        orders['order_size'] = orders['quantity']
    else:
        # if orders may be aggregated, try to infer from items_count
        orders['order_size'] = orders.get('items_count', 1)

    # Daily and monthly aggregations
    orders['date'] = orders['order_date'].dt.date
    orders['month'] = orders['order_date'].dt.to_period('M').dt.to_timestamp()

    daily = orders.groupby('date').agg(orders_count=('order_id','count') if 'order_id' in orders.columns else ('date','count'), revenue=('total_amount','sum')).reset_index()
    monthly = orders.groupby('month').agg(orders_count=('order_id','count') if 'order_id' in orders.columns else ('month','count'), revenue=('total_amount','sum')).reset_index()
    monthly['aov'] = monthly.apply(lambda r: r['revenue']/r['orders_count'] if r['orders_count']>0 else 0, axis=1)

    # Order frequency per customer
    freq = None
    if 'customer_id' in orders.columns:
        freq = orders.groupby('customer_id').agg(order_count=('order_id','nunique') if 'order_id' in orders.columns else ('order_date','count'), revenue=('total_amount','sum')).reset_index()
        freq['avg_order_value'] = freq.apply(lambda r: r['revenue']/r['order_count'] if r['order_count']>0 else 0, axis=1)
        freq_sorted = freq.sort_values('order_count', ascending=False)
        freq.to_csv(analysis_dir / 'order_frequency_per_customer.csv', index=False)

    # Large / small orders by percentile thresholds
    if 'total_amount' in orders.columns:
        large_threshold = orders['total_amount'].quantile(large_pct)
        small_threshold = orders['total_amount'].quantile(small_pct)
        large_orders = orders[orders['total_amount'] >= large_threshold].sort_values('total_amount', ascending=False)
        small_orders = orders[orders['total_amount'] <= small_threshold].sort_values('total_amount', ascending=True)
        large_orders.to_csv(analysis_dir / 'large_orders.csv', index=False)
        small_orders.to_csv(analysis_dir / 'small_orders.csv', index=False)
    else:
        large_orders = pd.DataFrame()
        small_orders = pd.DataFrame()

    # Cancelled orders and status distribution
    status_dist = pd.DataFrame()
    if 'order_status' in orders.columns:
        status_dist = orders['order_status'].value_counts().reset_index()
        status_dist.columns = ['order_status','count']
        status_dist.to_csv(analysis_dir / 'order_status_distribution.csv', index=False)
        if 'cancel' in status_dist['order_status'].str.lower().tolist() or 'cancelled' in status_dist['order_status'].str.lower().tolist() or 'canceled' in status_dist['order_status'].str.lower().tolist():
            cancelled = orders[orders['order_status'].str.lower().isin(['cancel','cancelled','canceled'])]
            cancelled.to_csv(analysis_dir / 'cancelled_orders.csv', index=False)
        else:
            cancelled = pd.DataFrame()
    else:
        # also check for boolean cancelled or canceled column
        if 'cancelled' in orders.columns or 'canceled' in orders.columns:
            col = 'cancelled' if 'cancelled' in orders.columns else 'canceled'
            cancelled = orders[orders[col].astype(str).str.lower().isin(['true','1', 'yes'])]
            cancelled.to_csv(analysis_dir / 'cancelled_orders.csv', index=False)
            status_dist = pd.DataFrame({'order_status':['cancelled','other'],'count':[len(cancelled), len(orders)-len(cancelled)]})
            status_dist.to_csv(analysis_dir / 'order_status_distribution.csv', index=False)
        else:
            cancelled = pd.DataFrame()
            status_dist = pd.DataFrame({'note':['order_status column not present']})
            status_dist.to_csv(analysis_dir / 'order_status_distribution.csv', index=False)

    # Order size distribution (quantity)
    order_size_stats = orders['order_size'].describe().to_frame().reset_index().rename(columns={'index':'stat', 'order_size':'value'})
    order_size_stats.to_csv(analysis_dir / 'order_size_stats.csv', index=False)

    # Save monthly & daily
    monthly.to_csv(analysis_dir / 'monthly_orders.csv', index=False)
    daily.to_csv(analysis_dir / 'daily_orders.csv', index=False)

    # Visualizations
    # Monthly orders
    if not monthly.empty:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.plot(monthly['month'], monthly['orders_count'], marker='o')
        ax.set_title('Monthly Orders')
        ax.set_xlabel('Month')
        ax.set_ylabel('Number of Orders')
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'monthly_orders.png')

    # Daily orders
    if not daily.empty:
        fig, ax = plt.subplots(figsize=(12,6))
        ax.plot(daily['date'], daily['orders_count'], marker='o')
        ax.set_title('Daily Orders')
        ax.set_xlabel('Date')
        ax.set_ylabel('Number of Orders')
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'daily_orders.png')

    # AOV by month
    if not monthly.empty:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.bar(monthly['month'].astype(str), monthly['aov'], color='tab:blue')
        ax.set_title('Average Order Value (AOV) by Month')
        ax.set_xlabel('Month')
        ax.set_ylabel('AOV')
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'aov_by_month.png')

    # Order size distribution
    if 'order_size' in orders.columns:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.hist(orders['order_size'].dropna(), bins=20, color='tab:purple')
        ax.set_title('Order Size Distribution (quantity per order)')
        ax.set_xlabel('Quantity')
        ax.set_ylabel('Number of Orders')
        save_fig(fig, figs / 'order_size_distribution.png')

    # Order status distribution
    if not status_dist.empty:
        fig, ax = plt.subplots(figsize=(8,5))
        ax.pie(status_dist['count'], labels=status_dist.iloc[:,0].astype(str), autopct='%1.1f%%')
        ax.set_title('Order Status Distribution')
        save_fig(fig, figs / 'order_status_distribution.png')

    # Save summary
    summary = {
        'total_revenue': float(total_revenue),
        'total_orders': int(total_orders),
        'unique_customers': int(unique_customers) if hasattr(unique_customers, '__int__') else int(orders['customer_id'].nunique()) if 'customer_id' in orders.columns else 0,
        'aov': float(aov)
    }
    pd.DataFrame([summary]).to_csv(analysis_dir / 'orders_summary.csv', index=False)

    # Save large/small orders counts
    counts = {
        'large_orders_count': int(len(large_orders)) if not large_orders.empty else 0,
        'small_orders_count': int(len(small_orders)) if not small_orders.empty else 0,
        'cancelled_orders_count': int(len(cancelled)) if cancelled is not None and not cancelled.empty else 0
    }
    pd.DataFrame([counts]).to_csv(analysis_dir / 'orders_counts_breakdown.csv', index=False)

    # Write report
    report = []
    report.append('# Order Analysis Report')
    report.append('\nThis report analyzes order trends, frequency, large/small orders, cancellations, and status distribution. Outputs are saved under analysis/ and visualizations/figures/.')
    report.append('\n## Summary metrics')
    report.append(f'- Total revenue: ${summary["total_revenue"]:.2f}')
    report.append(f'- Total orders: {summary["total_orders"]}')
    report.append(f'- Unique customers: {summary["unique_customers"]}')
    report.append(f'- Average Order Value (AOV): ${summary["aov"]:.2f}')
    report.append('\n## Large and small orders')
    report.append(f'- Large orders threshold (>= {large_pct*100:.0f}th percentile): ${large_threshold:.2f}' if 'large_threshold' in locals() else '- Not computed')
    report.append(f'- Small orders threshold (<= {small_pct*100:.0f}th percentile): ${small_threshold:.2f}' if 'small_threshold' in locals() else '- Not computed')
    report.append(f'- Large orders count: {counts["large_orders_count"]}')
    report.append(f'- Small orders count: {counts["small_orders_count"]}')
    report.append(f'- Cancelled orders count: {counts["cancelled_orders_count"]}')
    report.append('\n## Files produced')
    report.append('- analysis/monthly_orders.csv')
    report.append('- analysis/daily_orders.csv')
    report.append('- analysis/orders_summary.csv')
    report.append('- visualizations/figures/monthly_orders.png')
    report.append('- visualizations/figures/daily_orders.png')
    report.append('- visualizations/figures/aov_by_month.png')
    report.append('- visualizations/figures/order_size_distribution.png')
    report.append('- visualizations/figures/order_status_distribution.png')

    (output_dir.parent / 'documentation').mkdir(parents=True, exist_ok=True)
    (output_dir.parent / 'documentation' / 'order_analysis_report.md').write_text('\n'.join(report))

    logger.info('Order analysis complete. Outputs written to %s and %s', analysis_dir, figs)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str, default='data/processed_data')
    parser.add_argument('--output-dir', type=str, default='visualizations')
    parser.add_argument('--large_pct', type=float, default=0.90)
    parser.add_argument('--small_pct', type=float, default=0.10)
    args = parser.parse_args()
    main(args.input_dir, args.output_dir, args.large_pct, args.small_pct)
