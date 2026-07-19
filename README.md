# Sales Analytics — End-to-End Portfolio Project

Short description
This repository showcases an end-to-end data analytics workflow for retail sales data (customers, orders, products, transactions). It follows CRISP-DM and production-quality engineering practices: modular code, validation, tests, and reproducible artifacts.

Quick start
1. Create a virtual environment and install dependencies:
   - python -m venv venv && source venv/bin/activate
   - pip install -r requirements.txt
2. Place original CSVs in data/raw_data/
3. Run the pipeline:
   - python scripts/run_analysis.py --data-dir data/raw_data --output-dir data/processed_data
4. View outputs:
   - Processed datasets: data/processed_data/
   - Visuals: visualizations/figures and visualizations/interactive

Folder overview
- data/raw_data — original, immutable input files
- data/processed_data — cleaned and versioned datasets
- notebooks — exploratory and narrative notebooks
- src — reusable modules (data loading, cleaning, analysis)
- scripts — orchestrator scripts to run the pipeline
- visualizations — static & interactive charts
- reports — final deliverables (PDFs, slides)
- dashboard — dashboard app for interactive exploration
- documentation — data dictionary, assumptions, CRISP-DM log
- models — persisted model artifacts (if any)
- outputs — exported KPIs and CSV summaries

Contact
Project author: king-raymond1
