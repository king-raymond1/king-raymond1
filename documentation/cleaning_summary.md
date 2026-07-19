# Cleaning Summary Report

This document summarizes the professional cleaning steps applied to the four datasets and the results.

Repository branch: scaffold/project-structure
Files cleaned (input -> output):
- data/raw_data/customerscsv.csv -> data/processed_data/cleaned_customers.csv
- data/raw_data/productscsv.csv -> data/processed_data/cleaned_products.csv
- data/raw_data/orderscsv.csv -> data/processed_data/cleaned_orders.csv
- data/raw_data/transactions_2025_01_27.csv -> data/processed_data/cleaned_transactions.csv

Cleaning principles followed
- Never silently overwrite original data: all cleaned files were written to data/processed_data/ while raw inputs remain in data/raw_data/.
- Preserve original values where business rules are unclear; add diagnostic columns (expected_total, *_amount_mismatch) for human review.
- Avoid destructive imputations. When missing values occur, document and apply conservative imputations only when safe.
- Standardize text consistently and add canonical keys for reliable joins.

Summary statistics (rows before/after)
- customerscsv.csv: 5 rows -> cleaned_customers.csv: 5 rows
- productscsv.csv: 4 rows -> cleaned_products.csv: 4 rows
- orderscsv.csv: 5 rows -> cleaned_orders.csv: 5 rows
- transactions_2025_01_27.csv: 50 rows -> cleaned_transactions.csv: 50 rows

Duplicates removed
- Exact duplicate rows found and removed: 0 across all datasets.

Missing values handled
- No missing values were present in the provided raw CSVs. All columns for the supplied rows had values.
- The pipeline includes robust parsing (e.g., to_numeric with coercion) and flags parsing failures for manual review.

Incorrect data types fixed
- Parse dates: signup_date, order_date, transaction_date converted to ISO datetime formats in outputs.
- Numeric conversions: quantities, prices, totals converted to numeric types with two-decimal formatting for monetary fields.
- product_id: preserved original namespaces (numeric in products/orders, string Pxxx in transactions) to avoid incorrect mappings.

Whitespace and text standardization
- Trimmed leading/trailing whitespace from string fields.
- Collapsed repeated internal whitespace.
- Standardized product_name variants into two new columns in transactions:
  - product_name_key: normalized lowercase key used for grouping/matching (e.g., "usb c cable", "protein bar").
  - product_name_clean: human-friendly standardized display (title-case with common acronyms restored, e.g., "USB-C Cable").
- Standardized category, store_location, and payment_method capitalization where appropriate in the transactions cleaning step.

Invalid records and impossible values
- No negative quantities or negative prices were found in the supplied datasets.
- For orders and transactions, an expected_total = price * quantity (orders) or unit_price * quantity (transactions) was calculated and compared to reported total_amount. Differences were flagged for review rather than auto-corrected.

Amount mismatch diagnostics
- Orders: 1 row flagged as mismatch
  - order_id 5004: expected_total = 100.00 but total_amount = 90.00 -> order_amount_mismatch = True
- Transactions: 0 rows flagged as mismatch (all rows in supplied sample match unit_price * quantity within a 1-cent tolerance)

Outliers
- Small dataset: outlier detection needs business context. No obvious data-entry outliers were found (quantities are in 1-5 range; unit_price within expected product price ranges).
- Recommendation: for larger datasets, implement robust outlier detection (e.g., IQR or MAD-based) on monetary fields and quantities and log suspected entries for manual review.

Files produced (paths)
- data/processed_data/cleaned_customers.csv
- data/processed_data/cleaned_products.csv
- data/processed_data/cleaned_orders.csv
- data/processed_data/cleaned_transactions.csv

Next recommended steps
1. Manual review of flagged mismatches (orders_amount_diagnostics.csv produced by scripts/profile_data.py) to determine business rule (discount, tax, data entry error). If the 90.00 is a known discounted price, record discount metadata and update records accordingly.
2. Create a small mapping table to relate transactions.product_id (Pxxx) to products.product_id (numeric) if these refer to the same catalog; use product_name_key for assisted matching, but confirm mappings manually.
3. Add unit tests covering canonicalization, numeric parsing, and mismatch detection. Place tests under tests/ and run via CI.
4. For production workloads, add data validation checks (Deequ/Great Expectations) to prevent bad data from entering the pipeline, and record dataset checksums for provenance.

If you want, I can now:
- Open a pull request to merge these cleaned artifacts into your default branch.
- Run the profiling script and commit the generated HTML reports to visualizations/interactive/ for quick review.
- Add automated tests and a GitHub Actions workflow to run the profiling on push.

