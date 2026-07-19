"""
Create a master analytical dataset by merging cleaned/transformed customers, products, orders, and transactions.

The script performs:
- Proper joins (explainable) between datasets
- Left joins for preservation of primary transactional rows
- Mapping attempts for transactions -> products via product_name_key
- Adds provenance columns and validation summary

Usage:
    python scripts/create_master_dataset.py --input-dir data/processed_data --output data/processed_data/master_analytics_dataset.csv

Outputs:
- data/processed_data/master_analytics_dataset.csv
- documentation/merge_report.md (human-readable explanation and validation)
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np


def load_inputs(input_dir: Path):
    customers = pd.read_csv(input_dir / 'cleaned_customers.csv', parse_dates=['signup_date'])
    products = pd.read_csv(input_dir / 'cleaned_products.csv')
    orders = pd.read_csv(input_dir / 'cleaned_orders.csv', parse_dates=['order_date'])
    transactions = pd.read_csv(input_dir / 'cleaned_transactions.csv', parse_dates=['transaction_date'])
    return customers, products, orders, transactions


def build_master(customers, products, orders, transactions):
    # Normalize column names and prepare order-level dataframe
    orders_df = orders.copy()
    orders_df['event_type'] = 'order'
    orders_df['event_id'] = orders_df['order_id'].astype(str)
    orders_df['event_date'] = orders_df['order_date']
    # For schema consistency, add tx-specific columns to orders
    orders_df['transaction_id'] = pd.NA
    orders_df['tx_product_id'] = pd.NA
    orders_df['tx_product_name'] = pd.NA
    orders_df['store_location'] = pd.NA
    orders_df['payment_method'] = pd.NA
    # Rename some columns to master schema
    orders_master = orders_df[['event_id','event_type','event_date','order_id','transaction_id','customer_id','product_id','tx_product_id','product_name_product','tx_product_name','quantity','unit_price','total_amount','price','expected_total','order_amount_mismatch','store_location','payment_method']]
    orders_master = orders_master.rename(columns={
        'order_id':'order_id',
        'product_name_product':'product_name'
    })

    # Prepare transaction-level dataframe
    tx_df = transactions.copy()
    tx_df['event_type'] = 'transaction'
    tx_df['event_id'] = tx_df['transaction_id']
    tx_df['event_date'] = tx_df['transaction_date']
    # Map transaction product_id_mapped if exists
    if 'product_id_mapped' in tx_df.columns:
        tx_df['product_id_mapped'] = tx_df['product_id_mapped']
    else:
        tx_df['product_id_mapped'] = pd.NA
    # Standardize column names to match orders_master
    tx_master = tx_df[['event_id','event_type','event_date','transaction_id','transaction_id','customer_id','product_id','product_id_mapped','product_name','category','quantity','unit_price','total_amount','product_price_mapped','expected_total','tx_amount_mismatch','store_location','payment_method']]
    tx_master = tx_master.rename(columns={
        'transaction_id':'transaction_id',
        'product_id_mapped':'tx_product_id',
        'product_price_mapped':'price'
    })

    # Align columns between orders_master and tx_master by creating a superset schema
    master_cols = [
        'event_id','event_type','event_date','order_id','transaction_id','customer_id','tx_customer_id',
        'product_id','tx_product_id','product_name','category','quantity','unit_price','total_amount','price',
        'expected_total','order_amount_mismatch','tx_amount_mismatch','store_location','payment_method',
        'customer_first_name','customer_last_name','country'
    ]

    # Build wrapped orders_master with tx_customer_id placeholder
    orders_master = orders_master.rename(columns={'customer_id':'customer_id'})
    orders_master['tx_customer_id'] = pd.NA
    # Fill missing columns if any
    for c in master_cols:
        if c not in orders_master.columns:
            orders_master[c] = pd.NA
    for c in master_cols:
        if c not in tx_master.columns:
            tx_master[c] = pd.NA
    # For tx_master, create tx_customer_id from transactions.customer_id and ensure customer_id numeric empty
    tx_master['tx_customer_id'] = tx_master['customer_id']
    tx_master['customer_id'] = pd.NA
    # Ensure ordering of columns
    orders_master = orders_master[master_cols]
    tx_master = tx_master[master_cols]

    # Union the two datasets (orders first then transactions)
    master_df = pd.concat([orders_master, tx_master], ignore_index=True, sort=False)

    # Join customer metadata where customer_id exists (orders only)
    customers_small = customers[['customer_id','first_name','last_name','country']]
    master_df = master_df.merge(customers_small, on='customer_id', how='left')
    master_df = master_df.rename(columns={'first_name':'customer_first_name','last_name':'customer_last_name'})

    # Post-processing: consistent dtypes
    master_df['quantity'] = pd.to_numeric(master_df['quantity'], errors='coerce').fillna(0).astype(int)
    master_df['unit_price'] = pd.to_numeric(master_df['unit_price'], errors='coerce')
    master_df['total_amount'] = pd.to_numeric(master_df['total_amount'], errors='coerce')
    master_df['price'] = pd.to_numeric(master_df['price'], errors='coerce')

    return master_df


def validate_master(master_df, customers, products, orders, transactions):
    report = []
    # Row counts
    report.append(('orders_rows', len(orders)))
    report.append(('transactions_rows', len(transactions)))
    report.append(('master_rows', len(master_df)))
    # Check union size
    expected = len(orders) + len(transactions)
    report.append(('expected_union', expected))
    report.append(('union_match', len(master_df) == expected))
    # Referential integrity checks
    # Orders customer IDs present in master and customers
    orders_customers_missing = set(orders['customer_id'].dropna().astype(int)) - set(customers['customer_id'].dropna().astype(int))
    report.append(('orders_customers_missing_count', len(orders_customers_missing)))
    # Orders products missing in products
    orders_products_missing = set(orders['product_id'].dropna().astype(int)) - set(products['product_id'].dropna().astype(int))
    report.append(('orders_products_missing_count', len(orders_products_missing)))
    # Transactions mapped product ids missing
    if 'product_id_mapped' in transactions.columns:
        mapped = transactions['product_id_mapped'].dropna().unique()
        missing_mapped = [m for m in mapped if m not in products['product_id'].astype(str).values and m is not None]
        report.append(('transactions_mapped_products_missing_count', len(missing_mapped)))
    else:
        report.append(('transactions_mapped_products_missing_count', 'no_mapped_column'))

    # Monetary mismatches
    order_mismatches = orders[orders['order_amount_mismatch'] == True]
    tx_mismatches = transactions[transactions['tx_amount_mismatch'] == True] if 'tx_amount_mismatch' in transactions.columns else pd.DataFrame()
    report.append(('order_amount_mismatch_count', len(order_mismatches)))
    report.append(('tx_amount_mismatch_count', len(tx_mismatches)))

    return report


def write_report(report, out_path: Path):
    lines = ['# Master Merge Validation Report\n']
    lines.append('Summary of validation checks after building master analytical dataset.\n')
    for k,v in report:
        lines.append(f'- {k}: {v}\n')
    out_path.write_text('\n'.join(lines))


def main(input_dir: str, output: str):
    input_dir = Path(input_dir)
    output = Path(output)
    customers, products, orders, transactions = load_inputs(input_dir)
    master_df = build_master(customers, products, orders, transactions)
    master_df.to_csv(output, index=False)
    report = validate_master(master_df, customers, products, orders, transactions)
    write_report(report, Path('documentation/merge_report.md'))
    print('Master dataset written to', output)
    print('Validation report written to documentation/merge_report.md')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str, default='data/processed_data')
    parser.add_argument('--output', type=str, default='data/processed_data/master_analytics_dataset.csv')
    args = parser.parse_args()
    main(args.input_dir, args.output)
