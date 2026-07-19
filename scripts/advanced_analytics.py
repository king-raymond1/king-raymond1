"""
Advanced analytics: RFM segmentation, ABC & Pareto, Cohort analysis, Customer retention, Revenue concentration,
Top 20% customers & products, and business recommendations.

Usage:
    python scripts/advanced_analytics.py --input-dir data/processed_data --output-dir visualizations --cohort_period month

Outputs (written to analysis/ and visualizations/figures/):
- analysis/rfm_segmentation.csv
- analysis/abc_pareto_products.csv
- analysis/pareto_products.csv
- analysis/cohort_analysis.csv
- analysis/retention_table.csv
- analysis/revenue_concentration.csv
- analysis/top20_customers.csv
- analysis/top20_products.csv
- visualizations/figures/rfm_segment_counts.png
- visualizations/figures/abc_pareto.png
- visualizations/figures/cohort_retention_heatmap.png
- visualizations/figures/lorenz_curve.png
- visualizations/figures/top20_customers_products.png
- documentation/advanced_analytics_report.md

Notes:
- Script works from cleaned_transactions.csv by default; if you have cleaned_orders.csv we merge where sensible.
- Requires pandas, numpy, matplotlib, seaborn, scikit-learn
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

sns.set(style='whitegrid')


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


def rfm_from_transactions(tx, id_col='customer_id', date_col='transaction_date', amount_col='total_amount'):
    tx[date_col] = pd.to_datetime(tx[date_col], errors='coerce')
    ref_date = tx[date_col].max()
    agg = tx.groupby(id_col).agg(
        recency_date=(date_col, 'max'),
        frequency=(date_col, 'count'),
        monetary=(amount_col, 'sum')
    ).reset_index()
    agg['recency_days'] = (ref_date - agg['recency_date']).dt.days
    agg['avg_order_value'] = (agg['monetary'] / agg['frequency']).round(2)
    # scoring (quintiles)
    agg['r_score'] = pd.qcut(agg['recency_days'].rank(method='first'), q=5, labels=False, duplicates='drop')
    agg['r_score'] = (5 - agg['r_score']).astype(int)  # invert so recent -> high
    agg['f_score'] = pd.qcut(agg['frequency'].rank(method='first'), q=5, labels=False, duplicates='drop').astype(int) + 1
    agg['m_score'] = pd.qcut(agg['monetary'].rank(method='first'), q=5, labels=False, duplicates='drop').astype(int) + 1
    agg[['r_score','f_score','m_score']] = agg[['r_score','f_score','m_score']].clip(1,5)
    agg['rfm_score'] = agg['r_score'].map(str) + agg['f_score'].map(str) + agg['m_score'].map(str)
    agg['rfm_numeric'] = agg['r_score']*100 + agg['f_score']*10 + agg['m_score']
    return agg


def rfm_segment_label(df):
    def label(row):
        r, f, m = row['r_score'], row['f_score'], row['m_score']
        if r >=4 and f >=4 and m >=4:
            return 'Champion'
        if f >=4:
            return 'Loyal'
        if r >=4 and m >=3:
            return 'Potential Loyalist'
        if r <=2 and f >=3 and m >=3:
            return 'At Risk'
        if r <=2 and f <=2:
            return 'Hibernating'
        if f == 1 and r >=4:
            return 'New'
        return 'Other'
    df = df.copy()
    df['segment'] = df.apply(label, axis=1)
    return df


def abc_pareto_products(df_prod):
    df = df_prod.copy().sort_values('total_revenue', ascending=False)
    df['cum_revenue'] = df['total_revenue'].cumsum()
    total = df['total_revenue'].sum()
    df['cum_pct'] = df['cum_revenue'] / total
    # ABC
    def cls(x):
        if x <= 0.7:
            return 'A'
        elif x <= 0.9:
            return 'B'
        else:
            return 'C'
    df['abc_class'] = df['cum_pct'].apply(cls)
    return df


def pareto_summary(df_prod):
    df = df_prod.sort_values('total_revenue', ascending=False).copy()
    df['cum_revenue'] = df['total_revenue'].cumsum()
    total = df['total_revenue'].sum()
    df['cum_pct'] = df['cum_revenue'] / total
    # find products that make 80% revenue
    top_mask = df['cum_pct'] <= 0.8
    top_df = df[top_mask]
    return df, top_df


def cohort_analysis(tx, period='month'):
    df = tx.copy()
    df['transaction_date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
    df['order_period'] = df['transaction_date'].dt.to_period('M').dt.to_timestamp() if period=='month' else df['transaction_date'].dt.to_period('W').dt.start_time
    df['cohort'] = df.groupby('customer_id')['transaction_date'].transform('min').dt.to_period('M').dt.to_timestamp() if period=='month' else df.groupby('customer_id')['transaction_date'].transform('min').dt.to_period('W').dt.start_time
    grouped = df.groupby(['cohort','order_period']).agg(n_customers=('customer_id','nunique'), revenue=('total_amount','sum')).reset_index()
    # build cohort pivot table for retention (customers)
    cohort_pivot = grouped.pivot_table(index='cohort', columns='order_period', values='n_customers', fill_value=0)
    # convert absolute counts to retention rates
    retention = cohort_pivot.divide(cohort_pivot.iloc[:,0], axis=0).round(3)
    # flatten for CSV
    retention_flat = retention.reset_index()
    return retention, retention_flat


def revenue_concentration_customers(tx):
    # compute revenue per customer and Lorenz/Gini
    cust = tx.groupby('customer_id').total_amount.sum().reset_index().rename(columns={'total_amount':'revenue'})
    cust = cust.sort_values('revenue')
    cust['cum_revenue'] = cust['revenue'].cumsum()
    total = cust['revenue'].sum()
    cust['cum_pct'] = cust['cum_revenue']/total
    cust['cum_customers_pct'] = np.linspace(1/len(cust),1,len(cust))
    # Gini
    values = cust['revenue'].values
    if values.sum()==0:
        gini = 0
    else:
        sorted_vals = np.sort(values)
        n = len(values)
        cumulative = np.cumsum(sorted_vals)
        gini = (1 + (1/n) - 2 * (np.sum(cumulative) / (n * cumulative[-1])))
    return cust, gini


def main(input_dir: str, output_dir: str, cohort_period: str):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    figs = output_dir / 'figures'
    analysis_dir = output_dir.parent / 'analysis'
    figs.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)

    tx_path = input_dir / 'transformed_transactions.csv'
    if not tx_path.exists():
        tx_path = input_dir / 'cleaned_transactions.csv'

    tx = safe_read(tx_path, parse_dates=['transaction_date'])
    if tx.empty:
        logger.error('No transactions file found in %s', input_dir)
        return

    # --- RFM segmentation ---
    rfm = rfm_from_transactions(tx)
    rfm = rfm_segment_label(rfm)
    rfm.to_csv(analysis_dir / 'rfm_segmentation.csv', index=False)

    # plot rfm segments counts
    seg_counts = rfm['segment'].value_counts().reset_index()
    seg_counts.columns = ['segment','count']
    fig, ax = plt.subplots(figsize=(8,5))
    sns.barplot(data=seg_counts, x='segment', y='count', palette='muted', ax=ax)
    ax.set_title('RFM Segment Counts')
    plt.xticks(rotation=45)
    save_fig(fig, figs / 'rfm_segment_counts.png')

    # --- Revenue per product (combine transactions and orders where available) ---
    tx['prod_key'] = tx.get('product_name_clean', tx.get('product_name', tx.get('product_id', ''))).astype(str).str.lower().str.strip()
    prod_agg = tx.groupby('prod_key').agg(units_sold=('quantity','sum'), total_revenue=('total_amount','sum'), tx_count=('transaction_id','count')).reset_index()
    prod_agg.to_csv(analysis_dir / 'product_revenue.csv', index=False)

    # ABC & Pareto
    abc = abc_pareto_products(prod_agg.rename(columns={'total_revenue':'total_revenue'}))
    abc.to_csv(analysis_dir / 'abc_pareto_products.csv', index=False)
    pareto_df, top_pareto = pareto_summary(prod_agg.rename(columns={'total_revenue':'total_revenue'}))
    pareto_df.to_csv(analysis_dir / 'pareto_products.csv', index=False)
    top_pareto.to_csv(analysis_dir / 'top_pareto_products.csv', index=False)

    # ABC plot (cumulative)
    if not pareto_df.empty:
        fig, ax = plt.subplots(figsize=(12,6))
        ax.plot(pareto_df['prod_key'], pareto_df['cum_revenue'], color='tab:purple')
        ax.set_title('Pareto - Cumulative Revenue by Product')
        ax.set_xlabel('Product (sorted by revenue desc)')
        ax.set_ylabel('Cumulative Revenue')
        plt.xticks([], [])
        ax.axhline(pareto_df['cum_revenue'].sum() * 0.7, color='red', linestyle='--', label='70% threshold')
        save_fig(fig, figs / 'abc_pareto.png')

    # --- Cohort analysis (monthly by default) ---
    retention, retention_flat = cohort_analysis(tx, period=cohort_period)
    retention_flat.to_csv(analysis_dir / 'cohort_analysis.csv', index=False)
    retention.to_csv(analysis_dir / 'retention_table.csv')

    # cohort heatmap
    if not retention.empty:
        fig, ax = plt.subplots(figsize=(12,8))
        sns.heatmap(retention, annot=False, cmap='Blues', ax=ax)
        ax.set_title('Cohort Retention (rows=cohort by signup period, cols=periods)')
        save_fig(fig, figs / 'cohort_retention_heatmap.png')

    # --- Customer retention metrics ---
    # Simple retention: percent of customers active in last 30 days
    tx['transaction_date'] = pd.to_datetime(tx['transaction_date'], errors='coerce')
    ref_date = tx['transaction_date'].max()
    last_purchase = tx.groupby('customer_id').transaction_date.max().reset_index().rename(columns={'transaction_date':'last_purchase'})
    last_purchase['days_since_last'] = (ref_date - last_purchase['last_purchase']).dt.days
    churn_window = 90
    last_purchase['churn_flag'] = last_purchase['days_since_last'] > churn_window
    last_purchase.to_csv(analysis_dir / 'retention_customers_snapshot.csv', index=False)

    # --- Revenue concentration & Gini ---
    cust_rev, gini = revenue_concentration_customers(tx)
    cust_rev.to_csv(analysis_dir / 'revenue_concentration.csv', index=False)
    # Lorenz plot
    if not cust_rev.empty:
        fig, ax = plt.subplots(figsize=(8,6))
        x = np.insert(np.cumsum(np.ones(len(cust_rev))/len(cust_rev)), 0, 0)
        y = np.insert(cust_rev['cum_pct'].values, 0, 0)
        ax.plot(x, y, drawstyle='steps-post', label='Lorenz Curve')
        ax.plot([0,1],[0,1], linestyle='--', color='k', label='Equality line')
        ax.set_title(f'Lorenz Curve (Gini={gini:.3f})')
        ax.set_xlabel('Cumulative share of customers')
        ax.set_ylabel('Cumulative share of revenue')
        ax.legend()
        save_fig(fig, figs / 'lorenz_curve.png')

    # --- Top 20% Customers & Products ---
    # Customers
    custs = tx.groupby('customer_id').total_amount.sum().reset_index().rename(columns={'total_amount':'revenue'})
    custs = custs.sort_values('revenue', ascending=False)
    top20_cut = custs['revenue'].sum() * 0.2
    # alternatively top 20% by count
    n_top20 = max(1, int(len(custs) * 0.2))
    top20_customers = custs.head(n_top20)
    top20_customers.to_csv(analysis_dir / 'top20_customers.csv', index=False)

    # Products top20% by revenue
    prods = prod_agg[['prod_key','total_revenue']].sort_values('total_revenue', ascending=False)
    n_prod_top20 = max(1, int(len(prods) * 0.2))
    top20_products = prods.head(n_prod_top20)
    top20_products.to_csv(analysis_dir / 'top20_products.csv', index=False)

    # combined plot: top customers & products
    fig, axs = plt.subplots(1,2, figsize=(14,6))
    sns.barplot(data=top20_customers, x='customer_id', y='revenue', ax=axs[0], palette='Blues')
    axs[0].set_title('Top 20% Customers by Revenue (sample)')
    axs[0].tick_params(axis='x', rotation=45)
    sns.barplot(data=top20_products.head(10), x='prod_key', y='total_revenue', ax=axs[1], palette='Oranges')
    axs[1].set_title('Top Products (sample)')
    axs[1].tick_params(axis='x', rotation=45)
    save_fig(fig, figs / 'top20_customers_products.png')

    # --- Summary report ---
    report = []
    report.append('# Advanced Analytics Report')
    report.append('\nThis run produced RFM segmentation, ABC/Pareto product analysis, cohort retention, customer retention snapshot, revenue concentration (Gini), and top-20% lists for customers and products.\n')
    report.append(f'- Total customers (RFM): {len(rfm)}')
    report.append(f'- Gini coefficient (revenue by customer): {gini:.3f}')
    report.append('\nRefer to files under analysis/ and visualizations/figures/ for tables and charts.\n')

    (analysis_dir / 'advanced_analytics_summary.txt').write_text('\n'.join(report))
    (analysis_dir.parent / 'documentation').mkdir(parents=True, exist_ok=True)
    (analysis_dir.parent / 'documentation' / 'advanced_analytics_report.md').write_text('\n'.join(report))

    logger.info('Advanced analytics complete. Outputs written to %s and %s', analysis_dir, figs)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str, default='data/processed_data')
    parser.add_argument('--output-dir', type=str, default='visualizations')
    parser.add_argument('--cohort_period', type=str, default='month', choices=['month','week'])
    args = parser.parse_args()
    main(args.input_dir, args.output_dir, args.cohort_period)
