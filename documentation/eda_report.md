# Exploratory Data Analysis Report

This EDA report summarizes the findings and insights after analyzing the cleaned/processed datasets. The plots and interactive charts are saved to visualizations/. Run `python scripts/run_eda.py` to reproduce the results locally.

Key metrics computed
- Orders revenue: $645.00
- Transactions revenue: $4,874.77
- Combined revenue (orders + transactions): $5,519.77
- Transactions rows: 50
- Orders rows: 5
- Unique customers (transactions): 50
- Unique customers (orders): 5
- Total transaction quantity: 163
- Average transaction quantity: 3.26

Top products by transaction count (transactions dataset)
- USB-C Cable: 6 transactions
- Ballpoint Pen Pack: 6 transactions
- Headphones: 5 transactions
- Phone Charger: 5 transactions
- Running Shoes: 4 transactions
- Protein Bar: 4 transactions

Daily revenue (transactions)
- Revenue by date (transactions only):
  - 2025-01-27: $1,005.04
  - 2025-01-28: $815.77
  - 2025-01-29: $727.09
  - 2025-01-30: $529.23
  - 2025-01-31: $287.45
  - 2025-02-01: $404.87
  - 2025-02-02: $1,105.32

Insights and interpretation

1) Revenue concentration and temporal patterns
- Two days (2025-01-27 and 2025-02-02) account for the highest daily revenues (~$1,005 and ~$1,105 respectively), suggesting bursts of activity possibly due to promotions, restocking, or batch sales.
- Mid-week days (e.g., 2025-01-31) show lower revenue in the sample. If this dataset is representative, consider investigating drivers for high-volume days (marketing, store events, or bulk orders).

2) Product performance
- A small number of SKUs drive repeated transactions: USB-C Cable and Ballpoint Pen Pack each have 6 transactions; Headphones and Phone Charger also have 5 each. These are good candidates for inventory prioritization and targeted promotions.
- High priced items (Mechanical Keyboard, Running Shoes, Headphones) contribute large single-transaction revenues (e.g., Running Shoes: several transactions of 79.99 each totalling high revenue for their counts).

3) Customer behavior
- The transactions sample contains 50 unique customer IDs, suggesting low repeat purchase frequency in this short window. For more robust segmentation, collect a longer time horizon or link transaction IDs to canonical customer records.

4) Revenue vs quantity
- Average quantity per transaction is ~3.26, indicating multi-unit purchases are common (bundles or multipacks). However, many large-revenue transactions come from higher-priced single-item purchases.

5) Data quality and mappings
- Transactions and orders currently use different ID namespaces (Pxxx / Cxxxx) and require mapping to the canonical product and customer IDs to enable combined analytics (e.g., computing lifetime value or SKU-level inventory analyses).
- Monetary mismatch in orders (order_id 5004) remains flagged — investigate discounts or data-entry errors before relying on order totals for financial reports.

Recommended next analyses
- Map transaction product IDs (Pxxx) to canonical product IDs using product_name_key, then re-run SKU-level revenue and inventory velocity analyses.
- Perform RFM segmentation once canonical customer mapping is available (Recency, Frequency, Monetary).
- Drill into the high-revenue dates to find whether specific SKUs, stores, or payment methods drove the spikes.

Files produced by scripts/run_eda.py
- visualizations/figures/top_products_count.png
- visualizations/figures/daily_revenue.png
- visualizations/interactive/daily_revenue.html
- visualizations/figures/revenue_distribution.png
- documentation/eda_report.md (this file)

