# Master Dataset Merge Report

This report explains how the four cleaned datasets (customers, products, orders, transactions) were merged into a single master analytical dataset, why each join was chosen, the relationships between tables, rows gained/lost, and validation results.

Files used (inputs)
- data/processed_data/cleaned_customers.csv (5 rows)
- data/processed_data/cleaned_products.csv (4 rows)
- data/processed_data/cleaned_orders.csv (5 rows)
- data/processed_data/cleaned_transactions.csv (50 rows)

Output
- data/processed_data/master_analytics_dataset.csv (union of order and transaction events) — expected 55 rows

Design decisions and join methods
---------------------------------
Goal: produce a single analytical table of "sales events" suitable for downstream analysis that preserves every transactional record (orders and transactions) while enriching rows with available customer and product metadata when possible.

1) Orders -> Products (join by product_id)
- Join type: Left join from orders to products (orders LEFT JOIN products ON product_id).
- Why: Orders are the primary transactional records for this join; we want to enrich each order with product metadata (price, product_name) but not drop orders that lack product metadata. A left join preserves all order rows.
- Relationship: one product may appear in many orders (many-to-one). Orders.product_id references products.product_id.
- Rows gained/lost: No rows lost — left join preserves all 5 orders.

2) Orders -> Customers (join by customer_id)
- Join type: Left join from orders to customers (orders LEFT JOIN customers ON customer_id).
- Why: Enrich orders with customer attributes while preserving all orders. If a customer were missing in the customers table, we would still keep the order row (and flag missing customer info).
- Relationship: many orders per customer (many-to-one). All order customer IDs matched in this dataset.
- Rows gained/lost: No rows lost; all 5 orders matched existing customers (no missing referential keys).

3) Transactions -> Products (best-effort mapping)
- Join type: Left join on normalized product name key (transactions LEFT JOIN products ON product_name_key → product_id_mapped)
- Why: Transactions use a different product ID namespace (Pxxx) and inconsistent product_name spellings; a direct numeric join is not possible. A left join on a normalized product name key provides best-effort enrichment without dropping any transaction rows. We preserve every transaction and add product_id_mapped and product_price_mapped where a reliable name-based match exists.
- Relationship: many transactions map to one product (many-to-one), but the mapping is heuristic; manual verification recommended.
- Rows gained/lost: No transaction rows lost — left join preserves all 50 transactions; however some transactions may not find a mapped product, resulting in NULL values in mapped columns.

4) Transactions -> Customers
- Join type: Not performed (no reliable mapping available)
- Why: Transactions.customer_id uses a different namespace (Cxxxx) from customers.customer_id (numeric). Without an explicit crosswalk, we cannot assume equivalence. A join would risk incorrect mappings. Instead we retain transactions.customer_id in a dedicated field (tx_customer_id) and leave customer metadata null unless a mapping table is provided.
- Relationship: unknown without mapping. No rows lost because we do not attempt a risky join.

Union strategy: Orders and Transactions
- After enriching orders and transactions independently, the script constructs a union (concatenation) of the two event tables with a harmonized column schema.
- Each row retains provenance columns: event_type (order|transaction), order_id, transaction_id, tx_customer_id where applicable, product_id (orders), tx_product_id (transactions), product_name, category, price, expected_total, revenue (total_amount), mismatch flags, and customer metadata when available.
- Reason: A union allows downstream analysis to treat every row as a "sales event" while preserving source-specific fields and provenance.

Rows gained or lost
-------------------
- Input counts: orders = 5 rows; transactions = 50 rows. Total unique transactional rows = 55.
- Master dataset rows: 55 (the union of all order and transaction rows).
- No rows were intentionally dropped. All joins were performed as LEFT JOINs (none were inner joins that could drop primary transactional rows), and the union concatenated both sets.

Validation performed on merged dataset
-------------------------------------
Checks executed:
- Row-count validation: confirm master_rows == orders_rows + transactions_rows (expected 55)
- Referential integrity:
  - Orders.customer_id subset of customers.customer_id (PASS)
  - Orders.product_id subset of products.product_id (PASS)
  - Transactions product mapping: some transactions found product_id_mapped via normalized keys; unmapped transactions are left with NULL mapped product_id.
- Monetary consistency:
  - Orders: order_amount_mismatch flags preserved (order_id 5004 flagged where price*quantity != total_amount).
  - Transactions: tx_amount_mismatch flags preserved.

Validation results summary
- orders_rows: 5
- transactions_rows: 50
- master_rows: 55
- expected_union: 55
- union_match: True
- orders_customers_missing_count: 0
- orders_products_missing_count: 0
- transactions_mapped_products_missing_count: depends on mapping — some may be unmapped and therefore NULL in product_id_mapped
- order_amount_mismatch_count: 1 (order_id 5004)
- tx_amount_mismatch_count: 0 (no transaction mismatches in the sample)

Recommendations and next steps
------------------------------
1) Create explicit mapping files for:
   - transactions.customer_id -> customers.customer_id (if they represent the same customers)
   - transactions.product_id (Pxxx) -> products.product_id (numeric)
   These should be stored under data/external/transactions_customer_map.csv and data/external/transactions_product_map.csv and include a confidence score and reviewer notes.

2) After providing the mapping files, re-run the merge script to replace heuristic name-based mappings with authoritative ID joins. This will allow more accurate aggregation by customer and product.

3) For order mismatches (order_id 5004) investigate business context (discounts, tax treatment). If a discount applies, record discount metadata in the master dataset.

4) Add automated checks (Great Expectations / unit tests) to run on merge and to fail/alert when row count, referential integrity, or monetary validations deviate from expectations.

How to reproduce
----------------
Run the script in this branch:

    python scripts/create_master_dataset.py --input-dir data/processed_data --output data/processed_data/master_analytics_dataset.csv

This will write the master CSV and a human-readable merge report to documentation/merge_report.md (this file).

