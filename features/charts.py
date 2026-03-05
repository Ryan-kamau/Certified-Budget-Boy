# features/charts.py
"""
Finance Charts — Matplotlib renderer
-------------------------------------
Detailed, readable graphs displayed via plt.show() on explicit request.

Charts available
----------------
1. monthly_transactions()  – All transaction types as lines across 12 months
2. category_donut()        – Expense breakdown as an annotated donut chart
3. daily_heatmap()         – Calendar heatmap of daily spending intensity
4. net_worth_over_time()   – Cumulative net-worth line chart for the year

Data sources (no duplication — reuses existing models)
-------------------------------------------------------
  AnalyticsModel.monthly_comparison()   → charts 1, 4
  AnalyticsModel.top_categories()       → chart 2
  AnalyticsModel.daily_spending()       → chart 3
  BalanceService.get_net_worth()        → chart 4 (anchor point)

Usage
-----
    from features.charts import FinanceCharts
    fc = FinanceCharts(conn, current_user)
    fc.monthly_transactions()
    fc.category_donut()
    fc.daily_heatmap()
    fc.net_worth_over_time()
    fc.show_all()           # renders all 4 sequentially
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import matplotlib.colors as mcolors
import numpy as np
import mysql.connector

from models.analytics_model import AnalyticsModel
from features.balance import BalanceService

# ── Global style ──────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor":      "#0f1117",
    "axes.facecolor":        "#1a1d27",
    "axes.edgecolor":        "#3a3d4d",
    "axes.labelcolor":       "#d0d3e0",
    "axes.titlesize":        14,
    "axes.titleweight":      "bold",
    "axes.titlecolor":       "#ffffff",
    "axes.labelsize":        11,
    "axes.grid":             True,
    "grid.color":            "#2a2d3d",
    "grid.linestyle":        "--",
    "grid.alpha":            0.6,
    "xtick.color":           "#9a9db0",
    "ytick.color":           "#9a9db0",
    "xtick.labelsize":       9,
    "ytick.labelsize":       9,
    "legend.facecolor":      "#1e2130",
    "legend.edgecolor":      "#3a3d4d",
    "legend.labelcolor":     "#d0d3e0",
    "legend.fontsize":       9,
    "text.color":            "#d0d3e0",
    "font.family":           "DejaVu Sans",
    "figure.dpi":            110,
})

# ── Colour palette (mirrors Dashboard._TX_COLOR intent) ──────────────────────
COLORS = {
    "income":                "#2ecc71",   # green
    "expenses":              "#e74c3c",   # red
    "net":                   "#ffffff",   # white
    "debt_borrowed":         "#f1c40f",   # yellow
    "debt_repaid":           "#3498db",   # blue
    "investment_deposit":    "#9b59b6",   # purple
    "investment_withdrawal": "#e67e22",   # orange
    "positive":              "#2ecc71",
    "negative":              "#e74c3c",
    "neutral":               "#7f8c8d",
}

CATEGORY_PALETTE = [
    "#e74c3c", "#e67e22", "#f1c40f", "#2ecc71",
    "#1abc9c", "#3498db", "#9b59b6", "#fd79a8",
    "#00cec9", "#6c5ce7",
]

