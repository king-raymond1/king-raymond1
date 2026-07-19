# Advanced Analytics Report

This file accompanies scripts/advanced_analytics.py and summarizes the analyses produced. Run the script to generate CSVs and figures under analysis/ and visualizations/figures/.

What the script produces

- RFM segmentation (analysis/rfm_segmentation.csv)
  - Recency, Frequency, Monetary, RFM scores (1-5), RFM segment label (Champion, Loyal, At Risk, etc.)

- ABC / Pareto product analysis (analysis/abc_pareto_products.csv, analysis/pareto_products.csv)
  - Revenue per product, cumulative share, ABC class (A: top ~70%, B: next 20%, C: rest)

- Cohort analysis & retention (analysis/cohort_analysis.csv, analysis/retention_table.csv)
  - Cohort retention heatmap and CSV showing relative retention of cohorts over periods

- Customer retention snapshot (analysis/retention_customers_snapshot.csv)
  - Last purchase date and churn_flag using a 90-day churn window

- Revenue concentration and Gini (analysis/revenue_concentration.csv)
  - Lorenz curve figure and Gini coefficient to quantify revenue inequality across customers

- Top 20% customers and products (analysis/top20_customers.csv, analysis/top20_products.csv)
  - Lists of customers/products comprising the top 20% by count

Business recommendations (summary)

- Prioritize A-class products for inventory and promotions; focus marketing on top product bundles.
- Engage Champions and Loyal customers with VIP offers and referral incentives; create win-back campaigns for At Risk customers.
- Use cohort retention to evaluate onboarding effectiveness and the impact of campaigns on retention over time.
- If revenue concentration (Gini) is high, diversify product mix or increase cross-sell to reduce dependency on a small set of customers.
- Treat high-value customers as VIPs (dedicated support, premium shipping) and ensure fraud rules are tuned for high-value orders.

Next steps

- Provide canonical mappings (customer IDs, product SKUs) to consolidate records across orders and transactions for more accurate lifetime metrics.
- Add cost data to compute profit margin and LTV with profit rather than revenue.
- I can run the script on your cleaned data and commit the outputs (CSVs + PNGs) to the repository for direct review—reply "Run and commit results" to authorize that.

