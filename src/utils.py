"""
Utility helpers: logging configuration and small helpers used by the pipeline.
"""

import logging
import os
from pathlib import Path

def setup_logging(level=logging.INFO):
    """Configure root logger to output timestamps and level."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    return logging.getLogger()

def ensure_dir(path):
    """Create directory if it doesn't exist."""
    Path(path).mkdir(parents=True, exist_ok=True)
    return path
