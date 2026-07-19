"""
Orchestrator script to run the full pipeline:
- Loads CSVs
- Validates schemas
- Performs cleaning and merging
- Produces analysis tables and visualizations
- Writes cleaned datasets and figures to outputs
"""

import argparse
import logging
from pathlib import Path
import pandas as pd

from src.utils import setup_logging, ensure_dir
from src.data_loader import load_csv, validate_columns, summarize_df
from src.cleaning import normalize_transactions_products, standardize_orders_products
from src.analysis import top_products_by_revenue, top_customers_by_revenue, revenue_by_category, transactions_time_series
from src.visualization import bar_plot_top_products, interactive_time_series

logger = setup_logging()

def main(data_dir: str, output_dir: str):
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    ensure_dir(output_dir)
    ensure_dir(output_dir / "figures")

    # 1) Load datasets (with safe date parsing where appropriate)
    customers = load_csv(data_dir / "customerscsv.csv", parse_dates=["signup_date"])
    products = load_csv(data_dir / "productscsv.csv")
    orders = load_csv(data_dir / "orderscsv.csv", parse_dates=["order_date"])
    transactions = load_csv(data_dir / "transactions_2025_01_27.csv", parse_dates=["transaction_date"])

    # 2) Quick summaries for initial inspection
    summarize_df(customers, name="customers")
    summarize_df(products, name="products")
    summarize_df(orders, name="orders")
    summarize_df(transactions, name="transactions")

    # 3) Validate required columns (explicit checks)
    customers_expected = ["customer_id", "first_name", "last_name", "country", "signup_date"]
    products_expected = ["product_id", "product_name", "category", "price"]
    orders_expected = ["order_id", "customer_id", "product_id", "order_date", "quantity", "total_amount"]
    transactions_expected = ["transaction_id", "transaction_date", "customer_id", "product_id", "product_name",
                             "category", "quantity", "unit_price", "total_amount", "store_location", "payment_method"]

    assert validate_columns(customers, customers_expected, "customers")
    assert validate_columns(products, products_expected, "products")
    assert validate_columns(orders, orders_expected, "orders")
    assert validate_columns(transactions, transactions_expected, "transactions")

    # 4) Clean / Normalize
    # 4a) Orders + products merging and validation
    orders_products = standardize_orders_products(orders, products)
    # Save the merged table
    orders_products.to_csv(output_dir / "cleaned_orders_products.csv", index=False)
    logger.info("Wrote cleaned orders+products to cleaned_orders_products.csv")

    # 4b) Transactions normalization
    transactions_clean = normalize_transactions_products(transactions, product_name_col="product_name")
    transactions_clean.to_csv(output_dir / "cleaned_transactions.csv", index=False)
    logger.info("Wrote cleaned transactions to cleaned_transactions.csv")

    # 5) Analysis / Aggregations
    top_prod = top_products_by_revenue(orders_products, top_n=10)
    top_prod.to_csv(output_dir / "top_products_by_revenue.csv", index=False)
    logger.info("Saved top products table.")

    top_cust = top_customers_by_revenue(orders_products, customers, top_n=10)
    top_cust.to_csv(output_dir / "top_customers_by_revenue.csv", index=False)
    logger.info("Saved top customers table.")

    cat_rev = revenue_by_category(orders_products)
    cat_rev.to_csv(output_dir / "revenue_by_category.csv", index=False)
    logger.info("Saved revenue by category.")

    # 6) Transactions time series
    daily_ts = transactions_time_series(transactions_clean, date_col="transaction_date")
    daily_ts.to_csv(output_dir / "transactions_daily_timeseries.csv", index=False)
    logger.info("Saved transactions daily time series.")

    # 7) Visualizations
    # static bar chart of top products (from orders)
    if not top_prod.empty:
        bar_plot_top_products(top_prod.rename(columns={"product_name": "product_name", "revenue": "revenue"}),
                              output_path=output_dir / "figures" / "top_products_revenue.png",
                              title="Top Products by Revenue (Orders Dataset)")
    # interactive time series for transactions
    interactive_time_series(daily_ts, x_col="date", y_col="revenue",
                            output_html=output_dir / "figures" / "transactions_daily_revenue.html",
                            title="Daily Revenue (Transactions Dataset)")

    logger.info("Pipeline complete. Outputs available in %s", output_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run sales analytics pipeline")
    parser.add_argument("--data-dir", type=str, required=True, help="Directory containing CSV files")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to write outputs")
    args = parser.parse_args()
    main(args.data_dir, args.output_dir)
