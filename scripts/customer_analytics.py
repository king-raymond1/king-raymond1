"""
Customer analytics: RFM, segmentation, CLV, retention, churn indicators, repeat/one-time classification.

Usage:
    python scripts/customer_analytics.py --input-dir data/processed_data --output-dir analysis --recency_threshold_days 90 --clv_years 3

Outputs:
- analysis/customer_rfm_orders.csv
- analysis/customer_rfm_transactions.csv
- analysis/customer_segments_orders.csv
- analysis/customer_segments_transactions.csv
- documentation/customer_analytics_report.md

Notes:
- Transactions use Cxxxx customer IDs; orders use numeric customer_id. These are analyzed separately unless you provide a mapping file.
- CLV is a simplified deterministic estimate (AOV * purchase_freq_per_month * 12 * clv_years).
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import logging
from datetime import timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def safe_read(path: Path, parse_dates=None):
    if not path.exists():
        logger.warning('File not found: %s', path)
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=parse_dates, infer_datetime_format=True)


def rfm_table(df, id_col, date_col, amount_col, quantity_col=None, ref_date=None):
    # df: transactions or orders
    if df.empty:
        return pd.DataFrame()
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    if ref_date is None:
        ref_date = df[date_col].max()
    # Aggregate per customer
    agg = df.groupby(id_col).agg(
        recency_date=(date_col, 'max'),
        frequency=(date_col, 'count'),
        monetary=(amount_col, 'sum')
    ).reset_index()
    agg['recency_days'] = (ref_date - agg['recency_date']).dt.days
    # Optional average basket
    if quantity_col and quantity_col in df.columns:
        qty = df.groupby(id_col)[quantity_col].sum().reset_index().rename(columns={quantity_col: 'total_quantity'})
        agg = agg.merge(qty, on=id_col, how='left')
        agg['avg_basket_size'] = (agg['total_quantity'] / agg['frequency']).round(2)
    # AOV
    agg['avg_order_value'] = (agg['monetary'] / agg['frequency']).round(2)
    return agg


def rfm_score(df, r_bins=5, f_bins=5, m_bins=5):
    # Score R (lower recency better -> higher score), F and M higher is better
    if df.empty:
        return df
    df = df.copy()
    # Recency: lower is better -> invert bins
    df['r_score'] = pd.qcut(df['recency_days'].rank(method='first'), q=r_bins, labels=False, duplicates='drop')
    # Because qcut labels 0.., we want higher score for more recent (smaller recency_days)
    df['r_score'] = (r_bins - df['r_score']).astype(int)
    df['f_score'] = pd.qcut(df['frequency'].rank(method='first'), q=f_bins, labels=False, duplicates='drop').astype(int) + 1
    df['m_score'] = pd.qcut(df['monetary'].rank(method='first'), q=m_bins, labels=False, duplicates='drop').astype(int) + 1
    # Cap scores
    df['r_score'] = df['r_score'].clip(1, r_bins)
    df['f_score'] = df['f_score'].clip(1, f_bins)
    df['m_score'] = df['m_score'].clip(1, m_bins)
    df['rfm_score'] = df['r_score'].map(str) + df['f_score'].map(str) + df['m_score'].map(str)
    df['rfm_numeric'] = df['r_score']*100 + df['f_score']*10 + df['m_score']
    return df


def segment_map(rfm_df):
    # Simple mapping based on rfm_numeric thresholds
    if rfm_df.empty:
        return rfm_df
    df = rfm_df.copy()
    def label(row):
        r = row['r_score']; f = row['f_score']; m = row['m_score']
        # Champions: r in top2, f top2, m top2
        if r >=4 and f >=4 and m >=4:
            return 'Champion'
        # Loyal: f high
        if f >=4:
            return 'Loyal'
        # Potential Loyalist: r high & m mid
        if r >=4 and m >=3:
            return 'Potential Loyalist'
        # At Risk: r low (i.e., score small) but historically good (f>=3,m>=3)
        if r <=2 and f >=3 and m >=3:
            return 'At Risk'
        # Hibernating: r low and f low
        if r <=2 and f <=2:
            return 'Hibernating'
        # New customers: f ==1 and recency recent
        if f == 1 and r >=4:
            return 'New'
        return 'Other'
    df['segment'] = df.apply(label, axis=1)
    return df


def compute_clv(agg_df, clv_years=3.0):
    if agg_df.empty:
        return agg_df
    df = agg_df.copy()
    # purchase_frequency_per_month = frequency / tenure_months estimation using recency and frequency
    # Approximate tenure months as max(1, (recency_days + small) / 30) -- not perfect but works for short samples
    df['tenure_months'] = (df['recency_days'] / 30.0).replace(0,1).abs()
    df['purchase_frequency_per_month'] = (df['frequency'] / df['tenure_months']).replace([np.inf, -np.inf], 0).fillna(0)
    df['clv_simplified'] = (df['avg_order_value'] * df['purchase_frequency_per_month'] * 12 * clv_years).round(2)
    return df


def retention_and_churn(tx_df, ref_date=None, window_days=30):
    # Calculate basic retention and churn indicators per customer
    if tx_df.empty:
        return pd.DataFrame()
    tx_df['transaction_date'] = pd.to_datetime(tx_df['transaction_date'], errors='coerce')
    if ref_date is None:
        ref_date = tx_df['transaction_date'].max()
    # Last purchase date per customer
    last = tx_df.groupby('customer_id').transaction_date.max().reset_index().rename(columns={'transaction_date':'last_purchase_date'})
    last['days_since_last'] = (ref_date - last['last_purchase_date']).dt.days
    # churn indicator: no purchase in last window_days
    last['churn_flag'] = last['days_since_last'] > window_days
    # repeat vs one-time
    counts = tx_df.groupby('customer_id').transaction_id.nunique().reset_index().rename(columns={'transaction_id':'tx_count'})
    last = last.merge(counts, on='customer_id', how='left')
    last['repeat_customer'] = last['tx_count'] > 1
    return last


def main(input_dir: str, output_dir: str, recency_threshold_days: int, clv_years: float, churn_window: int):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # load
    orders = safe_read(input_dir / 'transformed_orders.csv', parse_dates=['order_date'])
    if orders.empty:
        orders = safe_read(input_dir / 'cleaned_orders.csv', parse_dates=['order_date'])
    tx = safe_read(input_dir / 'transformed_transactions.csv', parse_dates=['transaction_date'])
    if tx.empty:
        tx = safe_read(input_dir / 'cleaned_transactions.csv', parse_dates=['transaction_date'])

    customers = safe_read(input_dir / 'transformed_customers.csv', parse_dates=['signup_date'])
    if customers.empty:
        customers = safe_read(input_dir / 'cleaned_customers.csv', parse_dates=['signup_date'])

    # RFM for orders (numeric customer_id)
    rfm_orders = rfm_table(orders, id_col='customer_id', date_col='order_date', amount_col='total_amount', quantity_col='quantity')
    rfm_orders = rfm_score(rfm_orders)
    rfm_orders = segment_map(rfm_orders)
    rfm_orders = compute_clv(rfm_orders, clv_years=clv_years)
    rfm_orders['is_active_recent'] = rfm_orders['recency_days'] <= recency_threshold_days
    rfm_orders.to_csv(output_dir / 'customer_rfm_orders.csv', index=False)
    rfm_orders[['customer_id','r_score','f_score','m_score','rfm_score','segment','clv_simplified','is_active_recent']].to_csv(output_dir / 'customer_segments_orders.csv', index=False)

    # RFM for transactions (Cxxxx)
    rfm_tx = rfm_table(tx, id_col='customer_id', date_col='transaction_date', amount_col='total_amount', quantity_col='quantity')
    rfm_tx = rfm_score(rfm_tx)
    rfm_tx = segment_map(rfm_tx)
    rfm_tx = compute_clv(rfm_tx, clv_years=clv_years)
    rfm_tx['is_active_recent'] = rfm_tx['recency_days'] <= recency_threshold_days
    rfm_tx.to_csv(output_dir / 'customer_rfm_transactions.csv', index=False)
    rfm_tx[['customer_id','r_score','f_score','m_score','rfm_score','segment','clv_simplified','is_active_recent']].to_csv(output_dir / 'customer_segments_transactions.csv', index=False)

    # Retention & churn indicators from transactions
    retention = retention_and_churn(tx, ref_date=None, window_days=churn_window)
    retention.to_csv(output_dir / 'customer_retention_churn_transactions.csv', index=False)

    # Summary statistics
    summary = {}
    summary['total_customers_orders'] = int(rfm_orders['customer_id'].nunique()) if not rfm_orders.empty else 0
    summary['total_customers_transactions'] = int(rfm_tx['customer_id'].nunique()) if not rfm_tx.empty else 0
    summary['repeat_rate_orders'] = float((rfm_orders['frequency']>1).sum() / len(rfm_orders)) if len(rfm_orders)>0 else np.nan
    summary['repeat_rate_transactions'] = float((rfm_tx['frequency']>1).sum() / len(rfm_tx)) if len(rfm_tx)>0 else np.nan
    summary['active_customers_recent_orders'] = int(rfm_orders['is_active_recent'].sum()) if not rfm_orders.empty else 0
    summary['active_customers_recent_transactions'] = int(rfm_tx['is_active_recent'].sum()) if not rfm_tx.empty else 0

    pd.DataFrame([summary]).to_csv(output_dir / 'customer_analytics_summary.csv', index=False)

    # Generate human-readable report
    report_lines = []
    report_lines.append('# Customer Analytics Report\n')
    report_lines.append('This report contains RFM analysis, segmentation, CLV (simplified), retention and churn indicators.\n')
    report_lines.append('## Summary\n')
    for k,v in summary.items():
        report_lines.append(f'- {k}: {v}\n')
    report_lines.append('\n')

    report_lines.append('## RFM Segments (orders)\n')
    if not rfm_orders.empty:
        seg_counts = rfm_orders['segment'].value_counts()
        for s,c in seg_counts.items():
            report_lines.append(f'- {s}: {c} customers\n')
    else:
        report_lines.append('- No order-based customers found.\n')

    report_lines.append('\n## RFM Segments (transactions)\n')
    if not rfm_tx.empty:
        seg_counts_tx = rfm_tx['segment'].value_counts()
        for s,c in seg_counts_tx.items():
            report_lines.append(f'- {s}: {c} customers\n')
    else:
        report_lines.append('- No transaction-based customers found.\n')

    report_lines.append('\n## Churn & Retention (transactions)\n')
    if not retention.empty:
        churn_count = int(retention[retention['churn_flag']].shape[0])
        report_lines.append(f'- Customers flagged churn (no purchase in last {churn_window} days): {churn_count}\n')
        report_lines.append('\nSample churn snapshot (first 10 rows):\n')
        report_lines.append(retention.head(10).to_csv(index=False))
    else:
        report_lines.append('- No retention data (transactions empty).\n')

    report_lines.append('\n## Business implications and recommendations\n')
    report_lines.append('- Champions and Loyal customers should be prioritized for retention and referral incentives.\n')
    report_lines.append('- At Risk customers (good historical behavior but recent recency low) should be targeted with win-back campaigns.\n')
    report_lines.append('- Hibernating and One-time customers are candidates for introductory promotions to encourage a 2nd purchase.\n')
    report_lines.append('- For accurate LTV and retention modeling, map transaction customer IDs (Cxxxx) to canonical customer IDs and extend the time window.\n')
    report_lines.append('- Investigate churn drivers by segment (product preferences, store location, payment method).\n')

    (output_dir / 'documentation').mkdir(exist_ok=True)
    (output_dir / 'documentation' / 'customer_analytics_report.md').write_text('\n'.join(report_lines))

    logger.info('Customer analytics complete. Outputs written to %s', output_dir)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str, default='data/processed_data')
    parser.add_argument('--output-dir', type=str, default='analysis')
    parser.add_argument('--recency_threshold_days', type=int, default=90)
    parser.add_argument('--clv_years', type=float, default=3.0)
    parser.add_argument('--churn_window', type=int, default=90)
    args = parser.parse_args()
    main(args.input_dir, args.output_dir, args.recency_threshold_days, args.clv_years, args.churn_window)
