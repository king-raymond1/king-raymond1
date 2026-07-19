"""
Transform cleaned datasets to prepare them for analysis.

This script reads cleaned CSVs from data/processed_data, creates calculated columns, converts categorical variables,
normalizes text, creates time-based features (year, month, quarter, week, day, weekend, season), and prepares the
datasets for analysis. It writes transformed CSVs back to data/processed_data as transformed_*.csv.

Usage:
    pip install -r requirements.txt
    python scripts/transform_data.py --input-dir data/processed_data --output-dir data/processed_data

Notes:
- Profit calculations are not performed because cost data is not available in the provided datasets. Profit column is
  left as NaN and the script documents how to compute it if cost data becomes available.
- Customer age group is not applicable because the datasets do not contain date-of-birth or age. The script adds an
  'age_group' column with value 'unknown' to preserve schema compatibility.
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def season_from_month(month: int) -> str:
    """Map month number to season string."""
    if month in (12, 1, 2):
        return "Winter"
    if month in (3, 4, 5):
        return "Spring"
    if month in (6, 7, 8):
        return "Summer"
    if month in (9, 10, 11):
        return "Autumn"
    return None


def add_time_features(df: pd.DataFrame, date_col: str, prefix: str):
    """Add time-based features (year, month, quarter, week, day, weekday, is_weekend, season).
    Prefix each created column with the provided prefix to avoid name collisions.
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    # create features
    df[f"{prefix}_year"] = df[date_col].dt.year
    df[f"{prefix}_month"] = df[date_col].dt.month
    df[f"{prefix}_quarter"] = df[date_col].dt.to_period("Q").astype(str)
    # ISO week number
    # pandas >= 1.1: dt.isocalendar() returns DataFrame; compatible approach:
    try:
        df[f"{prefix}_week"] = df[date_col].dt.isocalendar().week
    except Exception:
        df[f"{prefix}_week"] = df[date_col].dt.week
    df[f"{prefix}_day"] = df[date_col].dt.day
    df[f"{prefix}_weekday"] = df[date_col].dt.day_name()
    df[f"{prefix}_is_weekend"] = df[date_col].dt.dayofweek >= 5
    df[f"{prefix}_season"] = df[date_col].dt.month.apply(lambda m: season_from_month(int(m)) if pd.notna(m) else None)
    return df


def normalize_text_columns(df: pd.DataFrame, cols: list):
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
            # collapse internal whitespace
            df[c] = df[c].str.replace(r"\s+", " ", regex=True)
    return df


def convert_to_categorical(df: pd.DataFrame, cols: list):
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].astype("category")
    return df


def prepare_customers(in_path: Path, out_path: Path):
    df = pd.read_csv(in_path, parse_dates=["signup_date"]) if in_path.exists() else pd.DataFrame()
    logger.info("Preparing customers: rows=%s", len(df))
    # Normalize text
    df = normalize_text_columns(df, ["first_name", "last_name", "country"])
    # Add time features for signup_date
    df = add_time_features(df, "signup_date", "signup")
    # Customer age group: not available in provided data - set to 'unknown'
    df["age_group"] = "unknown"
    # Convert country to categorical
    df = convert_to_categorical(df, ["country"])
    # Save
    df.to_csv(out_path, index=False)
    logger.info("Wrote transformed customers to %s", out_path)


