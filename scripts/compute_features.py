"""
Compute analytical customer and product features for modeling and reporting.

Features generated (examples):
- Customer-level (orders dataset):
  - total_revenue, orders_count, avg_order_value (AOV), purchase_frequency (orders per month),
    recency_days, tenure_days, days_since_last_purchase, customer_lifetime_value (CLV, simplified)
  - avg_basket_size (avg quantity per order), revenue_per_customer
- Customer-level (transactions dataset, per Cxxxx id): similar set computed from transactions
- Product-level:
  - revenue_per_product (sum across orders + transactions by normalized product_name)
  - units_sold, avg_unit_price

Notes/assumptions:
- Profit and profit_margin cannot be computed (no unit_cost data). Columns left NaN and instructions provided.
- CLV here is a simplified estimate: average_order_value * purchase_frequency * expected_customer_lifespan_years.
  We include 3 years as a configurable default; set to business-appropriate value.

Usage:
    python scripts/compute_features.py --input-dir data/processed_data --output-dir data/processed_data

Outputs (CSV):
- data/processed_data/features_customers_orders.csv
- data/processed_data/features_customers_transactions.csv
- data/processed_data/revenue_per_product.csv
- data/processed_data/features_summary.csv (high-level)

"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def safe_read(path: Path, parse_dates=None):
    if not path.exists():
        logger.warning("File not found: %s", path)
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=parse_dates, infer_datetime_format=True)


def months_between(start, end):
    return (end - start).days / 30.0 if pd.notna(start) and pd.notna(end) else np.nan


def compute_customer_features_from_orders(orders: pd.DataFrame, customers: pd.DataFrame, output_dir: Path, clv_lifespan_years=3.0):
    if orders.empty:
        logger.warning('Orders dataframe empty - no customer features from orders will be created')
        return pd.DataFrame()

    # ensure dates
    orders['order_date'] = pd.to_datetime(orders['order_date'], errors='coerce')

    # group by customer_id
    grp = orders.groupby('customer_id')
    customers_feat = grp.agg(
        orders_count=('order_id','nunique'),
        total_revenue=('total_amount','sum'),
        total_quantity=('quantity','sum'),
        first_order_date=('order_date','min'),
        last_order_date=('order_date','max')
    ).reset_index()

    customers_feat['avg_order_value'] = (customers_feat['total_revenue'] / customers_feat['orders_count']).round(2)
    customers_feat['avg_basket_size'] = (customers_feat['total_quantity'] / customers_feat['orders_count']).round(2)

    # tenure and recency
    overall_ref = orders['order_date'].max()
    customers_feat['tenure_days'] = (customers_feat['last_order_date'] - customers_feat['first_order_date']).dt.days
    customers_feat['recency_days'] = (overall_ref - customers_feat['last_order_date']).dt.days
    customers_feat['days_since_last_purchase'] = customers_feat['recency_days']

    # purchase frequency: orders per month (using tenure as active months; if tenure 0 use 1 month)
    customers_feat['tenure_months'] = customers_feat.apply(lambda r: max(1.0, months_between(r['first_order_date'], r['last_order_date'])), axis=1)
    customers_feat['purchase_frequency_per_month'] = (customers_feat['orders_count'] / customers_feat['tenure_months']).round(4)

    # CLV (simplified): avg_order_value * purchase_frequency_per_month * 12 * lifespan_years
    customers_feat['clv_simplified'] = (customers_feat['avg_order_value'] * customers_feat['purchase_frequency_per_month'] * 12 * clv_lifespan_years).round(2)

    # revenue per customer is total_revenue
    customers_feat['revenue_per_customer'] = customers_feat['total_revenue'].round(2)

    # add customer metadata (left join)
    if not customers.empty and 'customer_id' in customers.columns:
        out = customers_feat.merge(customers[['customer_id','first_name','last_name','country','signup_date']], on='customer_id', how='left')
    else:
        out = customers_feat

    # placeholder for profit margin (requires cost)
    out['profit_margin'] = np.nan

    out_path = output_dir / 'features_customers_orders.csv'
    out.to_csv(out_path, index=False)
    logger.info('Wrote customer features (orders) to %s', out_path)
    return out


def compute_customer_features_from_transactions(transactions: pd.DataFrame, output_dir: Path, ref_date=None, clv_lifespan_years=3.0):
    if transactions.empty:
        logger.warning('Transactions dataframe empty - no customer features from transactions will be created')
        return pd.DataFrame()

    transactions['transaction_date'] = pd.to_datetime(transactions['transaction_date'], errors='coerce')
    # use transactions.customer_id which are Cxxxx codes
    grp = transactions.groupby('customer_id')
    tx_feat = grp.agg(
        tx_count=('transaction_id','nunique'),
        total_revenue=('total_amount','sum'),
        total_quantity=('quantity','sum'),
        first_tx_date=('transaction_date','min'),
        last_tx_date=('transaction_date','max')
    ).reset_index()
    tx_feat['avg_tx_value'] = (tx_feat['total_revenue'] / tx_feat['tx_count']).round(2)
    tx_feat['avg_basket_size'] = (tx_feat['total_quantity'] / tx_feat['tx_count']).round(2)

    if ref_date is None:
        ref_date = transactions['transaction_date'].max()
    tx_feat['recency_days'] = (ref_date - tx_feat['last_tx_date']).dt.days
    tx_feat['tenure_days'] = (tx_feat['last_tx_date'] - tx_feat['first_tx_date']).dt.days
    tx_feat['tenure_months'] = tx_feat.apply(lambda r: max(1.0, months_between(r['first_tx_date'], r['last_tx_date'])), axis=1)
    tx_feat['purchase_frequency_per_month'] = (tx_feat['tx_count'] / tx_feat['tenure_months']).round(4)
    tx_feat['clv_simplified'] = (tx_feat['avg_tx_value'] * tx_feat['purchase_frequency_per_month'] * 12 * clv_lifespan_years).round(2)
    tx_feat['revenue_per_customer'] = tx_feat['total_revenue'].round(2)
    tx_feat['profit_margin'] = np.nan

    out_path = output_dir / 'features_customers_transactions.csv'
    tx_feat.to_csv(out_path, index=False)
    logger.info('Wrote customer features (transactions) to %s', out_path)
    return tx_feat


def compute_revenue_per_product(orders: pd.DataFrame, transactions: pd.DataFrame, output_dir: Path):
    # Use normalized product name keys to aggregate across orders & transactions
    orders_prod = pd.DataFrame()
    if not orders.empty:
        # orders may have product_name_product or product_name
        if 'product_name_product' in orders.columns:
            orders['prod_key'] = orders['product_name_product'].astype(str).str.lower().str.replace(r'[^0-9a-zA-Z\s\-]', ' ', regex=True).str.replace(r'\s+', ' ', regex=True).str.strip()
            orders_prod = orders.groupby('prod_key').agg(units_sold_orders=('quantity','sum'), revenue_orders=('total_amount','sum')).reset_index()
        elif 'product_name' in orders.columns:
            orders['prod_key'] = orders['product_name'].astype(str).str.lower().str.replace(r'[^0-9a-zA-Z\s\-]', ' ', regex=True).str.replace(r'\s+', ' ', regex=True).str.strip()
            orders_prod = orders.groupby('prod_key').agg(units_sold_orders=('quantity','sum'), revenue_orders=('total_amount','sum')).reset_index()

    tx_prod = pd.DataFrame()
    if not transactions.empty:
        transactions['prod_key'] = transactions['product_name_clean'].astype(str).str.lower().str.replace(r'[^0-9a-zA-Z\s\-]', ' ', regex=True).str.replace(r'\s+', ' ', regex=True).str.strip()
        tx_prod = transactions.groupby('prod_key').agg(units_sold_tx=('quantity','sum'), revenue_tx=('total_amount','sum')).reset_index()

    # full outer join on prod_key
    if not orders_prod.empty or not tx_prod.empty:
        merged = pd.merge(orders_prod, tx_prod, on='prod_key', how='outer').fillna(0)
        merged['total_units_sold'] = merged['units_sold_orders'] + merged['units_sold_tx']
        merged['total_revenue'] = merged['revenue_orders'] + merged['revenue_tx']
        # compute avg_unit_price where possible
        merged['avg_unit_price'] = merged.apply(lambda r: (r['total_revenue'] / r['total_units_sold']) if r['total_units_sold']>0 else np.nan, axis=1).round(2)
    else:
        merged = pd.DataFrame(columns=['prod_key','total_units_sold','total_revenue','avg_unit_price'])

    out_path = output_dir / 'revenue_per_product.csv'
    merged.to_csv(out_path, index=False)
    logger.info('Wrote revenue per product to %s', out_path)
    return merged


def compute_order_and_basket_metrics(orders: pd.DataFrame, output_dir: Path):
    if orders.empty:
        logger.warning('Orders empty - skipping order/basket metrics')
        return pd.DataFrame()
    # Per order metrics already exist (quantity, total_amount)
    orders_metrics = orders[['order_id','customer_id','order_date','quantity','total_amount']].copy()
    orders_metrics['order_size'] = orders_metrics['quantity']
    orders_metrics['basket_value'] = orders_metrics['total_amount']
    out_path = output_dir / 'order_metrics.csv'
    orders_metrics.to_csv(out_path, index=False)
    logger.info('Wrote order metrics to %s', out_path)
    return orders_metrics


def summarize_features(features_orders, features_tx, revenue_prod, output_dir: Path):
    summary = {
        'customers_from_orders': int(len(features_orders)) if features_orders is not None else 0,
        'customers_from_transactions': int(len(features_tx)) if features_tx is not None else 0,
        'products_covered': int(len(revenue_prod)) if revenue_prod is not None else 0
    }
    out_path = output_dir / 'features_summary.csv'
    pd.DataFrame([summary]).to_csv(out_path, index=False)
    logger.info('Wrote features summary to %s', out_path)
    return summary


def main(input_dir: str, output_dir: str, clv_years: float):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    orders = safe_read(input_dir / 'transformed_orders.csv', parse_dates=['order_date'])
    if orders.empty:
        orders = safe_read(input_dir / 'cleaned_orders.csv', parse_dates=['order_date'])
    transactions = safe_read(input_dir / 'transformed_transactions.csv', parse_dates=['transaction_date'])
    if transactions.empty:
        transactions = safe_read(input_dir / 'cleaned_transactions.csv', parse_dates=['transaction_date'])
    customers = safe_read(input_dir / 'transformed_customers.csv', parse_dates=['signup_date'])
    if customers.empty:
        customers = safe_read(input_dir / 'cleaned_customers.csv', parse_dates=['signup_date'])
    products = safe_read(input_dir / 'transformed_products.csv')
    if products.empty:
        products = safe_read(input_dir / 'cleaned_products.csv')

    feats_orders = compute_customer_features_from_orders(orders, customers, output_dir, clv_lifespan_years=clv_years)
    feats_tx = compute_customer_features_from_transactions(transactions, output_dir, clv_lifespan_years=clv_years)
    revenue_prod = compute_revenue_per_product(orders, transactions, output_dir)
    order_metrics = compute_order_and_basket_metrics(orders, output_dir)
    summary = summarize_features(feats_orders, feats_tx, revenue_prod, output_dir)

    # Write human-readable documentation explaining each feature
    doc = output_dir.parent / 'documentation' / 'features.md'
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(FEATURES_DOC)
    logger.info('Wrote features documentation to %s', doc)

    logger.info('Feature generation complete. Outputs in %s', output_dir)


FEATURES_DOC = """
Analytical Features Generated

