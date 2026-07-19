"""
Data loading and schema validation functions.
"""

from typing import List, Dict
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def load_csv(path: str, parse_dates: List[str] = None) -> pd.DataFrame:
    """
    Load a CSV into a DataFrame with safe parsing.
    - parse_dates: list of columns to parse as datetime.
    """
    try:
        logger.info("Loading CSV: %s", path)
        df = pd.read_csv(path, parse_dates=parse_dates, infer_datetime_format=True)
        logger.info("Loaded %s rows, %s columns", df.shape[0], df.shape[1])
        return df
    except FileNotFoundError as e:
        logger.exception("File not found: %s", path)
        raise
    except pd.errors.EmptyDataError:
        logger.exception("CSV is empty: %s", path)
        raise
    except Exception:
        logger.exception("Unexpected error loading CSV: %s", path)
        raise

def validate_columns(df: pd.DataFrame, expected: List[str], df_name: str = "dataframe") -> bool:
    """
    Validate that required columns exist in df.
    Logs missing columns and returns True if OK.
    """
    missing = [c for c in expected if c not in df.columns]
    if missing:
        logger.error("Missing columns in %s: %s", df_name, missing)
        return False
    return True

def summarize_df(df, name="df", max_rows=5):
    """Print a short summary for inspection (non-destructive)."""
    logger.info("Summary of %s", name)
    logger.info("Shape: %s", df.shape)
    logger.info("Columns: %s", df.dtypes.to_dict())
    logger.info("Missing values per column:\n%s", df.isnull().sum())
    logger.info("Head:\n%s", df.head(max_rows).to_dict(orient="records"))
