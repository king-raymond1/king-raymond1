"""
Compute business KPIs and generate visualizations.

Usage:
    python scripts/compute_kpis.py --input-dir data/processed_data --output-dir visualizations

Outputs:
- documentation/kpi_report.md
- visualizations/figures/*.png
- visualizations/interactive/monthly_revenue.html

Notes:
- Transactions use separate customer/product namespaces; metrics that combine orders and transactions report each source separately and combined totals where safe.
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def safe_read(path: Path, parse_dates=None):
    if not path.exists():
        logger.warning('File not found: %s', path)
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=parse_dates, infer_datetime_format=True)


def ensure_dates(df, col):
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors='coerce')
    return df


def save_fig(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info('Saved %s', path)


def main(input_dir: str, output_dir: str):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    figs = output_dir / 'figures'
    inter = output_dir / 'interactive'
    figs.mkdir(parents=True, exist_ok=True)
    inter.mkdir(parents=True, exist_ok=True)

    # Load data (prefer transformed)
    orders_path = input_dir / 'transformed_orders.csv'
    if not orders_path.exists():
        orders_path = input_dir / 'cleaned_orders.csv'
    tx_path = input_dir / 'transformed_transactions.csv'
    if not tx_path.exists():
        tx_path = input_dir / 'cleaned_transactions.csv'

    orders = safe_read(orders_path, parse_dates=['order_date'])
    tx = safe_read(tx_path, parse_dates=['transaction_date'])

    # Ensure dates
    orders = ensure_dates(orders, 'order_date')
    tx = ensure_dates(tx, 'transaction_date')

    # Basic KPIs
    orders_revenue = orders['total_amount'].sum() if 'total_amount' in orders.columns else 0.0
    tx_revenue = tx['total_amount'].sum() if 'total_amount' in tx.columns else 0.0
    total_revenue = orders_revenue + tx_revenue

    total_orders = len(orders)
    total_transactions = len(tx)
    total_sales_events = total_orders + total_transactions

    unique_customers_orders = int(orders['customer_id'].nunique()) if 'customer_id' in orders.columns else 0
    unique_customers_tx = int(tx['customer_id'].nunique()) if 'customer_id' in tx.columns else 0

    # combined unique customers naive (may double-count due to different namespaces)
    combined_unique_customers = 'requires_mapping'  # cannot safely combine without mapping

    aov = (orders_revenue / total_orders) if total_orders>0 else np.nan
    avg_revenue_per_customer_orders = (orders_revenue / unique_customers_orders) if unique_customers_orders>0 else np.nan
    avg_revenue_per_customer_tx = (tx_revenue / unique_customers_tx) if unique_customers_tx>0 else np.nan

    # Time series KPIs
    # Monthly revenue (transactions) and orders
    if not tx.empty:
        tx['month'] = tx['transaction_date'].dt.to_period('M').dt.to_timestamp()
        monthly_tx = tx.groupby('month').agg(revenue=('total_amount','sum'), transactions=('transaction_id','count')).reset_index()
    else:
        monthly_tx = pd.DataFrame()
    if not orders.empty:
        orders['month'] = orders['order_date'].dt.to_period('M').dt.to_timestamp()
        monthly_orders = orders.groupby('month').agg(revenue=('total_amount','sum'), orders=('order_id','count')).reset_index()
    else:
        monthly_orders = pd.DataFrame()

    # Revenue growth month-over-month (transactions)
    if not monthly_tx.empty:
        monthly_tx['revenue_mom_pct'] = monthly_tx['revenue'].pct_change().fillna(0)*100
    if not monthly_orders.empty:
        monthly_orders['revenue_mom_pct'] = monthly_orders['revenue'].pct_change().fillna(0)*100

    # Daily revenue
    if not tx.empty:
        tx['date'] = tx['transaction_date'].dt.date
        daily_tx = tx.groupby('date').agg(revenue=('total_amount','sum'), transactions=('transaction_id','count')).reset_index()
    else:
        daily_tx = pd.DataFrame()
    if not orders.empty:
        orders['date'] = orders['order_date'].dt.date
        daily_orders = orders.groupby('date').agg(revenue=('total_amount','sum'), orders=('order_id','count')).reset_index()
    else:
        daily_orders = pd.DataFrame()

    # Sales trend (simple moving average on daily_tx)
    if not daily_tx.empty:
        daily_tx = daily_tx.sort_values('date')
        daily_tx['revenue_sma_3'] = daily_tx['revenue'].rolling(window=3, min_periods=1).mean()

    # Top products and categories and customers
    top_products = tx.groupby('product_name_clean').agg(transactions=('transaction_id','count'), revenue=('total_amount','sum')).sort_values('revenue', ascending=False).reset_index().head(10)
    top_categories = tx.groupby('category').agg(transactions=('transaction_id','count'), revenue=('total_amount','sum')).sort_values('revenue', ascending=False).reset_index()
    # Top customers by revenue in transactions
    top_customers_tx = tx.groupby('customer_id').agg(transactions=('transaction_id','count'), revenue=('total_amount','sum')).sort_values('revenue', ascending=False).reset_index().head(10)
    top_customers_orders = orders.groupby('customer_id').agg(orders=('order_id','count'), revenue=('total_amount','sum')).sort_values('revenue', ascending=False).reset_index().head(10)

    # Repeat purchase rate (orders): customers with >1 orders / customers with >=1 orders
    repeat_rate_orders = None
    if unique_customers_orders>0:
        customers_order_counts = orders.groupby('customer_id').agg(orders=('order_id','nunique')).reset_index()
        repeat_rate_orders = (customers_order_counts['orders']>1).sum() / len(customers_order_counts)
    repeat_rate_tx = None
    if unique_customers_tx>0:
        customers_tx_counts = tx.groupby('customer_id').agg(tx_count=('transaction_id','nunique')).reset_index()
        repeat_rate_tx = (customers_tx_counts['tx_count']>1).sum() / len(customers_tx_counts)

    # Customer retention rate by month (transactions) - cohort style naive: customers present in month n and in n+1
    retention_rate = pd.DataFrame()
    if not monthly_tx.empty:
        monthly_customers = tx.groupby('month').customer_id.unique().to_dict()
        months = sorted(monthly_customers.keys())
        rows = []
        for i in range(len(months)-1):
            m = months[i]
            m2 = months[i+1]
            base = set(monthly_customers[m])
            nextset = set(monthly_customers[m2])
            retained = len(base & nextset)
            rate = retained / len(base) if len(base)>0 else np.nan
            rows.append({'month': m, 'next_month': m2, 'retained': retained, 'base_customers': len(base), 'retention_rate': rate})
        retention_rate = pd.DataFrame(rows)

    # Revenue by region (store_location available in transactions)
    revenue_by_region = None
    if 'store_location' in tx.columns:
        revenue_by_region = tx.groupby('store_location').agg(revenue=('total_amount','sum'), transactions=('transaction_id','count')).sort_values('revenue', ascending=False).reset_index()

    # Visualizations
    # 1. Monthly revenue (transactions)
    if not monthly_tx.empty:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.plot(monthly_tx['month'], monthly_tx['revenue'], marker='o')
        ax.set_title('Monthly Revenue (Transactions)')
        ax.set_xlabel('Month')
        ax.set_ylabel('Revenue')
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'monthly_revenue_transactions.png')
        # interactive
        fig_int = px.line(monthly_tx, x='month', y='revenue', title='Monthly Revenue (Transactions)', markers=True)
        fig_int.write_html(inter / 'monthly_revenue.html')
        logger.info('Saved interactive monthly revenue chart')

    # 2. Daily revenue
    if not daily_tx.empty:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.plot(daily_tx['date'], daily_tx['revenue'], marker='o')
        ax.set_title('Daily Revenue (Transactions)')
        ax.set_xlabel('Date')
        ax.set_ylabel('Revenue')
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'daily_revenue_transactions.png')

    # 3. Sales trend with rolling avg
    if not daily_tx.empty:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.plot(daily_tx['date'], daily_tx['revenue'], label='daily')
        ax.plot(daily_tx['date'], daily_tx['revenue_sma_3'], label='3-day SMA')
        ax.set_title('Sales Trend (Daily Revenue with 3-day SMA)')
        ax.legend()
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'sales_trend_sma.png')

    # 4. Top products (bar)
    if not top_products.empty:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.bar(top_products['product_name_clean'], top_products['revenue'], color='tab:blue')
        ax.set_title('Top Products by Revenue (Transactions)')
        plt.xticks(rotation=45, ha='right')
        save_fig(fig, figs / 'top_products_by_revenue.png')

    # 5. Top categories
    if not top_categories.empty:
        fig, ax = plt.subplots(figsize=(8,6))
        ax.bar(top_categories['category'], top_categories['revenue'], color='tab:green')
        ax.set_title('Revenue by Category (Transactions)')
        plt.xticks(rotation=45, ha='right')
        save_fig(fig, figs / 'revenue_by_category.png')

    # 6. Top customers
    if not top_customers_tx.empty:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.bar(top_customers_tx['customer_id'].astype(str), top_customers_tx['revenue'], color='tab:purple')
        ax.set_title('Top Customers by Revenue (Transactions)')
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'top_customers_transactions.png')
    if not top_customers_orders.empty:
        fig, ax = plt.subplots(figsize=(8,4))
        ax.bar(top_customers_orders['customer_id'].astype(str), top_customers_orders['revenue'], color='tab:orange')
        ax.set_title('Top Customers by Revenue (Orders)')
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'top_customers_orders.png')

    # 7. Revenue by region
    if revenue_by_region is not None and not revenue_by_region.empty:
        fig, ax = plt.subplots(figsize=(8,6))
        ax.bar(revenue_by_region['store_location'], revenue_by_region['revenue'], color='tab:red')
        ax.set_title('Revenue by Region (Store Location)')
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'revenue_by_region.png')

    # 8. Repeat purchase rate visualization
    fig, ax = plt.subplots(figsize=(6,4))
    labels = ['Repeat','One-time']
    repeat_count = 0
    one_time = 0
    if repeat_rate_orders is not None:
        # compute counts
        customers_order_counts = orders.groupby('customer_id').agg(orders=('order_id','nunique')).reset_index()
        repeat_count = (customers_order_counts['orders']>1).sum()
        one_time = (customers_order_counts['orders']==1).sum()
        ax.pie([repeat_count, one_time], labels=labels, autopct='%1.1f%%', colors=['#2ca02c','#1f77b4'])
        ax.set_title('Repeat Purchase Rate (Orders)')
        save_fig(fig, figs / 'repeat_purchase_rate_orders.png')
    else:
        plt.close(fig)

    # Compose KPI report (markdown)
    md = []
    md.append('# KPI Report\n')
    md.append('This report summarizes key business KPIs computed from the cleaned/processed datasets.\n')
    md.append('## High-level metrics\n')
    md.append(f'- Total revenue (orders): ${orders_revenue:.2f}')
    md.append(f'- Total revenue (transactions): ${tx_revenue:.2f}')
    md.append(f'- Combined total revenue: ${total_revenue:.2f}')
    md.append(f'- Total orders (order records): {total_orders}')
    md.append(f'- Total transactions (transaction records): {total_transactions}')
    md.append(f'- Total sales events: {total_sales_events}')
    md.append(f'- Unique customers (orders): {unique_customers_orders}')
    md.append(f'- Unique customers (transactions): {unique_customers_tx}')
    md.append('- Note: Combining unique customers across orders and transactions requires authoritative mapping (transactions use Cxxxx namespace).\n')
    md.append('## Averages\n')
    md.append(f'- Average Order Value (AOV): ${aov:.2f} (orders only)')
    md.append(f'- Average revenue per customer (orders): ${avg_revenue_per_customer_orders:.2f}')
    md.append(f'- Average revenue per customer (transactions): ${avg_revenue_per_customer_tx:.2f}')
    md.append('## Revenue growth (month-over-month)\n')
    if not monthly_tx.empty:
        md.append('Monthly revenue (transactions):\n')
        for _, r in monthly_tx.iterrows():
            md.append(f'- {r.month.date()}: ${r.revenue:.2f} (MoM {r.revenue_mom_pct:.1f}%)')
    if not monthly_orders.empty:
        md.append('Monthly revenue (orders):\n')
        for _, r in monthly_orders.iterrows():
            md.append(f'- {r.month.date()}: ${r.revenue:.2f} (MoM {r.revenue_mom_pct:.1f}%)')
    md.append('\n')
    md.append('## Top products (transactions)\n')
    for _, r in top_products.iterrows():
        md.append(f'- {r.product_name_clean}: revenue ${r.revenue:.2f}, transactions {int(r.transactions)}')
    md.append('\n')
    md.append('## Top categories\n')
    for _, r in top_categories.head(10).iterrows():
        md.append(f'- {r.category}: revenue ${r.revenue:.2f}, transactions {int(r.transactions)}')
    md.append('\n')
    md.append('## Top customers\n')
    md.append('Top customers (transactions):\n')
    for _, r in top_customers_tx.iterrows():
        md.append(f'- {r.customer_id}: revenue ${r.revenue:.2f}, transactions {int(r.transactions)}')
    md.append('Top customers (orders):\n')
    for _, r in top_customers_orders.iterrows():
        md.append(f'- {r.customer_id}: revenue ${r.revenue:.2f}, orders {int(r.orders)}')
    md.append('\n')
    md.append('## Repeat & retention\n')
    md.append(f'- Repeat purchase rate (orders): {repeat_rate_orders:.2%}' if repeat_rate_orders is not None else '- Repeat purchase rate (orders): N/A')
    md.append(f'- Repeat purchase rate (transactions): {repeat_rate_tx:.2%}' if repeat_rate_tx is not None else '- Repeat purchase rate (transactions): N/A')
    if not retention_rate.empty:
        md.append('\nMonthly retention samples:\n')
        for _, r in retention_rate.iterrows():
            md.append(f'- {r.month.date()} -> {r.next_month.date()}: retention_rate {r.retention_rate:.2%} (base {r.base_customers} customers)')

    if revenue_by_region is not None:
        md.append('\n## Revenue by region (store_location)\n')
        for _, r in revenue_by_region.iterrows():
            md.append(f'- {r.store_location}: revenue ${r.revenue:.2f}, transactions {int(r.transactions)}')

    md.append('\n## Visualizations\n')
    md.append('- visualizations/figures/monthly_revenue_transactions.png (and interactive HTML)')
    md.append('- visualizations/figures/daily_revenue_transactions.png')
    md.append('- visualizations/figures/sales_trend_sma.png')
    md.append('- visualizations/figures/top_products_by_revenue.png')
    md.append('- visualizations/figures/revenue_by_category.png')
    md.append('- visualizations/figures/top_customers_transactions.png')
    md.append('- visualizations/figures/revenue_by_region.png')

    report_path = Path('documentation') / 'kpi_report.md'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text('\n'.join(md))
    logger.info('Wrote KPI report to %s', report_path)

    # Save some data tables for review
    (output_dir / 'top_products.csv').write_text(top_products.to_csv(index=False))
    (output_dir / 'top_customers_tx.csv').write_text(top_customers_tx.to_csv(index=False))
    (output_dir / 'revenue_by_region.csv').write_text(revenue_by_region.to_csv(index=False) if revenue_by_region is not None else '')

    print('KPIs and visualizations generated. See documentation/kpi_report.md and visualizations/ for outputs.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str, default='data/processed_data')
    parser.add_argument('--output-dir', type=str, default='visualizations')
    args = parser.parse_args()
    main(args.input_dir, args.output_dir)
