"""
Analysis functions to produce metrics and aggregated tables for reporting.
"""

import pandas as pd
import logging

logger = logging.getLogger(__name__)

def top_products_by_revenue(orders_products_df: pd.DataFrame, top_n=10):
    """
    Compute top products by revenue from merged orders+products table.
    Returns DataFrame with product_id, product_name, category, revenue, units_sold.
    """
    logger.info("Computing top %d products by revenue.", top_n)
    agg = (orders_products_df
           .groupby(["product_id", "product_name", "category"], dropna=False)
           .agg(units_sold=("quantity", "sum"),
                revenue=("total_amount", "sum"))
           .reset_index()
           .sort_values("revenue", ascending=False)
           .head(top_n))
    return agg

def top_customers_by_revenue(orders_products_df: pd.DataFrame, customers_df: pd.DataFrame, top_n=10):
    """
    Aggregate revenue by customer and attach customer metadata.
    """
    logger.info("Computing top %d customers by revenue.", top_n)
    cust_rev = (orders_products_df
                .groupby("customer_id", dropna=False)
                .agg(total_revenue=("total_amount", "sum"),
                     orders_count=("order_id", "count"))
                .reset_index()
                .sort_values("total_revenue", ascending=False)
                .head(top_n))
    # merge names
    result = cust_rev.merge(customers_df, on="customer_id", how="left")
    return result

def revenue_by_category(orders_products_df: pd.DataFrame):
    logger.info("Computing revenue by category.")
    return (orders_products_df
            .groupby("category", dropna=False)
            .agg(revenue=("total_amount", "sum"),
                 units_sold=("quantity", "sum"))
            .reset_index()
            .sort_values("revenue", ascending=False))

def transactions_time_series(transactions_df: pd.DataFrame, date_col="transaction_date"):
    """
    Returns daily revenue and counts from the transactions dataset.
    """
    df = transactions_df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    df["date"] = df[date_col].dt.date
    daily = (df.groupby("date")
             .agg(revenue=("total_amount", "sum"),
                  transactions=("transaction_id", "count"))
             .reset_index()
             .sort_values("date"))
    return daily
