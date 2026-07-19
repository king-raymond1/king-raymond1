# Order Analysis Report

This report is produced by scripts/order_analysis.py. It analyzes order trends, monthly and daily orders, average order value (AOV), order frequency per customer, identification of large and small orders, cancelled orders (if available), and order status distribution.

Files produced (after running the script):
- analysis/orders_summary.csv — high-level totals and AOV
- analysis/monthly_orders.csv — monthly counts and revenue
- analysis/daily_orders.csv — daily counts and revenue
- analysis/large_orders.csv — orders at or above the large-order percentile threshold
- analysis/small_orders.csv — orders at or below the small-order percentile threshold
- analysis/order_frequency_per_customer.csv — orders per customer and avg order value by customer
- analysis/order_status_distribution.csv — distribution of order statuses (if present)
- analysis/cancelled_orders.csv — cancelled orders (if present)
- visualizations/figures/*.png — charts for presentation

How the analysis works
- Order trends: daily and monthly aggregations of order counts and revenue. Plots produced for trend visualization.
- Monthly orders: aggregated counts per month and AOV (monthly revenue / monthly orders).
- Average order value: computed globally and by month.
- Order frequency: per-customer order counts and revenue to identify frequent purchasers.
- Large/Small orders: determined by configurable percentiles (default large=90th, small=10th). Use these for fraud checks, VIP handling, or special shipping/pricing.
- Cancelled orders: detected from common fields (`order_status`, `cancelled`, `canceled`) and saved if available.
- Order status distribution: pie chart showing proportions of order statuses.

Business implications and recommended actions
- Monitor order trends for spikes/drops linked to campaigns or operational issues. Drill into spike dates for root cause.
- High AOV months are candidates for premium offers and loyalty incentives; low AOV months could benefit from bundling promotions.
- Large orders: ensure fraud screening and fulfillment readiness; consider VIP handling for repeat large customers.
- Small orders: consider minimum basket promotions, free-shipping thresholds or bundling to increase AOV.
- Cancellations: if present and high, investigate reasons (fulfillment, pricing, returns policy) and fix root causes.
- Order frequency: identify and reward frequent customers with retention programs to improve LTV.

How to run locally
1. Checkout branch scaffold/project-structure:
   - git clone https://github.com/king-raymond1/king-raymond1.git
   - cd king-raymond1
   - git checkout scaffold/project-structure
2. Setup environment and run:
   - python -m venv venv
   - source venv/bin/activate
   - pip install -r requirements.txt
   - python scripts/order_analysis.py --input-dir data/processed_data --output-dir visualizations --large_pct 0.90 --small_pct 0.10

Open the generated files under analysis/ and visualizations/figures/.

