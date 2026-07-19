"""
Data cleaning and normalization functions.

Key responsibilities:
- Parse dates reliably
- Standardize names and categories
- Normalize whitespace and casing in text fields
- Provide canonical product_name mapping for transactions dataset where product_id doesn't map to products.csv
"""

import pandas as pd
import re
import logging
from typing import Callable

logger = logging.getLogger(__name__)

_whitespace_re = re.compile(r"\s+")
_non_alnum_re = re.compile(r"[^0-9A-Za-z\s\-]+")  # keep hyphens for e.g. "USB-C"

def _normalize_text(s: str) -> str:
    """Trim, collapse whitespace, remove repeated spaces, and lower-case for canonical matching."""
    if pd.isna(s):
        return s
    t = str(s).strip()
    t = _non_alnum_re.sub(" ", t)   # remove punctuation except hyphen removal above if desired
    t = _whitespace_re.sub(" ", t)
    t = t.lower()
    return t

def standardize_product_name(s: str) -> str:
    """
    A friendly human-readable product name canonicalizer.
    E.g., "uSB-c cABLE" -> "USB-C CABLE" or better "USB-C Cable"
    Strategy:
    - Normalize text for matching (lowercase)
    - Use title case for final display but keep 'USB', 'USB-C' and other acronyms in uppercase manually
    """
    if pd.isna(s):
        return s
    raw = str(s).strip()
    # collapse whitespace
    tmp = _non_alnum_re.sub(" ", raw)
    tmp = _whitespace_re.sub(" ", tmp).strip()
    # title case then fix common acronyms
    candidate = tmp.title()
    # restore common uppercase tokens
    candidate = candidate.replace("Usb", "USB")
    candidate = candidate.replace("Usb C", "USB-C")
    candidate = candidate.replace(" Usb-C ", " USB-C ")
    candidate = candidate.replace("Rgb", "RGB")
    return candidate

def normalize_transactions_products(df: pd.DataFrame, product_name_col="product_name") -> pd.DataFrame:
    """
    Normalize product_name casing/whitespace and produce a canonical_name column used for grouping/matching.
    Also check for price/amount inconsistencies and log them.
    """
    df = df.copy()
    logger.info("Normalizing product names in transactions.")
    df["product_name_raw"] = df[product_name_col]
    # canonical key for matching
    df["product_name_key"] = df[product_name_col].apply(_normalize_text)
    # friendly display name
    df["product_name_clean"] = df[product_name_col].apply(standardize_product_name)
    # parse numeric columns
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce")
    # Validate unit_price * quantity approx equals total_amount
    mismatch_mask = (df["unit_price"] * df["quantity"] - df["total_amount"]).abs() > 1e-2
    if mismatch_mask.any():
        logger.warning("Found %d rows in transactions where unit_price * quantity != total_amount; will keep reported total_amount but flag them.",
                       mismatch_mask.sum())
        df.loc[mismatch_mask, "amount_mismatch"] = True
    else:
        df["amount_mismatch"] = False
    return df

def standardize_orders_products(orders: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """
    Merge orders and products (orders have numeric product_id that matches products).
    Validate that product price * quantity equals total_amount, and handle mismatches.
    """
    orders = orders.copy()
    products = products.copy()
    # ensure product_id is numeric
    orders["product_id"] = pd.to_numeric(orders["product_id"], errors="coerce")
    products["product_id"] = pd.to_numeric(products["product_id"], errors="coerce")
    merged = orders.merge(products, on="product_id", how="left", suffixes=("_order", "_product"))
    # parse types
    merged["quantity"] = pd.to_numeric(merged["quantity"], errors="coerce").fillna(0).astype(int)
    merged["total_amount"] = pd.to_numeric(merged["total_amount"], errors="coerce")
    # compute expectation
    merged["expected_total"] = merged["price"] * merged["quantity"]
    mismatch = (merged["expected_total"] - merged["total_amount"]).abs() > 1e-2
    if mismatch.any():
        logger.warning("Found %d order rows with price*quantity != total_amount; logging for further review.", mismatch.sum())
        merged["order_amount_mismatch"] = mismatch
    else:
        merged["order_amount_mismatch"] = False
    return merged
