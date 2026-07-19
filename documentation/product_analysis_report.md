# Product Analysis Report

This report is produced by scripts/product_analysis.py. It summarizes best-selling and worst-selling products, revenue by product and category, product popularity, average quantity sold, contribution/Pareto analysis, and ABC classification.

Files produced (after running the script):
- analysis/revenue_per_product.csv — total units and revenue per normalized product key
- analysis/top_products_by_revenue.csv — top N products by revenue
- analysis/worst_products_by_revenue.csv — bottom N products by revenue (non-zero)
- analysis/product_popularity.csv — counts, units, revenue per product
- analysis/product_contribution.csv — revenue share and cumulative % per product
- analysis/abc_classification.csv — ABC class assigned to each product
- visualizations/figures/ — PNG charts for quick review

ABC classification method
- We compute cumulative revenue share sorted by product revenue.
- Products contributing to the first 70% cumulative revenue are class A.
- Products contributing to the next 20% (up to 90% cumulative) are class B.
- Remaining products are class C.

Business implications
- A-class products: core revenue drivers. Ensure high availability, consider premium placement and promotional support.
- B-class products: growth opportunities through cross-sell, pricing experiments, or targeted promotions.
- C-class products: low revenue contribution — consider delisting, bundling, or clearance strategies.
- Use Pareto results to prioritize assortment, procurement, and marketing budget allocation.

How to run locally
1. Ensure cleaned data exists in data/processed_data:
   - data/processed_data/cleaned_transactions.csv
   - (optional) data/processed_data/cleaned_orders.csv
2. Run:
   - python scripts/product_analysis.py --input-dir data/processed_data --output-dir visualizations --top-n 20
3. Open outputs:
   - analysis/*.csv
   - visualizations/figures/*.png

