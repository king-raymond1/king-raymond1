"""
Exploratory Data Analysis script

This script loads processed/transformed datasets and generates:
- summary statistics
- distribution analyses (numeric & categorical)
- correlation matrix for numeric features
- time series and sales trend plots
- product/customer/revenue distributions
- saves figures to visualizations/figures and interactive plots to visualizations/interactive
- writes a markdown EDA report summarizing insights

Usage:
    python scripts/run_eda.py --input-dir data/processed_data --output-dir visualizations

Requires: pandas, numpy, matplotlib, plotly
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def safe_read(path: Path, parse_dates=None):
    if not path.exists():
        logger.warning("File not found: %s", path)
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=parse_dates, infer_datetime_format=True)


def summary_statistics(df: pd.DataFrame):
    desc = df.describe(include='all', datetime_is_numeric=True)
    return desc


def plot_top_products_by_count(tx_df: pd.DataFrame, out_png: Path, top_n=10):
    counts = tx_df['product_name_clean'].value_counts().head(top_n)
    fig, ax = plt.subplots(figsize=(10,6))
    counts.plot(kind='bar', color='tab:blue', ax=ax)
    ax.set_title(f'Top {top_n} Products by Transactions (count)')
    ax.set_ylabel('Count')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    logger.info('Saved %s', out_png)


def plot_revenue_time_series(daily_ts: pd.DataFrame, out_png: Path, out_html: Path):
    # matplotlib static
    fig, ax = plt.subplots(figsize=(10,6))
    ax.plot(daily_ts['date'], daily_ts['revenue'], marker='o')
    ax.set_title('Daily Revenue')
    ax.set_ylabel('Revenue')
    ax.set_xlabel('Date')
    plt.xticks(rotation=45)
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    logger.info('Saved %s', out_png)
    # interactive
    fig2 = px.line(daily_ts, x='date', y='revenue', title='Daily Revenue', markers=True)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    fig2.write_html(out_html)
    logger.info('Saved interactive %s', out_html)


def correlation_matrix(df: pd.DataFrame, out_png: Path):
    num = df.select_dtypes(include=[np.number])
    if num.shape[1] < 2:
        logger.info('Not enough numeric columns for correlation matrix')
        return
    corr = num.corr()
    fig, ax = plt.subplots(figsize=(10,8))
    cax = ax.matshow(corr, cmap='coolwarm')
    fig.colorbar(cax)
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=45, ha='left')
    ax.set_yticklabels(corr.columns)
    plt.title('Correlation matrix (numeric)')
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    logger.info('Saved %s', out_png)


def category_counts_plot(df: pd.DataFrame, col: str, out_png: Path, top_n=10):
    counts = df[col].value_counts().head(top_n)
    fig, ax = plt.subplots(figsize=(10,6))
    counts.plot(kind='bar', ax=ax, color='tab:green')
    ax.set_title(f'Top {top_n} {col}')
    ax.set_ylabel('Count')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    logger.info('Saved %s', out_png)


def revenue_distribution_plot(df: pd.DataFrame, out_png: Path):
    fig, ax = plt.subplots(figsize=(10,6))
    df['total_amount'].plot(kind='hist', bins=30, ax=ax, color='tab:orange')
    ax.set_title('Revenue Distribution (Transaction/order total_amount)')
    ax.set_xlabel('Amount')
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    logger.info('Saved %s', out_png)


def generate_eda_report(out_md: Path, metrics: dict, insights: str):
    lines = ['# Exploratory Data Analysis Report\n']
    lines.append('## Key summary metrics\n')
    for k,v in metrics.items():
        lines.append(f'- **{k}**: {v}\n')
    lines.append('\n## Insights and commentary\n')
    lines.append(insights)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text('\n'.join(lines))
    logger.info('Wrote EDA report to %s', out_md)


def main(input_dir: str, output_dir: str):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    fig_dir = output_dir / 'figures'
    html_dir = output_dir / 'interactive'

    # Prefer transformed files if present
    tx_path = input_dir / 'transformed_transactions.csv'
    if not tx_path.exists():
        tx_path = input_dir / 'cleaned_transactions.csv'
    orders_path = input_dir / 'transformed_orders.csv' if (input_dir / 'transformed_orders.csv').exists() else input_dir / 'cleaned_orders.csv'
    customers_path = input_dir / 'transformed_customers.csv' if (input_dir / 'transformed_customers.csv').exists() else input_dir / 'cleaned_customers.csv'
    products_path = input_dir / 'transformed_products.csv' if (input_dir / 'transformed_products.csv').exists() else input_dir / 'cleaned_products.csv'

    tx = safe_read(tx_path, parse_dates=['transaction_date'])
    orders = safe_read(orders_path, parse_dates=['order_date'])
    customers = safe_read(customers_path, parse_dates=['signup_date'])
    products = safe_read(products_path)

    # Summary statistics
    tx_desc = summary_statistics(tx)
    orders_desc = summary_statistics(orders)

    # Compute totals we already know for small datasets for inclusion in report
    orders_revenue = orders['total_amount'].sum() if 'total_amount' in orders.columns else 0
    tx_revenue = tx['total_amount'].sum() if 'total_amount' in tx.columns else 0
    combined_revenue = orders_revenue + tx_revenue

    # Distribution analysis: product counts, revenue by product
    top_products_counts = tx['product_name_clean'].value_counts().head(10).to_dict()
    # product revenue
    prod_rev = tx.groupby('product_name_clean', dropna=False)['total_amount'].sum().sort_values(ascending=False).head(10).to_dict()

    # Time trend analysis: daily revenue
    if 'transaction_date' in tx.columns and not tx.empty:
        tx['date'] = pd.to_datetime(tx['transaction_date']).dt.date
        daily = tx.groupby('date').agg(revenue=('total_amount','sum'), transactions=('transaction_id','count')).reset_index()
    else:
        daily = pd.DataFrame()

    # Customer distribution
    unique_customers_tx = tx['customer_id'].nunique() if 'customer_id' in tx.columns else 0
    unique_customers_orders = orders['customer_id'].nunique() if 'customer_id' in orders.columns else 0

    # Sales distribution
    # revenue distribution plot
    revenue_distribution_plot(pd.concat([tx[['total_amount']].assign(source='transaction'), orders[['total_amount']].assign(source='order')]) if (not tx.empty and not orders.empty) else tx, fig_dir / 'revenue_distribution.png')

    # Top products plot
    if not tx.empty:
        plot_top_products_by_count(tx, fig_dir / 'top_products_count.png')
    # Daily revenue plots
    if not daily.empty:
        plot_revenue_time_series(daily, fig_dir / 'daily_revenue.png', html_dir / 'daily_revenue.html')

    # Correlation matrix (transactions)
    correlation_matrix(tx, fig_dir / 'tx_correlation_matrix.png')

    # Categorical analyses
    if 'category' in tx.columns:
        category_counts_plot(tx, 'category', fig_dir / 'category_counts.png', top_n=20)
    if 'payment_method' in tx.columns:
        category_counts_plot(tx, 'payment_method', fig_dir / 'payment_method_counts.png', top_n=10)

    # Generate EDA report summary and insights (include some computed values)
    metrics = {
        'orders_revenue': f'{orders_revenue:.2f}',
        'transactions_revenue': f'{tx_revenue:.2f}',
        'combined_revenue': f'{combined_revenue:.2f}',
        'transactions_rows': int(len(tx)),
        'orders_rows': int(len(orders)),
        'unique_customers_transactions': int(unique_customers_tx),
        'unique_customers_orders': int(unique_customers_orders),
        'total_transaction_quantity': int(tx['quantity'].sum()) if 'quantity' in tx.columns else 'NA',
        'average_transaction_quantity': float(tx['quantity'].mean()) if 'quantity' in tx.columns else 'NA'
    }

    # Craft insights narrative based on computations
    insights = []
    insights.append('### High-level revenue')
    insights.append(f'- Orders revenue: ${orders_revenue:.2f}')
    insights.append(f'- Transactions revenue: ${tx_revenue:.2f}')
    insights.append(f'- Combined revenue (orders + transactions): ${combined_revenue:.2f}')
    insights.append('\n')
    insights.append('### Top products by transaction count')
    for p,c in top_products_counts.items():
        insights.append(f'- {p}: {c} transactions')
    insights.append('\n')
    insights.append('### Time trends (transactions)')
    if not daily.empty:
        top_day = daily.sort_values('revenue', ascending=False).iloc[0]
        insights.append(f'- Highest revenue day: {top_day.date} with revenue ${top_day.revenue:.2f}')
        insights.append('- See visualizations/daily_revenue for the full trend.')
    insights.append('\n')
    insights.append('### Customers')
    insights.append(f'- Unique customers in transactions: {unique_customers_tx}')
    insights.append(f'- Unique customers in orders: {unique_customers_orders}')
    insights.append('\n')
    insights.append('### Recommendations')
    insights.append('- Map transaction product/customer IDs to canonical IDs to enable unified analysis.\n- Investigate order mismatches (order_id 5004) for discounts or corrections.\n- Enrich customers with demographics for segmentation analysis.')

    generate_eda_report(Path('documentation/eda_report.md'), metrics, '\n'.join(insights))
    logger.info('EDA complete. Figures and report written to %s', output_dir)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str, default='data/processed_data')
    parser.add_argument('--output-dir', type=str, default='visualizations')
    args = parser.parse_args()
    main(args.input_dir, args.output_dir)
