"""
Profile the four datasets and generate:
 - inspection prints (shape, dtypes, missingness, duplicates, memory usage)
 - first & last 5 rows
 - a ydata_profiling HTML report per dataset
 - a diagnostics CSV for orders and transactions that flags amount mismatches

Usage:
    pip install -r requirements.txt
    pip install ydata-profiling==4.2.0  # or pandas-profiling if you prefer
    python scripts/profile_data.py --data-dir data/raw_data --output-dir outputs/profiling
"""

import argparse
import logging
from pathlib import Path
import pandas as pd
import numpy as np
from ydata_profiling import ProfileReport  # pip install ydata-profiling

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def safe_load_csv(path: Path, parse_dates=None):
    try:
        logger.info("Loading %s", path)
        df = pd.read_csv(path, parse_dates=parse_dates, infer_datetime_format=True)
        logger.info("Loaded %d rows, %d columns", df.shape[0], df.shape[1])
        return df
    except Exception as e:
        logger.exception("Failed to load %s: %s", path, e)
        raise

def inspect_df(df: pd.DataFrame, name: str, show_head_tail: bool = True):
    print("="*80)
    print(f"Dataset: {name}")
    print("- Shape: {} (rows, columns)".format(df.shape))
    print("- Number of rows:", df.shape[0])
    print("- Number of columns:", df.shape[1])
    print("- Column names:", list(df.columns))
    print("- Data types:\n", df.dtypes)
    print("- Missing values per column:\n", df.isnull().sum())
    dup_count = df.duplicated(keep=False).sum()
    print("- Duplicate rows (exact):", dup_count)
    # memory usage (deep)
    try:
        mem = df.memory_usage(deep=True).sum()
        print(f"- Memory usage (deep): {mem} bytes")
    except Exception:
        mem_light = df.memory_usage().sum()
        print(f"- Memory usage (approx): {mem_light} bytes")
    if show_head_tail:
        print("- First 5 rows:")
        print(df.head(5).to_string(index=False))
        print("- Last 5 rows:")
        print(df.tail(5).to_string(index=False))
    print("="*80)

def generate_profile_report(df: pd.DataFrame, name: str, out_html: Path):
    logger.info("Generating profile report for %s -> %s", name, out_html)
    profile = ProfileReport(df, title=f"Profile Report: {name}", explorative=True)
    profile.to_file(out_html)
    logger.info("Saved profile report to %s", out_html)

def flag_amount_mismatches_orders(orders_df: pd.DataFrame, products_df: pd.DataFrame) -> pd.DataFrame:
    df = orders_df.copy()
    # Ensure numeric
    df["product_id"] = pd.to_numeric(df["product_id"], errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce")
    products_df = products_df.copy()
    products_df["product_id"] = pd.to_numeric(products_df["product_id"], errors="coerce")
    merged = df.merge(products_df[["product_id", "price"]], on="product_id", how="left")
    merged["expected_total"] = merged["price"] * merged["quantity"]
    merged["order_amount_mismatch"] = (~np.isclose(merged["expected_total"].fillna(0), merged["total_amount"].fillna(0), atol=1e-2))
    return merged

def flag_amount_mismatches_transactions(tx_df: pd.DataFrame) -> pd.DataFrame:
    df = tx_df.copy()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0.0)
    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0.0)
    df["expected_total"] = df["quantity"] * df["unit_price"]
    df["tx_amount_mismatch"] = (~np.isclose(df["expected_total"], df["total_amount"], atol=1e-2))
    return df

def canonicalize_product_name(s: str) -> str:
    if pd.isna(s):
        return s
    s2 = str(s).strip()
    # remove excess punctuation, collapse whitespace
    s2 = " ".join(s2.split())
    s2_low = s2.lower()
    # common normalization rules
    s2_low = s2_low.replace("usb c", "usb-c")
    s2_low = s2_low.replace("usb-c", "usb-c")
    return s2_low

def main(data_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    # Load files (adjust paths as needed)
    customers = safe_load_csv(data_dir / "customerscsv.csv", parse_dates=["signup_date"])
    products = safe_load_csv(data_dir / "productscsv.csv")
    orders = safe_load_csv(data_dir / "orderscsv.csv", parse_dates=["order_date"])
    transactions = safe_load_csv(data_dir / "transactions_2025_01_27.csv", parse_dates=["transaction_date"])

    # Inspections & prints
    inspect_df(customers, "customerscsv.csv")
    inspect_df(products, "productscsv.csv")
    inspect_df(orders, "orderscsv.csv")
    inspect_df(transactions, "transactions_2025_01_27.csv")

    # Generate profile reports (HTML)
    generate_profile_report(customers, "customerscsv.csv", output_dir / "customers_profile.html")
    generate_profile_report(products, "productscsv.csv", output_dir / "products_profile.html")
    generate_profile_report(orders, "orderscsv.csv", output_dir / "orders_profile.html")
    generate_profile_report(transactions, "transactions_profile.html", output_dir / "transactions_profile.html")

    # Diagnostics: flag mismatches
    orders_diag = flag_amount_mismatches_orders(orders, products)
    orders_diag.to_csv(output_dir / "orders_amount_diagnostics.csv", index=False)
    logger.info("Wrote orders diagnostics to %s", output_dir / "orders_amount_diagnostics.csv")

    transactions_diag = flag_amount_mismatches_transactions(transactions)
    # Add canonical product name to help mapping to products/products.csv
    transactions_diag["product_name_key"] = transactions_diag["product_name"].apply(canonicalize_product_name)
    transactions_diag.to_csv(output_dir / "transactions_amount_diagnostics.csv", index=False)
    logger.info("Wrote transactions diagnostics to %s", output_dir / "transactions_amount_diagnostics.csv")

    logger.info("Profiling complete. Reports and diagnostics saved to %s", output_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=str, required=True, help="Path to folder with raw CSVs")
    parser.add_argument("--output-dir", type=str, required=True, help="Path to write reports & diagnostics")
    args = parser.parse_args()
    main(Path(args.data_dir), Path(args.output_dir))