def prepare_products(in_path: Path, out_path: Path):
    df = pd.read_csv(in_path) if in_path.exists() else pd.DataFrame()
    logger.info("Preparing products: rows=%s", len(df))
    # Normalize product name and category
    df = normalize_text_columns(df, ["product_name", "category"])
    # Create a canonical key and clean display name
    df["product_name_key"] = df["product_name"].str.lower().str.replace(r"[^0-9a-zA-Z\s\-]", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    df["product_name_clean"] = df["product_name"].str.title().str.replace("Usb", "USB").str.replace("Usb C", "USB-C")
    # Convert category to categorical
    df = convert_to_categorical(df, ["category"])
    # Ensure price numeric
    df["price"] = pd.to_numeric(df["price"], errors="coerce").round(2)
    df.to_csv(out_path, index=False)
    logger.info("Wrote transformed products to %s", out_path)


def prepare_orders(in_path: Path, products_path: Path, out_path: Path):
    df = pd.read_csv(in_path, parse_dates=["order_date"]) if in_path.exists() else pd.DataFrame()
    products = pd.read_csv(products_path) if products_path.exists() else pd.DataFrame()
    logger.info("Preparing orders: rows=%s", len(df))
    # Normalize text if any
    df = normalize_text_columns(df, [])
    # Ensure numeric types
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").round(2)
    # Merge product price if available
    if not products.empty:
        products["product_id"] = pd.to_numeric(products["product_id"], errors="coerce")
        df["product_id"] = pd.to_numeric(df["product_id"], errors="coerce")
        df = df.merge(products[["product_id", "price", "product_name"]], on="product_id", how="left", suffixes=("", "_product"))
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
    else:
        df["price"] = np.nan
    # Compute unit_price (from product price) and expected_total
    df["unit_price"] = df.apply(lambda r: r["price"] if pd.notna(r.get("price")) else (r.get("total_amount") / r.get("quantity") if r.get("quantity") else np.nan), axis=1)
    df["expected_total"] = (df["unit_price"] * df["quantity"]).round(2)
    # Revenue = total_amount
    df["revenue"] = df["total_amount"].round(2)
    # Monetary mismatch flag
    df["order_amount_mismatch"] = ~np.isclose(df["expected_total"].fillna(0), df["total_amount"].fillna(0), atol=1e-2)
    # Time features
    df = add_time_features(df, "order_date", "order")
    # Convert categorical
    df = convert_to_categorical(df, ["product_name", "product_name_product", "price"])  # price left as numeric but included for completeness
    # Customer age group left as unknown (no DOB provided)
    df["customer_age_group"] = "unknown"
    # Profit: not computed (cost data unavailable)
    df["profit"] = np.nan
    # Save
    df.to_csv(out_path, index=False)
    logger.info("Wrote transformed orders to %s", out_path)


def prepare_transactions(in_path: Path, products_path: Path, out_path: Path):
    df = pd.read_csv(in_path, parse_dates=["transaction_date"]) if in_path.exists() else pd.DataFrame()
    products = pd.read_csv(products_path) if products_path.exists() else pd.DataFrame()
    logger.info("Preparing transactions: rows=%s", len(df))
    # Normalize text columns
    df = normalize_text_columns(df, ["product_name", "category", "store_location", "payment_method"])
    # Ensure numeric
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").round(2)
    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").round(2)
    # Create keys and cleaned product name if not already present
    if "product_name_key" not in df.columns:
        df["product_name_key"] = df["product_name"].str.lower().str.replace(r"[^0-9a-zA-Z\s\-]", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    if "product_name_clean" not in df.columns:
        df["product_name_clean"] = df["product_name"].str.title().str.replace("Usb", "USB").str.replace("Usb C", "USB-C")
    # Compute expected_total and revenue
    df["expected_total"] = (df["unit_price"] * df["quantity"]).round(2)
    df["revenue"] = df["total_amount"].round(2)
    df["tx_amount_mismatch"] = ~np.isclose(df["expected_total"].fillna(0), df["total_amount"].fillna(0), atol=1e-2)
    # Join with products by normalized name where possible (best-effort)
    if not products.empty:
        products["product_name_key"] = products["product_name"].astype(str).str.lower().str.replace(r"[^0-9a-zA-Z\s\-]", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
        # left join on key
        df = df.merge(products[["product_id", "product_name_key", "price"]].rename(columns={"product_id": "product_id_mapped", "price": "product_price_mapped"}), on="product_name_key", how="left")
    else:
        df["product_id_mapped"] = np.nan
        df["product_price_mapped"] = np.nan
    # Time features
    df = add_time_features(df, "transaction_date", "tx")
    # Weekend flag, season included in add_time_features
    # Convert categorical
    df = convert_to_categorical(df, ["category", "store_location", "payment_method"])
    # Customer age group: unknown (no DOB data)
    df["customer_age_group"] = "unknown"
    # Profit: cannot compute without cost data
    df["profit"] = np.nan
    # Save
    df.to_csv(out_path, index=False)
    logger.info("Wrote transformed transactions to %s", out_path)


def main(input_dir: str, output_dir: str):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    customers_in = input_dir / "cleaned_customers.csv"
    products_in = input_dir / "cleaned_products.csv"
    orders_in = input_dir / "cleaned_orders.csv"
    transactions_in = input_dir / "cleaned_transactions.csv"

    customers_out = output_dir / "transformed_customers.csv"
    products_out = output_dir / "transformed_products.csv"
    orders_out = output_dir / "transformed_orders.csv"
    transactions_out = output_dir / "transformed_transactions.csv"

    prepare_customers(customers_in, customers_out)
    prepare_products(products_in, products_out)
    prepare_orders(orders_in, products_in, orders_out)
    prepare_transactions(transactions_in, products_in, transactions_out)

    logger.info("All transformations complete. Transformed files written to %s", output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transform cleaned datasets for analysis")
    parser.add_argument("--input-dir", type=str, default="data/processed_data", help="Input directory with cleaned CSVs")
    parser.add_argument("--output-dir", type=str, default="data/processed_data", help="Output directory for transformed CSVs")
    args = parser.parse_args()
    main(args.input_dir, args.output_dir)
