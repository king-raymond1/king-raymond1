"""
Transaction analysis: frequency, payment trends, daily/monthly aggregations, high-value transactions,
transaction distribution, outlier detection and insights.

Usage:
    python scripts/transaction_analysis.py --input-dir data/processed_data --output-dir visualizations --high_value_pct 0.95

Outputs (written to output-dir and analysis/):
- analysis/transaction_summary.csv
- analysis/daily_transactions.csv
- analysis/monthly_transactions.csv
- analysis/payment_trends.csv
- analysis/high_value_transactions.csv
- analysis/transaction_distribution.csv
- analysis/transaction_outliers.csv
- visualizations/figures/daily_transactions.png
- visualizations/figures/monthly_transactions.png
- visualizations/figures/payment_trends.png
- visualizations/figures/transaction_value_distribution.png
- visualizations/figures/high_value_transactions.png
- documentation/transaction_analysis_report.md

Notes:
- Script reads cleaned_transactions.csv (or transformed_transactions.csv if present) from input dir.
- Outlier detection uses both IQR and z-score (fallback) methods; thresholds configurable.
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


def iqr_outliers(series, k=1.5):
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - k * iqr
    upper = q3 + k * iqr
    return lower, upper


def zscore_outliers(series, threshold=3.0):
    mean = series.mean()
    std = series.std()
    if std == 0 or np.isnan(std):
        return (-np.inf, np.inf)
    lower = mean - threshold * std
    upper = mean + threshold * std
    return lower, upper


def main(input_dir: str, output_dir: str, high_value_pct: float, iqr_k: float, z_thresh: float):
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
        logger.error('No transactions file found. Place cleaned_transactions.csv or transformed_transactions.csv in %s', input_dir)
        return

    if 'transaction_date' in tx.columns:
        tx['transaction_date'] = pd.to_datetime(tx['transaction_date'], errors='coerce')
    else:
        logger.error('transaction_date column not found in transactions file')

    # Basic summary
    total_revenue = tx['total_amount'].sum()
    total_transactions = tx['transaction_id'].nunique() if 'transaction_id' in tx.columns else len(tx)
    unique_customers = tx['customer_id'].nunique() if 'customer_id' in tx.columns else tx['customer_id'].nunique()
    avg_tx_value = tx['total_amount'].mean()

    summary = {
        'total_revenue': float(total_revenue),
        'total_transactions': int(total_transactions),
        'unique_customers': int(unique_customers),
        'avg_transaction_value': float(avg_tx_value)
    }
    pd.DataFrame([summary]).to_csv(analysis_dir / 'transaction_summary.csv', index=False)

    # Frequency: transactions per customer
    if 'customer_id' in tx.columns:
        freq = tx.groupby('customer_id').agg(tx_count=('transaction_id','nunique') if 'transaction_id' in tx.columns else ('transaction_date','count'), revenue=('total_amount','sum')).reset_index()
        freq['avg_tx_value'] = (freq['revenue'] / freq['tx_count']).round(2)
        freq = freq.sort_values('tx_count', ascending=False)
        freq.to_csv(analysis_dir / 'transaction_frequency_per_customer.csv', index=False)
    else:
        freq = pd.DataFrame()

    # Daily transactions
    tx['date'] = tx['transaction_date'].dt.date
    daily = tx.groupby('date').agg(transactions=('transaction_id','count') if 'transaction_id' in tx.columns else ('date','count'), revenue=('total_amount','sum')).reset_index()
    daily = daily.sort_values('date')
    daily['avg_tx_value'] = daily.apply(lambda r: r['revenue']/r['transactions'] if r['transactions']>0 else 0, axis=1)
    daily.to_csv(analysis_dir / 'daily_transactions.csv', index=False)

    # Monthly transactions
    tx['month'] = tx['transaction_date'].dt.to_period('M').dt.to_timestamp()
    monthly = tx.groupby('month').agg(transactions=('transaction_id','count') if 'transaction_id' in tx.columns else ('month','count'), revenue=('total_amount','sum')).reset_index()
    monthly = monthly.sort_values('month')
    monthly['avg_tx_value'] = monthly.apply(lambda r: r['revenue']/r['transactions'] if r['transactions']>0 else 0, axis=1)
    monthly.to_csv(analysis_dir / 'monthly_transactions.csv', index=False)

    # Payment trends
    payment_trends = pd.DataFrame()
    if 'payment_method' in tx.columns:
        payment_trends = tx.groupby('payment_method').agg(transactions=('transaction_id','count') if 'transaction_id' in tx.columns else ('transaction_date','count'), revenue=('total_amount','sum')).reset_index().sort_values('revenue', ascending=False)
        payment_trends['avg_tx_value'] = payment_trends.apply(lambda r: r['revenue']/r['transactions'] if r['transactions']>0 else 0, axis=1)
        payment_trends.to_csv(analysis_dir / 'payment_trends.csv', index=False)

    # High-value transactions (top percentile)
    high_threshold = tx['total_amount'].quantile(high_value_pct)
    high_tx = tx[tx['total_amount'] >= high_threshold].sort_values('total_amount', ascending=False)
    high_tx.to_csv(analysis_dir / 'high_value_transactions.csv', index=False)

    # Transaction distribution
    dist = tx['total_amount'].describe().to_frame().reset_index().rename(columns={'index':'stat', 'total_amount':'value'})
    dist.to_csv(analysis_dir / 'transaction_distribution.csv', index=False)

    # Outlier detection: IQR method
    lower, upper = iqr_outliers(tx['total_amount'].dropna(), k=iqr_k)
    outliers_iqr = tx[(tx['total_amount'] < lower) | (tx['total_amount'] > upper)].copy()
    # z-score fallback
    zlower, zupper = zscore_outliers(tx['total_amount'].dropna(), threshold=z_thresh)
    outliers_z = tx[(tx['total_amount'] < zlower) | (tx['total_amount'] > zupper)].copy()

    # Combine outliers
    outliers = pd.concat([outliers_iqr, outliers_z]).drop_duplicates()
    outliers.to_csv(analysis_dir / 'transaction_outliers.csv', index=False)

    # Visualizations
    # Daily transactions plot
    if not daily.empty:
        fig, ax = plt.subplots(figsize=(12,6))
        ax.plot(daily['date'], daily['transactions'], marker='o')
        ax.set_title('Daily Transactions')
        ax.set_xlabel('Date')
        ax.set_ylabel('Number of Transactions')
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'daily_transactions.png')

    # Monthly transactions plot
    if not monthly.empty:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.plot(monthly['month'], monthly['transactions'], marker='o')
        ax.set_title('Monthly Transactions')
        ax.set_xlabel('Month')
        ax.set_ylabel('Number of Transactions')
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'monthly_transactions.png')

    # Payment trends plot
    if not payment_trends.empty:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.bar(payment_trends['payment_method'], payment_trends['revenue'], color='tab:green')
        ax.set_title('Revenue by Payment Method')
        ax.set_xlabel('Payment Method')
        ax.set_ylabel('Revenue')
        plt.xticks(rotation=45)
        save_fig(fig, figs / 'payment_trends.png')

    # Transaction value distribution histogram
    fig, ax = plt.subplots(figsize=(10,6))
    ax.hist(tx['total_amount'].dropna(), bins=40, color='tab:blue')
    ax.set_title('Transaction Value Distribution')
    ax.set_xlabel('Transaction Value')
    ax.set_ylabel('Count')
    save_fig(fig, figs / 'transaction_value_distribution.png')

    # High value transactions plot (top N)
    if not high_tx.empty:
        topn = high_tx.head(50)
        fig, ax = plt.subplots(figsize=(12,6))
        ax.bar(range(len(topn)), topn['total_amount'], color='tab:orange')
        ax.set_title(f'High-value Transactions (top >= {high_value_pct*100:.0f}th percentile)')
        ax.set_xlabel('Rank')
        ax.set_ylabel('Transaction Value')
        save_fig(fig, figs / 'high_value_transactions.png')

    # Save small CSV summaries for quick inspection
    (analysis_dir / 'transaction_summary.csv').write_text(pd.DataFrame([summary]).to_csv(index=False))
    if not payment_trends.empty:
        (analysis_dir / 'payment_trends.csv').write_text(payment_trends.to_csv(index=False))
    (analysis_dir / 'transaction_distribution.csv').write_text(dist.to_csv(index=False, index=False))

    # Generate report
    report = []
    report.append('# Transaction Analysis Report')
    report.append('\nThis report summarizes transaction behavior: frequency, payment trends, daily/monthly trends, high-value transactions, distribution, outliers and business insights.\n')
    report.append('## Summary metrics\n')
    report.append(f'- Total revenue: ${summary["total_revenue"]:.2f}')
    report.append(f'- Total transactions: {summary["total_transactions"]}')
    report.append(f'- Unique customers: {summary["unique_customers"]}')
    report.append(f'- Average transaction value: ${summary["avg_transaction_value"]:.2f}')

    report.append('\n## Frequency & temporal trends\n')
    report.append('- Daily & monthly transaction CSVs: analysis/daily_transactions.csv and analysis/monthly_transactions.csv')
    report.append('- See visualizations/figures/daily_transactions.png and monthly_transactions.png for trends.\n')

    report.append('\n## Payment trends\n')
    if not payment_trends.empty:
        for _, r in payment_trends.iterrows():
            report.append(f'- {r.payment_method}: revenue ${r.revenue:.2f}, transactions {int(r.transactions)}, avg ${r.avg_tx_value:.2f}')
    else:
        report.append('- No payment_method column available in transactions.\n')

    report.append('\n## High-value transactions\n')
    report.append(f'- High-value threshold (>= {high_value_pct*100:.0f}th percentile): ${high_threshold:.2f}')
    report.append(f'- High-value transactions count: {len(high_tx)}')

    report.append('\n## Distribution & outliers\n')
    report.append('- Transaction value distribution: analysis/transaction_distribution.csv and visualizations/figures/transaction_value_distribution.png')
    report.append(f'- Outliers detected (IQR k={iqr_k} and z-score threshold={z_thresh}): {len(outliers)} transactions — file: analysis/transaction_outliers.csv')

    report.append('\n## Business insights & recommendations\n')
    report.append('- Transaction frequency: identify top recurring customers (analysis/transaction_frequency_per_customer.csv) and prioritize for retention programs.')
    report.append('- Payment trends: if a dominant payment method exists, ensure UX and fraud rules are tuned for it; if certain methods show higher avg transaction, consider promotional nudges for others.')
    report.append('- High-value transactions: review top transactions for VIP customers and potential fraud; consider dedicated fulfillment and upsell.\n')
    report.append('- Outlier detection: validate outliers to filter data errors, chargebacks, refunds or genuine bulk buys. Use refined thresholds for production.\n')
    report.append('- Distribution: if heavy right-skew observed, consider log-transform for modeling, and tailor marketing/promo segmentation by value buckets.\n')

    (output_dir.parent / 'documentation').mkdir(parents=True, exist_ok=True)
    (output_dir.parent / 'documentation' / 'transaction_analysis_report.md').write_text('\n'.join(report))

    logger.info('Transaction analysis complete. Outputs written to %s and %s', analysis_dir, figs)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str, default='data/processed_data')
    parser.add_argument('--output-dir', type=str, default='visualizations')
    parser.add_argument('--high_value_pct', type=float, default=0.95)
    parser.add_argument('--iqr_k', type=float, default=1.5)
    parser.add_argument('--z_thresh', type=float, default=3.0)
    args = parser.parse_args()
    main(args.input_dir, args.output_dir, args.high_value_pct, args.iqr_k, args.z_thresh)
