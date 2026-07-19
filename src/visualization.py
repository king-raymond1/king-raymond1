"""
Plotting utilities that produce both static and interactive charts.

- Matplotlib for PNG/print-quality figures.
- Plotly for interactive HTML outputs suitable for portfolio.
"""

import os
import matplotlib.pyplot as plt
import plotly.express as px
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def bar_plot_top_products(df, output_path=None, title="Top Products by Revenue"):
    """
    Static matplotlib bar plot for top products.
    Expects df with columns: product_name, revenue
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(df["product_name"], df["revenue"], color="tab:blue")
    ax.set_title(title)
    ax.set_ylabel("Revenue")
    ax.set_xticklabels(df["product_name"], rotation=45, ha="right")
    plt.tight_layout()
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150)
        logger.info("Saved static figure to %s", output_path)
    plt.close(fig)
    return output_path

def interactive_time_series(df, x_col, y_col, output_html=None, title="Time Series"):
    """
    Create a plotly interactive timeseries and optionally save to HTML.
    """
    fig = px.line(df, x=x_col, y=y_col, title=title, markers=True)
    fig.update_layout(template="plotly_white")
    if output_html:
        Path(output_html).parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(output_html)
        logger.info("Saved interactive figure to %s", output_html)
    return fig