Customer-level (from Orders - numeric customer_id)
- orders_count: Number of unique orders for the customer. Useful for frequency measurement.
- total_revenue: Sum of total_amount across orders for the customer. Monetary value.
- total_quantity: Total units purchased across orders.
- avg_order_value (AOV): total_revenue / orders_count. Typical spend per order.
- avg_basket_size: total_quantity / orders_count. Typical number of items per order.
- first_order_date / last_order_date: temporal anchors for recency/tenure calculations.
- tenure_days: last_order_date - first_order_date.
- recency_days: reference_date (max order_date in dataset) - last_order_date. Also known as days since last purchase.
- purchase_frequency_per_month: orders_count / tenure_months (tenure in months). Provides a monthly frequency rate.
- clv_simplified: Simplified Customer Lifetime Value estimate computed as:
    clv = avg_order_value * purchase_frequency_per_month * 12 * expected_customer_lifespan_years
  This is an approximation and should be replaced with a more robust model when more data / margins available.
- revenue_per_customer: same as total_revenue.
- profit_margin: placeholder (NaN) until unit cost data is available.

Customer-level (from Transactions - Cxxxx customer_id)
- tx_count, total_revenue, avg_tx_value, avg_basket_size, recency_days, tenure_days, purchase_frequency_per_month, clv_simplified
- These metrics are computed on transaction customer ids (Cxxxx). To combine with orders-level customers, provide a mapping table to canonical customer ids.

