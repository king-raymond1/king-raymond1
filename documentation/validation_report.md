# Validation Report — Cleaned Datasets

Branch: scaffold/project-structure
Repository: king-raymond1/king-raymond1

Summary
-------
This validation report documents the results of a systematic validation performed on the cleaned datasets produced and committed to data/processed_data. The validation follows data-quality best practices and checks for:

- Missing values
- Duplicate records
- Data consistency (types, value ranges)
- Referential integrity across datasets
- Invalid IDs and formatting
- Incorrect relationships (e.g., price * quantity mismatches)

Datasets validated
------------------
- data/processed_data/cleaned_customers.csv (5 rows)
- data/processed_data/cleaned_products.csv (4 rows)
- data/processed_data/cleaned_orders.csv (5 rows)
- data/processed_data/cleaned_transactions.csv (50 rows)

Validation results (high level)
-------------------------------
- Missing values: NONE detected in the supplied cleaned files (no nulls in any column across samples).
- Duplicate records: NONE exact duplicates across all files.
- Data types: Columns are consistent with expected types (IDs numeric or string as appropriate; dates are ISO-formatted strings in outputs and parseable to datetimes).
- Referential integrity:
  - Orders → Customers: PASS (all customer_id values in cleaned_orders are present in cleaned_customers).
  - Orders → Products: PASS (all numeric product_id values in cleaned_orders are present in cleaned_products).
  - Transactions → Customers: FAIL (transactions.customer_id values use a different namespace, e.g., "C3067" vs customers.customer_id numeric — no direct referential link).
  - Transactions → Products: FAIL (transactions.product_id values are codes like "P002" while products.product_id are numeric; no direct referential link).
- Invalid IDs: NONE detected (IDs conform to their observed formats; no missing or malformed IDs in the samples).
- Incorrect relationships (monetary consistency): ONE ORDER FLAGGED — order_id 5004 (expected_total = 100.00 vs recorded total_amount = 90.00). Transactions monetary fields were consistent (no tx rows flagged within a 1-cent tolerance).

Detailed findings and checks
----------------------------
I. Missing values
- Approach: For each cleaned CSV I counted nulls by column. All counts were zero in the provided cleaned files.
- Conclusion: No missing values in the sample. The ETL pipeline uses safe coercion and will flag parse errors if present in larger inputs.

II. Duplicate detection
- Approach: exact duplicate detection using pandas.DataFrame.duplicated(keep=False).
- Result: 0 duplicates in each file.

III. Data consistency and types
- Customers
  - customer_id: all integer-like values (101, 102, 103, 104, 105)
  - signup_date: ISO strings (YYYY-MM-DD) and parseable to datetime
- Products
  - product_id: integers (9001..9004)
  - price: numeric two-decimal values
- Orders
  - order_id, customer_id, product_id: integers
  - quantity: integer
  - total_amount: numeric (two decimals)
  - expected_total: computed by merging product price and quantity, stored as numeric
  - order_amount_mismatch: boolean added for diagnostic
- Transactions
  - transaction_date: ISO datetime strings (YYYY-MM-DD HH:MM:SS) and parseable
  - quantity: integer; unit_price and total_amount numeric
  - product_name_key and product_name_clean: canonicalized string fields added for mapping
  - expected_total and tx_amount_mismatch: diagnostics added

IV. Referential integrity
- Orders → Customers
  - customers.customer_id: {101,102,103,104,105}
  - orders.customer_id values present in orders: {101,102,101,103,105}
  - Result: all orders customer_id values are present in customers (PASS).

- Orders → Products
  - products.product_id: {9001,9002,9003,9004}
  - orders.product_id values present in orders: {9001,9003,9002,9004,9003}
  - Result: all orders product_id values are present in products (PASS).

- Transactions → Customers / Products
  - transactions.customer_id values use a separate 'C' namespace (e.g., C3067). There is no direct match with customers.customer_id numeric values. Referential integrity cannot be established with the current data (FAIL).
  - transactions.product_id values use 'P' codes (e.g., P002). There is no direct match to products.product_id numeric values. Referential integrity cannot be established with the current data (FAIL).

