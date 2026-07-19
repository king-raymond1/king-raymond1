# Transaction Analysis Report

This document describes the transaction analysis script and summarizes outputs. Run `python scripts/transaction_analysis.py --input-dir data/processed_data --output-dir visualizations` to regenerate the analysis.

Files produced (after running)
- analysis/transaction_summary.csv — totals and average transaction value
- analysis/daily_transactions.csv — daily transaction counts and revenue
- analysis/monthly_transactions.csv — monthly transaction counts and revenue
- analysis/transaction_frequency_per_customer.csv — transactions per customer and revenue contribution
- analysis/payment_trends.csv — revenue and counts by payment_method (if available)
- analysis/high_value_transactions.csv — transactions at or above threshold
- analysis/transaction_distribution.csv — descriptive stats for transaction values
- analysis/transaction_outliers.csv — transactions flagged as outliers by IQR/z-score
- visualizations/figures/*.png — charts

Key analyses performed

1) Transaction frequency
- Transactions per customer (counts) and revenue per customer. Useful to identify high-frequency customers for retention.

2) Payment trends
- Aggregation by payment_method to understand preferred methods and relative revenue contributions.

3) Daily & monthly transactions
- Time-series aggregates with average transaction value per period.

4) High-value transactions
- Identifies top percentile transactions (configurable). Useful for VIP detection and fraud review.

5) Transaction distribution & outliers
- Distribution metrics (count, mean, median, percentiles) and histograms. Outlier detection via IQR and z-score methods.

Business insights & recommendations

- If transactions are heavily skewed (common), use log-scale visualizations and log-transform for modeling.
- Target high-frequency customers with loyalty/retention; they typically have higher LTV.
- Review payment_method mix; prioritize reliability and UX for top methods. If certain methods show higher average transaction value, consider incentives to migrate low-value customers to higher-value methods where appropriate.
- Investigate high-value transactions for VIP behavior and potential fraud. Apply tiered fulfillment and customer service for high-value buyers.
- Validate outliers: remove data errors, sync refunds/cancellations, and flag chargebacks. Fine-tune outlier thresholds as more data is collected.

