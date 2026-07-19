# Transformation Summary

This document summarizes the transformations applied (or that will be applied by the transformation script) to
prepare the cleaned datasets for analysis. The script is located at `scripts/transform_data.py` and writes outputs to
`data/processed_data/transformed_*.csv`.

Transformations performed
-------------------------
- Calculated columns:
  - unit_price (for orders where possible), expected_total (price * quantity), revenue (alias for total_amount)
  - For transactions: expected_total = unit_price * quantity; revenue = total_amount
  - Diagnostic flags: order_amount_mismatch, tx_amount_mismatch
- Text normalization:
  - Trim whitespace and collapse repeated spaces in string columns (product_name, category, payment_method, store_location)
  - product_name_key: normalized lowercase key for joining (non-alphanumeric removed, multi-space collapsed)
  - product_name_clean: human-friendly title-cased product name with common acronyms restored (USB-C)
- Time-based features (for order_date and transaction_date):
  - year, month, quarter, week, day, weekday name, is_weekend (boolean), season (Winter/Spring/Summer/Autumn)
- Categorical conversion:
  - category, store_location, payment_method, country converted to pandas 'category' dtype for efficient storage and analysis
- Customer age group:
  - Not applicable (no DOB or age columns). The script creates an 'age_group' column with value 'unknown' for schema compatibility.
- Profit calculations:
  - Not performed because cost data is not available. The script creates a 'profit' column populated with NaN; instructions are
    provided in the script and this file for computing profit after cost data is available.

Notes on referential mapping
---------------------------
- The transactions dataset uses a separate ID namespace (Pxxx for products and Cxxxx for customers). The transform script
  performs a best-effort mapping from transactions to products using the product_name_key. This is a heuristic and should be
  verified manually; the script writes mapped product_id_mapped and product_price_mapped fields for review.

How to run
----------
1. Create a virtual environment and install dependencies:
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt

2. Run the transformation script:
   python scripts/transform_data.py --input-dir data/processed_data --output-dir data/processed_data

3. Output files:
   - data/processed_data/transformed_customers.csv
   - data/processed_data/transformed_products.csv
   - data/processed_data/transformed_orders.csv
   - data/processed_data/transformed_transactions.csv

Next steps
----------
- Verify mapped product_id_mapped values in transformed_transactions.csv and create a manual mapping file for ambiguous cases
  at data/external/transactions_product_map.csv.
- If cost data becomes available, compute profit as (unit_price - cost) * quantity and populate the profit column.
- Add unit tests for the seasonal mapping, week-number handling, and text canonicalization logic.