V. Invalid IDs and formatting
- No IDs were missing or null.
- Numeric IDs were numeric; string-coded IDs (transactions) are consistent in format (leading letter + digits).

VI. Incorrect relationships (monetary consistency)
- Orders diagnostics (from cleaned_orders.csv):
  - order_id 5004 flagged as order_amount_mismatch = True
    - price for product 9004 = 50.00
    - quantity = 2
    - expected_total = 100.00
    - recorded total_amount = 90.00
    - Possible causes: discount applied, tax or shipping included/excluded, data-entry error.
- Transactions diagnostics: No tx_amount_mismatch rows in the sample (all unit_price * quantity match total_amount within tolerance).

Validation summary table
------------------------
Dataset | Rows | Missing values | Exact duplicates | Referential integrity | Amount mismatches
---|---:|---:|---:|---|---:
cleaned_customers.csv | 5 | 0 | 0 | N/A | 0
cleaned_products.csv | 4 | 0 | 0 | N/A | 0
cleaned_orders.csv | 5 | 0 | 0 | Orders→Customers: PASS; Orders→Products: PASS | 1 (order_id 5004)
cleaned_transactions.csv | 50 | 0 | 0 | Transactions→Customers: FAIL; Transactions→Products: FAIL | 0

Root-causes and recommendations
--------------------------------
1) Transactions namespace mismatch (primary issue)
   - Root cause: The transactions dataset uses a separate ID namespace for both customers (Cxxxx) and products (Pxxx). Likely this dataset originates from a separate operational system or a different catalog version.
   - Recommendation: Build a mapping table that relates transactions.customer_id to customers.customer_id, and transactions.product_id (Pxxx) to products.product_id (numeric). Suggested approach:
     - Use product_name_key (transactions) to candidate-match against products.product_name normalized similarly.
     - Create a small manual mapping file (data/external/transactions_product_map.csv) for ambiguous cases. Example schema: transactions_product_id,products_product_id,confidence,notes
     - Use the mapping to join and then re-run referential integrity checks and analysis.

2) Order 5004 amount mismatch
   - Root cause: data mismatch between expected_total (price*quantity) and recorded total_amount.
   - Recommendation: Investigate business rules — was a discount applied? Are taxes or fees included/excluded? Determine authoritative source for order pricing. If discount is valid, add discount_amount and discount_reason fields and re-compute expected_total accordingly.

3) Maintain provenance and checks
   - Add ingestion metadata per file: source system, ingestion timestamp, row counts, SHA256 checksum.
   - Add automated checks (e.g., Great Expectations / Deequ) that run on ingestion and fail builds or open issues when referential integrity or monetary validations fail.

4) Document mapping decisions
   - Record any manual mappings created between transaction IDs and core product/customer IDs in documentation/mappings.md so future reviewers can understand the lineage.

Reproducible validation commands
--------------------------------
You can reproduce these checks locally using the scripts included in the repo.

1. Checkout branch:
   git checkout scaffold/project-structure

2. Create env and install dependencies:
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

3. Run the profiling & diagnostics script (it will create diagnostics CSVs):
   python scripts/profile_data.py --data-dir data/raw_data --output-dir outputs/profiling

4. Inspect diagnostics:
   - outputs/profiling/orders_amount_diagnostics.csv (shows order 5004 mismatch)
   - outputs/profiling/transactions_amount_diagnostics.csv (transaction diagnostics and canonical product_name_key)

Files added with this report
----------------------------
- documentation/validation_report.md (this file)

Next steps I can take (pick any)
--------------------------------
- Create a suggested mapping file (data/external/transactions_product_map.csv) using fuzzy matching on product_name_key and commit it as a draft for manual review.
- Open a Pull Request merging scaffold/project-structure into your default branch and include this validation report.
- Add a GitHub Actions workflow to run the profile_data.py validation automatically on pushes to scaffold/project-structure.

If you want me to proceed with any of these, tell me which and I will implement it.
