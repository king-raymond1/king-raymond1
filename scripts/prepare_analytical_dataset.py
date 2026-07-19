"""
Prepare analytical dataset for dashboarding

This script reads cleaned transactions/orders/customers/products (if available) from data/processed_data,
performs normalization, type-casting, validation, creates dimensions (date, customers, products), fact table (sales),
summary measures/aggregates, RFM, ABC classification and exports dashboard-ready CSVs under analysis/final_dataset/.

Usage:
    python scripts/prepare_analytical_dataset.py --input-dir data/processed_data --output-dir analysis/final_dataset --churn_days 90 --abc_thresholds 0.7 0.9

Outputs (csv):
- analysis/final_dataset/fact_sales.csv
- analysis/final_dataset/dim_date.csv
- analysis/final_dataset/dim_customers.csv
- analysis/final_dataset/dim_products.csv
- analysis/final_dataset/sales_by_day.csv
- analysis/final_dataset/sales_by_month.csv
- analysis/final_dataset/sales_by_store_payment.csv
- analysis/final_dataset/rfm_customers.csv
- analysis/final_dataset/abc_products.csv
- analysis/final_dataset/top_customers.csv
- analysis/final_dataset/top_products.csv
- documentation/final_dataset_readme.md

Notes:
- The script prefers transformed_* files but falls back to cleaned_*. Ensure cleaned_transactions.csv exists.
- It performs basic validation: total_amount vs quantity*unit_price and flags mismatches.
- If product cost (unit_cost) is present, computes profit and margin.
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def safe_read(path: Path, parse_dates=None):
    if not path.exists():
        logger.info('File not found: %s', path)
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=parse_dates, infer_datetime_format=True)


def normalize_colnames(df):
    df = df.copy()
    df.columns = [c.strip().lower().replace(' ', '_').replace('-', '_') for c in df.columns]
    return df


def ensure_types_sales(df):
    # Normalize expected columns and types for sales fact
    df = df.copy()
    # common columns
    for col in ['transaction_id','transaction_date','customer_id','product_id','product_name_clean','category','quantity','unit_price','total_amount','store_location','payment_method']:
        if col not in df.columns:
            df[col] = np.nan
    # types
    df['transaction_id'] = df['transaction_id'].astype(str)
    df['transaction_date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
    df['customer_id'] = df['customer_id'].astype(str)
    df['product_id'] = df['product_id'].astype(str)
    df['product_key'] = df['product_name_clean'].fillna(df.get('product_name','')).astype(str).str.strip().str.lower()
    df['category'] = df['category'].astype(str).str.strip().replace('nan','')
    df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0).astype(int)
    df['unit_price'] = pd.to_numeric(df['unit_price'], errors='coerce').fillna(0.0).astype(float)
    df['total_amount'] = pd.to_numeric(df['total_amount'], errors='coerce').fillna(0.0).astype(float)
    return df


def validate_totals(df):
    df = df.copy()
    df['expected_total'] = (df['quantity'] * df['unit_price']).round(2)
    df['total_mismatch'] = ~np.isclose(df['expected_total'], df['total_amount'], atol=0.01)
    mismatch_count = int(df['total_mismatch'].sum())
    logger.info('Total mismatches (quantity*unit_price != total_amount): %d', mismatch_count)
    return df


def build_date_dim(dates):
    # dates: iterable of pd.Timestamp or datetime.date
    s = pd.Series(pd.to_datetime(list(set(dates))).astype('datetime64[ns]'))
    s = s.dropna().sort_values()
    df = pd.DataFrame({'date': s.dt.date})
    df['date'] = pd.to_datetime(df['date'])
    df['year'] = df['date'].dt.year
    df['quarter'] = df['date'].dt.to_period('Q').astype(str)
    df['month'] = df['date'].dt.month
    df['month_name'] = df['date'].dt.strftime('%b')
    df['day'] = df['date'].dt.day
    df['weekday'] = df['date'].dt.weekday
    df['weekday_name'] = df['date'].dt.strftime('%a')
    df['is_weekend'] = df['weekday'].isin([5,6])
    df['year_month'] = df['date'].dt.to_period('M').dt.to_timestamp()
    return df.sort_values('date')


def rfm_table(tx, id_col='customer_id', date_col='transaction_date', amount_col='total_amount'):
    tx = tx.copy()
    tx[date_col] = pd.to_datetime(tx[date_col], errors='coerce')
    ref_date = tx[date_col].max()
    agg = tx.groupby(id_col).agg(
        recency_date=(date_col,'max'),
        frequency=(date_col,'count'),
        monetary=(amount_col,'sum')
    ).reset_index()
    agg['recency_days'] = (ref_date - agg['recency_date']).dt.days
    agg['avg_order_value'] = (agg['monetary'] / agg['frequency']).round(2)
    # scoring
    agg['r_score'] = pd.qcut(agg['recency_days'].rank(method='first'), q=5, labels=False, duplicates='drop')
    agg['r_score'] = (5 - agg['r_score']).astype(int)
    agg['f_score'] = pd.qcut(agg['frequency'].rank(method='first'), q=5, labels=False, duplicates='drop').astype(int) + 1
    agg['m_score'] = pd.qcut(agg['monetary'].rank(method='first'), q=5, labels=False, duplicates='drop').astype(int) + 1
    agg[['r_score','f_score','m_score']] = agg[['r_score','f_score','m_score']].clip(1,5)
    agg['rfm_score'] = agg['r_score'].map(str) + agg['f_score'].map(str) + agg['m_score'].map(str)
    return agg


def abc_products(prod_df, thresholds=(0.7,0.9)):
    df = prod_df.copy().sort_values('total_revenue', ascending=False)
    df['cum_revenue'] = df['total_revenue'].cumsum()
    total = df['total_revenue'].sum()
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


def main(input_dir: str, output_dir: str, churn_days: int, abc_thresholds):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_doc_dir = Path('documentation')
    analysis_doc_dir.mkdir(parents=True, exist_ok=True)

    # Read inputs (prefer transformed_*, else cleaned_*)
    tx_path = input_dir / 'transformed_transactions.csv'
    if not tx_path.exists():
        tx_path = input_dir / 'cleaned_transactions.csv'
    tx = safe_read(tx_path, parse_dates=['transaction_date'])
    if tx.empty:
        logger.error('No transactions file found in %s. Provide cleaned_transactions.csv', input_dir)
        return
    orders_path = input_dir / 'transformed_orders.csv'
    if not orders_path.exists():
        orders_path = input_dir / 'cleaned_orders.csv'
    orders = safe_read(orders_path, parse_dates=['order_date'])
    products_path = input_dir / 'transformed_products.csv'
    if not products_path.exists():
        products_path = input_dir / 'cleaned_products.csv'
    products = safe_read(products_path)
    customers_path = input_dir / 'transformed_customers.csv'
    if not customers_path.exists():
        customers_path = input_dir / 'cleaned_customers.csv'
    customers = safe_read(customers_path, parse_dates=['signup_date'])

    # Normalize column names to snake_case
    tx = normalize_colnames(tx)
    orders = normalize_colnames(orders)
    products = normalize_colnames(products)
    customers = normalize_colnames(customers)

    # Prepare fact sales from transactions (primary source of revenue)
    tx = ensure_types_sales(tx)
    tx = validate_totals(tx)

    # If orders exist and include order-level fields, try to append orders rows not present in transactions (left as optional)
    # We'll not duplicate: prefer transactions as truth for payments. If orders have unique order_id not in tx, append minimal rows.
    if not orders.empty:
        orders = normalize_colnames(orders)
        # prefer order_date -> transaction_date aliasing
        if 'order_date' in orders.columns:
            orders['transaction_date'] = orders['order_date']
        orders = ensure_types_sales(orders)
        # find orders not in tx by order_id if present
        if 'order_id' in orders.columns and 'transaction_id' in tx.columns:
            missing_orders = orders[~orders['order_id'].astype(str).isin(tx['transaction_id'].astype(str))]
            if not missing_orders.empty:
                logger.info('Appending %d orders not present in transactions to fact_sales', len(missing_orders))
                # map order_id to transaction_id field name for consistency
                missing_orders['transaction_id'] = missing_orders['order_id'].astype(str)
                # append
                tx = pd.concat([tx, missing_orders[tx.columns]], ignore_index=True, sort=False).fillna('')

    # Build dim_date
    date_dim = build_date_dim(tx['transaction_date'].dropna().dt.date)
    date_dim.to_csv(output_dir / 'dim_date.csv', index=False)

    # Build fact_sales with standardized columns
    fact_cols = ['transaction_id','transaction_date','customer_id','product_id','product_key','category','quantity','unit_price','total_amount','expected_total','total_mismatch','store_location','payment_method']
    for c in fact_cols:
        if c not in tx.columns:
            tx[c] = np.nan
    fact_sales = tx[fact_cols].copy()
    # cast date to iso
    fact_sales['transaction_date'] = pd.to_datetime(fact_sales['transaction_date'])
    # add derived measures
    fact_sales['year_month'] = fact_sales['transaction_date'].dt.to_period('M').dt.to_timestamp()
    fact_sales['year_week'] = fact_sales['transaction_date'].dt.to_period('W').dt.start_time
    # profit/margin if unit_cost present
    if 'unit_cost' in tx.columns:
        fact_sales['unit_cost'] = pd.to_numeric(tx['unit_cost'], errors='coerce').fillna(0.0)
        fact_sales['total_cost'] = (fact_sales['unit_cost'] * fact_sales['quantity']).round(2)
        fact_sales['profit'] = (fact_sales['total_amount'] - fact_sales['total_cost']).round(2)
        # margin percent
        fact_sales['margin_pct'] = (fact_sales['profit'] / fact_sales['total_amount'].replace({0:np.nan})).round(4)
    else:
        fact_sales['unit_cost'] = np.nan
        fact_sales['total_cost'] = np.nan
        fact_sales['profit'] = np.nan
        fact_sales['margin_pct'] = np.nan

    # Save fact_sales
    fact_sales.to_csv(output_dir / 'fact_sales.csv', index=False)

    # Build dim_customers
    if not customers.empty:
        customers = normalize_colnames(customers)
        # ensure id column
        if 'customer_id' not in customers.columns and 'id' in customers.columns:
            customers = customers.rename(columns={'id':'customer_id'})
    # build customer aggregates from fact_sales
    cust_agg = fact_sales.groupby('customer_id').agg(total_revenue=('total_amount','sum'), orders_count=('transaction_id','nunique'), first_purchase_date=('transaction_date','min'), last_purchase_date=('transaction_date','max')).reset_index()
    # merge with customer profile if available
    if not customers.empty and 'customer_id' in customers.columns:
        dim_customers = customers.merge(cust_agg, on='customer_id', how='right')
    else:
        dim_customers = cust_agg
    # compute recency/tenure
    ref_date = fact_sales['transaction_date'].max()
    dim_customers['days_since_last'] = (pd.to_datetime(ref_date) - pd.to_datetime(dim_customers['last_purchase_date'])).dt.days
    dim_customers['customer_tenure_days'] = (pd.to_datetime(dim_customers['last_purchase_date']) - pd.to_datetime(dim_customers['first_purchase_date'])).dt.days.fillna(0)
    dim_customers.to_csv(output_dir / 'dim_customers.csv', index=False)

    # Build dim_products
    prod_agg = fact_sales.groupby('product_key').agg(product_id=('product_id','first'), category=('category','first'), unit_price=('unit_price','mean'), units_sold=('quantity','sum'), total_revenue=('total_amount','sum')).reset_index()
    abc = abc_products(prod_agg.rename(columns={'total_revenue':'total_revenue'}), thresholds=tuple(abc_thresholds))
    prod_dim = prod_agg.merge(abc[['prod_key','abc_class']] if 'prod_key' in abc.columns else abc[['prod_key','abc_class']].rename(columns={'prod_key':'product_key'}), left_on='product_key', right_on='prod_key', how='left') if 'prod_key' in abc.columns else prod_agg
    # simpler: attach abc by product_key
    if 'product_key' in prod_agg.columns:
        abc_by_key = abc.rename(columns={'prod_key':'product_key'})[['product_key','abc_class']]
        prod_dim = prod_agg.merge(abc_by_key, on='product_key', how='left')
    prod_dim.to_csv(output_dir / 'dim_products.csv', index=False)

    # Aggregates for dashboard
    sales_by_day = fact_sales.groupby(fact_sales['transaction_date'].dt.date).agg(revenue=('total_amount','sum'), units=('quantity','sum'), transactions=('transaction_id','nunique')).reset_index().rename(columns={'transaction_date':'date'})
    sales_by_day['date'] = pd.to_datetime(sales_by_day['date'])
    sales_by_day.to_csv(output_dir / 'sales_by_day.csv', index=False)

    sales_by_month = fact_sales.groupby('year_month').agg(revenue=('total_amount','sum'), units=('quantity','sum'), transactions=('transaction_id','nunique')).reset_index()
    sales_by_month['year_month'] = pd.to_datetime(sales_by_month['year_month'])
    sales_by_month.to_csv(output_dir / 'sales_by_month.csv', index=False)

    sales_by_store_payment = fact_sales.groupby(['store_location','payment_method']).agg(revenue=('total_amount','sum'), transactions=('transaction_id','nunique'), units=('quantity','sum')).reset_index()
    sales_by_store_payment.to_csv(output_dir / 'sales_by_store_payment.csv', index=False)

    # RFM
    rfm = rfm_table(fact_sales)
    rfm.to_csv(output_dir / 'rfm_customers.csv', index=False)

    # ABC products
    abc_prod = abc_products(prod_agg.rename(columns={'total_revenue':'total_revenue'}), thresholds=tuple(abc_thresholds))
    abc_prod.to_csv(output_dir / 'abc_products.csv', index=False)

    # Top 20% customers (by revenue)
    custs = dim_customers.copy()
    custs_sorted = custs.sort_values('total_revenue', ascending=False)
    n_top = max(1, int(len(custs_sorted) * 0.2))
    top_customers = custs_sorted.head(n_top)[['customer_id','total_revenue','orders_count']]
    top_customers.to_csv(output_dir / 'top_customers.csv', index=False)

    # Top 20% products by revenue
    prods_sorted = prod_agg.sort_values('total_revenue', ascending=False)
    n_prod_top = max(1, int(len(prods_sorted) * 0.2))
    top_products = prods_sorted.head(n_prod_top)[['product_key','units_sold','total_revenue']]
    top_products.to_csv(output_dir / 'top_products.csv', index=False)

    # Validation summary
    validation = {
        'total_transactions_rows': int(len(fact_sales)),
        'total_customers': int(dim_customers.shape[0]),
        'total_products': int(prod_dim.shape[0] if 'prod_dim' in locals() else prod_agg.shape[0]),
        'mismatched_totals': int(fact_sales['total_mismatch'].sum())
    }
    pd.DataFrame([validation]).to_csv(output_dir / 'validation_summary.csv', index=False)

    # README
    readme = []
    readme.append('# Final analytical dataset for dashboarding')
    readme.append('\nLocation: analysis/final_dataset/')
    readme.append('\nFiles:')
    for f in ['fact_sales.csv','dim_date.csv','dim_customers.csv','dim_products.csv','sales_by_day.csv','sales_by_month.csv','sales_by_store_payment.csv','rfm_customers.csv','abc_products.csv','top_customers.csv','top_products.csv','validation_summary.csv']:
        readme.append(f'- {f}')
    readme.append('\nNotes:')
    readme.append('- Column names are snake_case and types are optimized (dates parsed, numeric columns as float/int).')
    readme.append('- Measures are revenue (total_amount), units (quantity), transactions (unique transaction_id), average order value (revenue / transactions).')
    readme.append('- Dimensions: dim_date, dim_customers, dim_products. Use these for joins in your dashboard tool.')
    readme.append('- Calculated fields: expected_total (quantity*unit_price), total_mismatch flag, profit/margin if unit_cost present, RFM scores, ABC class for products.')
    readme.append('- Validation: validation_summary.csv shows row counts and mismatches detected.')

    (analysis_doc_dir / 'final_dataset_readme.md').write_text('\n'.join(readme))

    logger.info('Final analytical dataset prepared at %s', output_dir)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str, default='data/processed_data')
    parser.add_argument('--output-dir', type=str, default='analysis/final_dataset')
    parser.add_argument('--churn_days', type=int, default=90)
    parser.add_argument('--abc_thresholds', nargs=2, type=float, default=[0.7,0.9])
    args = parser.parse_args()
    main(args.input_dir, args.output_dir, args.churn_days, args.abc_thresholds)
