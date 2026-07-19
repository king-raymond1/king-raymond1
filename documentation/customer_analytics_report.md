# Customer Analytics Report

This file explains the outputs of the customer analytics pipeline. Run scripts/customer_analytics.py to regenerate the outputs under the analysis/ directory.

Files produced
- analysis/customer_rfm_orders.csv: RFM table computed from the orders dataset (numeric customer_id)
- analysis/customer_rfm_transactions.csv: RFM table computed from the transactions dataset (Cxxxx customer IDs)
- analysis/customer_segments_orders.csv: Segment labels for order-based customers (Champion, Loyal, Potential Loyalist, At Risk, Hibernating, New, Other)
- analysis/customer_segments_transactions.csv: Segment labels for transaction-based customers
- analysis/customer_retention_churn_transactions.csv: retention/churn indicators derived from transactions
- analysis/customer_analytics_summary.csv: small summary of counts and rates
- analysis/documentation/customer_analytics_report.md: human-readable summary and recommendations

Key methodologies

1) RFM Analysis
- R (Recency): number of days since last purchase; lower is better. Scored 1..5 (5 most recent) using quintiles.
- F (Frequency): count of purchases in the sample window. Scored 1..5 (5 most frequent) using quintiles.
- M (Monetary): total revenue contributed. Scored 1..5 (5 highest) using quintiles.
- The RFM score is RFM concatenated (e.g., 544) and used to segment customers.

2) Customer Segmentation rules
- Champion: r>=4 and f>=4 and m>=4
- Loyal: f>=4
- Potential Loyalist: r>=4 and m>=3
- At Risk: r<=2 and f>=3 and m>=3
- Hibernating: r<=2 and f<=2
- New: f==1 and r>=4
- Other: falls outside these rules

3) CLV (simplified)
- CLV_simplified = avg_order_value * purchase_frequency_per_month * 12 * clv_years
- Uses a configurable expected customer lifespan (default 3 years). This is a deterministic approximation — use predictive models for robust LTV.

4) Purchase Frequency
- frequency = number of transactions/orders per customer in the sample window
- purchase_frequency_per_month approximated in CLV using recency-days based tenure estimation

5) Retention & Churn
- Churn indicator: days since last purchase greater than churn_window (default 90 days) flagged as churn.
- Retention: month-to-month retention rate computed naively from transactions by checking customers present in month N and month N+1.

Business implications and actions

- Champions and Loyal segments: high-value and frequent purchasers — prioritize with VIP programs, exclusive offers, and referrals.
- Potential Loyalists: recently active with decent monetary value — encourage repeat purchases with cross-sell/bundles.
- At Risk: historically valuable but not recent — use win-back campaigns and personalized offers.
- Hibernating & One-time: low engagement — test onboarding, introductory offers, or reactivation emails.
- Repeat purchasers vs One-time: repeat purchasers indicate product-market fit and higher LTV; focus retention efforts to convert one-time to repeat.
- For meaningful customer lifetime and churn modeling, expand the historical window and reconcile transactions/customer mappings.

Next steps

- Provide mapping files to reconcile transaction customer IDs (Cxxxx) to canonical customer IDs used in orders so we can compute unified RFM and LTV.
- Add cost data to compute profit and margin per customer and per product.
- Implement predictive CLV models (BG/NBD + Gamma-Gamma) for better LTV estimates.

