# Final analytical dataset README

This directory contains dashboard-ready CSV datasets produced by scripts/prepare_analytical_dataset.py.

How to generate

1. Ensure processed data exists in data/processed_data/ (cleaned_transactions.csv at minimum). Optional: cleaned_orders.csv, cleaned_customers.csv, cleaned_products.csv
2. Run:
   python scripts/prepare_analytical_dataset.py --input-dir data/processed_data --output-dir analysis/final_dataset

Files produced
- fact_sales.csv: transaction-level fact table (standardized columns, validated totals, profit/margin if unit_cost present)
- dim_date.csv: date dimension with attributes (year, month, weekday, is_weekend, year_month)
- dim_customers.csv: customer dimension with aggregated metrics (total_revenue, orders_count, first/last purchase)
- dim_products.csv: product dimension with aggregated metrics and ABC class
- sales_by_day.csv: aggregated daily metrics (revenue, units, transactions)
- sales_by_month.csv: aggregated monthly metrics
- sales_by_store_payment.csv: breakdown by store_location and payment_method
- rfm_customers.csv: RFM table with scores and rfm_score
- abc_products.csv: product ABC classification and cumulative revenue share
- top_customers.csv / top_products.csv: top 20% lists for quick use in dashboards
- validation_summary.csv: counts and basic validation checks

Design choices / best practices
- Use fact_sales.transaction_id joined to dim tables by customer_id, product_key, and transaction_date -> date_dim.date (or year_month/week) in your dashboard tool.
- Keep dimensions small and denormalized for fast dashboard joins (pre-aggregated fields included).
- Use consistent snake_case naming for all columns.
- Use numeric types for measures and ISO dates for date joins.

If you need other aggregates or a Parquet export for faster dashboards, I can add that next.