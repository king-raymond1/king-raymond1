"""
Product analysis: best/worst selling products, revenue by product/category, popularity, avg quantity,
contribution analysis, ABC classification, and visualizations.

Usage:
    python scripts/product_analysis.py --input-dir data/processed_data --output-dir visualizations --top-n 20

Outputs (written to output-dir):
- analysis/revenue_per_product.csv
- analysis/product_popularity.csv
- analysis/abc_classification.csv
- visualizations/figures/top_products_by_revenue.png
- visualizations/figures/worst_products_by_revenue.png
- visualizations/figures/revenue_by_category.png
- visualizations/figures/pareto_contribution.png
- visualizations/figures/avg_quantity_by_product.png
- visualizations/figures/abc_classification.png
- documentation/product_analysis_report.md

Notes:
- Uses product_name_clean as the canonical product key. If you have product_id mapping, provide transformed_products.csv and the script will prefer product_id/product_name_product.
- Combines orders and transactions where possible using normalized product keys. If only transactions exist, analysis is based on transactions.
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


def normalize_key(s):
    if pd.isna(s):
        return ''
    return str(s).strip().lower()


def compute_abc(df, revenue_col='total_revenue', thresholds=(0.7, 0.9)):
    # thresholds: cumulative revenue fractions for A and B (A up to 0.7, B up to 0.9, C rest)
    df = df.copy().sort_values(revenue_col, ascending=False)
    df['cum_revenue'] = df[revenue_col].cumsum()
    total = df[revenue_col].sum()
    if total == 0:
        df['cum_pct'] = 0
    else:
        df['cum_pct'] = df['cum_revenue'] / total
    def cls(x):
        if x <= thresholds[0]:
            return 'A'
        elif x <= thresholds[1]:
            return 'B'
        else:
            return 'C'
    df['abc_class'] = df['cum_pct'].apply(cls)
    return df


def main(input_dir: str, output_dir: str, top_n: int):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    figs = output_dir / 'figures'
    analysis_dir = output_dir.parent / 'analysis'
    figs.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # Prefer transformed_products and transformed_orders if present
    tx_path = input_dir / 'transformed_transactions.csv'
    if not tx_path.exists():
        tx_path = input_dir / 'cleaned_transactions.csv'
    orders_path = input_dir / 'transformed_orders.csv'
    if not orders_path.exists():
        orders_path = input_dir / 'cleaned_orders.csv'

    products_path = input_dir / 'transformed_products.csv'
    if not products_path.exists():
        products_path = input_dir / 'cleaned_products.csv'

    tx = safe_read(tx_path, parse_dates=['transaction_date'])
    orders = safe_read(orders_path, parse_dates=['order_date'])
    products = safe_read(products_path)

    # Determine product key
    if not products.empty and 'product_id' in products.columns and 'product_name' in products.columns:
        # prefer product_id-based aggregation if orders use product_id
        prefer_id = True
    else:
        prefer_id = False

    # Build product-level aggregation from transactions
    if not tx.empty:
        tx['prod_key'] = tx['product_name_clean'].apply(normalize_key)
        tx_agg = tx.groupby('prod_key').agg(units_sold_tx=('quantity','sum'), revenue_tx=('total_amount','sum'), tx_count=('transaction_id','count')).reset_index()
    else:
        tx_agg = pd.DataFrame(columns=['prod_key','units_sold_tx','revenue_tx','tx_count'])

    # Build product-level aggregation from orders
    if not orders.empty:
        # try to find product name column
        if 'product_name' in orders.columns:
            orders['prod_key'] = orders['product_name'].astype(str).apply(normalize_key)
        elif 'product_name_product' in orders.columns:
            orders['prod_key'] = orders['product_name_product'].astype(str).apply(normalize_key)
        elif 'product_id' in orders.columns and prefer_id and not products.empty:
            # map product_id to name
            prod_map = products.set_index('product_id')['product_name'].to_dict()
            orders['prod_key'] = orders['product_id'].map(prod_map).fillna('').apply(normalize_key)
        else:
            orders['prod_key'] = ''
        orders_agg = orders.groupby('prod_key').agg(units_sold_orders=('quantity','sum'), revenue_orders=('total_amount','sum'), orders_count=('order_id','count')).reset_index()
    else:
        orders_agg = pd.DataFrame(columns=['prod_key','units_sold_orders','revenue_orders','orders_count'])

    # Merge aggregations
    merged = pd.merge(orders_agg, tx_agg, on='prod_key', how='outer').fillna(0)
    merged['prod_key'] = merged['prod_key'].astype(str)
    merged['total_units_sold'] = merged['units_sold_orders'] + merged['units_sold_tx']
    merged['total_revenue'] = merged['revenue_orders'] + merged['revenue_tx']
    merged['total_count'] = merged['orders_count'] + merged['tx_count']
    merged['avg_quantity_per_order_tx'] = merged.apply(lambda r: (r['total_units_sold'] / r['total_count']) if r['total_count']>0 else 0, axis=1).round(2)
    merged = merged.sort_values('total_revenue', ascending=False)

    # Save revenue per product
    merged[['prod_key','total_units_sold','total_revenue','avg_quantity_per_order_tx']].to_csv(analysis_dir / 'revenue_per_product.csv', index=False)

    # Best-selling products (by revenue)
    top_products = merged.head(top_n).copy()
    top_products.to_csv(analysis_dir / 'top_products_by_revenue.csv', index=False)

    # Worst-selling products (bottom N non-zero revenue)
    non_zero = merged[merged['total_revenue']>0]
    worst_products = non_zero.tail(top_n).sort_values('total_revenue') if not non_zero.empty else merged.tail(top_n)
    worst_products.to_csv(analysis_dir / 'worst_products_by_revenue.csv', index=False)

    # Revenue by category (use transactions primarily)
    revenue_by_category = pd.DataFrame()
    if not tx.empty and 'category' in tx.columns:
        revenue_by_category = tx.groupby('category').agg(units_sold=('quantity','sum'), revenue=('total_amount','sum'), transactions=('transaction_id','count')).reset_index().sort_values('revenue', ascending=False)
        revenue_by_category.to_csv(analysis_dir / 'revenue_by_category.csv', index=False)

    # Product popularity: frequency (count of transactions/orders) and units sold
    popularity = merged[['prod_key','total_count','total_units_sold','total_revenue']].copy()
    popularity = popularity.sort_values(['total_revenue','total_units_sold'], ascending=[False,False])
    popularity.to_csv(analysis_dir / 'product_popularity.csv', index=False)

    # Contribution analysis & Pareto
    merged['revenue_pct'] = merged['total_revenue'] / merged['total_revenue'].sum() if merged['total_revenue'].sum()>0 else 0
    merged['cum_revenue_pct'] = merged['revenue_pct'].cumsum()
    merged[['prod_key','total_units_sold','total_revenue','revenue_pct','cum_revenue_pct']].to_csv(analysis_dir / 'product_contribution.csv', index=False)

    # ABC classification
    abc = compute_abc(merged[['prod_key','total_revenue']].rename(columns={'total_revenue':'total_revenue'}), revenue_col='total_revenue', thresholds=(0.7,0.9))
    abc.to_csv(analysis_dir / 'abc_classification.csv', index=False)

    # Visualizations
    # Top products by revenue
    if not top_products.empty:
        fig, ax = plt.subplots(figsize=(12,6))
        ax.bar(top_products['prod_key'], top_products['total_revenue'], color='tab:blue')
        ax.set_title(f'Top {top_n} Products by Revenue')
        ax.set_xlabel('Product')
        ax.set_ylabel('Revenue')
        plt.xticks(rotation=45, ha='right')
        save_fig(fig, figs / f'top_products_by_revenue.png')

    # Worst products
    if not worst_products.empty:
        fig, ax = plt.subplots(figsize=(12,6))
        ax.bar(worst_products['prod_key'], worst_products['total_revenue'], color='tab:orange')
        ax.set_title(f'Worst {top_n} Products by Revenue (non-zero)')
        ax.set_xlabel('Product')
        ax.set_ylabel('Revenue')
        plt.xticks(rotation=45, ha='right')
        save_fig(fig, figs / f'worst_products_by_revenue.png')

    # Revenue by category
    if not revenue_by_category.empty:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.bar(revenue_by_category['category'], revenue_by_category['revenue'], color='tab:green')
        ax.set_title('Revenue by Category')
        ax.set_xlabel('Category')
        ax.set_ylabel('Revenue')
        plt.xticks(rotation=45, ha='right')
        save_fig(fig, figs / 'revenue_by_category.png')

    # Pareto contribution
    if merged['total_revenue'].sum()>0:
        fig, ax = plt.subplots(figsize=(12,6))
        ax.plot(merged['prod_key'], merged['cum_revenue_pct'], marker='o', color='tab:purple')
        ax.set_title('Cumulative Revenue Contribution by Product (Pareto)')
        ax.set_xlabel('Products (sorted by revenue)')
        ax.set_ylabel('Cumulative Revenue %')
        plt.xticks(rotation=90)
        ax.axhline(0.7, color='red', linestyle='--', label='70% (A/B threshold)')
        ax.axhline(0.9, color='orange', linestyle='--', label='90% (B/C threshold)')
        ax.legend()
        save_fig(fig, figs / 'pareto_contribution.png')

    # Avg quantity by product (top N)
    if not merged.empty:
        sample = merged.head(top_n)
        fig, ax = plt.subplots(figsize=(12,6))
        ax.bar(sample['prod_key'], sample['avg_quantity_per_order_tx'], color='tab:brown')
        ax.set_title(f'Average Quantity per Order/Transaction (Top {top_n} Products)')
        ax.set_xlabel('Product')
        ax.set_ylabel('Avg Quantity')
        plt.xticks(rotation=45, ha='right')
        save_fig(fig, figs / 'avg_quantity_by_product.png')

    # ABC classification plot
    if not abc.empty:
        counts = abc['abc_class'].value_counts().reindex(['A','B','C']).fillna(0)
        fig, ax = plt.subplots(figsize=(6,4))
        ax.bar(counts.index, counts.values, color=['#1f77b4','#ff7f0e','#2ca02c'])
        ax.set_title('ABC Classification Counts')
        ax.set_xlabel('Class')
        ax.set_ylabel('Number of Products')
        save_fig(fig, figs / 'abc_classification.png')

    # Write report
    report = []
    report.append('# Product Analysis Report')
    report.append('\nThis report summarizes product-level performance: best/worst sellers, revenue by product and category, product popularity, average quantity sold, contribution and ABC classification.\n')
    report.append('## Key outputs')
    report.append(f'- analysis/revenue_per_product.csv')
    report.append(f'- analysis/top_products_by_revenue.csv')
    report.append(f'- analysis/worst_products_by_revenue.csv')
    report.append(f'- analysis/product_popularity.csv')
    report.append(f'- analysis/abc_classification.csv')
    report.append('\n## Suggestions and business implications')
    report.append('- Focus merchandising, promotions, and inventory on A-class products (top ~70% revenue) — ensure stock availability and consider premium placements.')
    report.append('- Monitor B-class products for upsell/cross-sell opportunities and evaluate promotions to move them into A-class.')
    report.append('- Consider whether C-class SKUs are worth retaining (low revenue, possibly high carrying cost) — consider delisting or bundling.')
    report.append('- Investigate worst-selling products for issues (pricing, discoverability, product quality).')
    report.append('- Use percent contribution (Pareto) to prioritize 20% of SKUs that drive ~80% of revenue; tailor operations and procurement.\n')
    report.append('\nVisualizations can be found in visualizations/figures/. Run the script locally to regenerate and inspect interactive versions if desired.')

    (output_dir.parent / 'documentation').mkdir(parents=True, exist_ok=True)
    (output_dir.parent / 'documentation' / 'product_analysis_report.md').write_text('\n'.join(report))

    logger.info('Product analysis complete. Outputs written to %s and %s', analysis_dir, figs)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str, default='data/processed_data')
    parser.add_argument('--output-dir', type=str, default='visualizations')
    parser.add_argument('--top-n', type=int, default=20)
    args = parser.parse_args()
    main(args.input_dir, args.output_dir, args.top_n)