Product-level
- total_units_sold: Sum of units sold across orders+transactions using normalized product_name keys.
- total_revenue: Sum of revenue across orders+transactions for the product key.
- avg_unit_price: total_revenue / total_units_sold (where units > 0).
- revenue_per_product: used for SKU prioritization and Pareto analysis.

Order-level / Basket-level
- order_size: number of items in the order (quantity).
- basket_value: total_amount for each order.

Profit / Margin
- profit and profit_margin: cannot be computed without cost/unit_cost data. Once available provide a product-level unit_cost or transaction-level cost to compute:
    profit_per_order = (unit_price - unit_cost) * quantity
    profit_margin = profit / revenue

Assumptions & Notes
- CLV uses a simplified deterministic formula that requires assumptions about customer lifespan; by default we use 3 years (configurable).
- Purchase frequency uses active tenure between first and last order; if a customer has only one order we use 1 month tenure to avoid division by zero.
- Transactions use a different customer id namespace (Cxxxx). Features computed from transactions are separate unless a mapping to canonical customers is provided.
- Normalization: product keys are normalized by lowercasing and removing non-alphanumeric characters before aggregation.

"""

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str, default='data/processed_data')
    parser.add_argument('--output-dir', type=str, default='data/processed_data')
    parser.add_argument('--clv-years', type=float, default=3.0, help='Assumed customer lifetime in years for simplified CLV calculation')
    args = parser.parse_args()
    main(args.input_dir, args.output_dir, args.clv_years)
