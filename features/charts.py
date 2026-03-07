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
from pyparsing import line

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


def _currency(val: float, currency: str = "KES") -> str:
    """Return a compact currency string for chart labels."""
    if abs(val) >= 1_000_000:
        return f"{currency} {val/1_000_000:.1f}M"
    if abs(val) >= 1_000:
        return f"{currency} {val/1_000:.1f}K"
    return f"{currency} {val:,.0f}"

def _add_watermark(fig: plt.Figure, text: str = "Finance Dashboard") -> None:
    fig.text(
        0.99, 0.01, text,
        ha="right", va="bottom",
        fontsize=7, color="#3a3d4d", style="italic",
    )


# ════════════════════════════════════════════════════════════════════════════
# FinanceCharts
# ════════════════════════════════════════════════════════════════════════════

class FinanceCharts:
    """
    Matplotlib chart renderer for the finance dashboard.

    Parameters
    ----------
    conn         : live MySQL connection
    current_user : authenticated user dict
    currency     : currency label (default "KES")
    year         : year to visualise (default: current year)
    """

    def __init__(
        self,
        conn: mysql.connector.MySQLConnection,
        current_user: Dict[str, Any],
        currency: str = "KES",
        year: Optional[int] = None,
    ) -> None:
        self.conn     = conn
        self.user     = current_user
        self.currency = currency
        self.year     = year or date.today().year

        self._analytics = AnalyticsModel(conn, current_user)
        self._balance   = BalanceService(conn, current_user)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _c(self, val: float) -> str:
        return _currency(val, self.currency)

    def _yformatter(self) -> mticker.FuncFormatter:
        """Y-axis tick formatter using compact currency."""
        return mticker.FuncFormatter(lambda x, _: self._c(x))

    # ════════════════════════════════════════════════════════════════════════
    # Chart 1 — Monthly Transaction Types Line Graph
    # ════════════════════════════════════════════════════════════════════════

    def monthly_transactions(self, year: Optional[int] = None) -> None:
        """
        Plot all transaction types as individual lines across all 12 months.
        Uses AnalyticsModel.monthly_comparison(year).
        """
        yr   = year or self.year
        data = self._analytics.monthly_comparison(year=yr)

        labels  = [r["month_label"] for r in data]
        x       = np.arange(len(labels))

        series = {
            "Income":                ([r["total_income"]               for r in data], COLORS["income"],                "o",  2.5),
            "Expenses":              ([r["total_expenses"]              for r in data], COLORS["expenses"],               "s",  2.5),
            "Debt Borrowed":         ([r["total_debt_in"]               for r in data], COLORS["debt_borrowed"],          "^",  2.0),
            "Debt Repaid":           ([r["total_debt_out"]              for r in data], COLORS["debt_repaid"],            "v",  2.0),
            "Investment Deposit":    ([r["total_investment_deposit"]    for r in data], COLORS["investment_deposit"],     "D",  2.0),
            "Investment Withdrawal": ([r["total_investment_withdrawal"] for r in data], COLORS["investment_withdrawal"],  "P",  2.0),
            "Net":                   ([r["net"]                         for r in data], COLORS["net"],                    "x",  1.5),
        }

        fig, ax = plt.subplots(figsize=(14, 7))
        fig.suptitle(
            f"Monthly Transaction Overview — {yr}",
            fontsize=16, fontweight="bold", color="#ffffff", y=0.98,
        )

        for label, (values, colour, marker, lw) in series.items():
            has_data = any(v != 0 for v in values)
            if not has_data:
                continue

            ax.plot(
                x, values,
                label=label,
                color=colour,
                marker=marker,
                linewidth=lw,
                markersize=6,
                markeredgewidth=1.2,
                markeredgecolor="#0f1117",
                alpha=0.92,
                zorder=3,
            )

            # Annotate peak value
            peak_i = int(np.argmax(np.abs(values)))
            if values[peak_i] != 0:
                ax.annotate(
                    self._c(values[peak_i]),
                    xy=(x[peak_i], values[peak_i]),
                    xytext=(0, 10),
                    textcoords="offset points",
                    ha="center",
                    fontsize=7,
                    color=colour,
                    fontweight="bold",
                )

        # Fill between income and expenses for visual impact
        income_vals   = series["Income"][0]
        expenses_vals = series["Expenses"][0]
        ax.fill_between(
            x, income_vals, expenses_vals,
            where=[i >= e for i, e in zip(income_vals, expenses_vals)],
            alpha=0.08, color=COLORS["positive"], label="_nolegend_",
        )
        ax.fill_between(
            x, income_vals, expenses_vals,
            where=[i < e for i, e in zip(income_vals, expenses_vals)],
            alpha=0.08, color=COLORS["negative"], label="_nolegend_",
        )

        # Zero line
        ax.axhline(0, color="#3a3d4d", linewidth=1, linestyle="--", zorder=1)

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10)
        ax.yaxis.set_major_formatter(self._yformatter())
        ax.set_xlabel("Month", labelpad=10)
        ax.set_ylabel(f"Amount ({self.currency})", labelpad=10)
        ax.set_title(
            "Each line represents a transaction type  •  Net = Income − Expenses",
            fontsize=9, color="#9a9db0", pad=6,
        )

        legend = ax.legend(
            loc="upper left",
            ncol=2,
            framealpha=0.85,
            borderpad=0.8,
        )

        # Summary stats box
        total_income   = sum(series["Income"][0])
        total_expenses = sum(series["Expenses"][0])
        net_annual     = total_income - total_expenses
        net_col        = COLORS["positive"] if net_annual >= 0 else COLORS["negative"]

        stats_text = (
            f"Annual Income:   {self._c(total_income)}\n"
            f"Annual Expenses: {self._c(total_expenses)}\n"
            f"Net Savings:     {self._c(net_annual)}"
        )
        ax.text(
            0.99, 0.97, stats_text,
            transform=ax.transAxes,
            ha="right", va="top",
            fontsize=8.5,
            color="#d0d3e0",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#1e2130",
                      edgecolor="#3a3d4d", alpha=0.9),
        )

        fig.tight_layout(rect=[0, 0, 1, 0.97])
        _add_watermark(fig)
        plt.show()

    # ════════════════════════════════════════════════════════════════════════
    # Chart 2 — Spending by Category Donut Chart
    # ════════════════════════════════════════════════════════════════════════

    def category_donut(
        self,
        transaction_type: str = "expense",
        top_n: int = 9,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> None:
        """
        Annotated donut chart of expense breakdown by category.
        Uses AnalyticsModel.top_categories().
        """
        today      = date.today()
        start_date = start_date or today.replace(day=1)
        end_date   = end_date   or today

        raw = self._analytics.top_categories(
            transaction_type=transaction_type,
            limit=top_n + 1,          # fetch one extra to detect an "Others" slice
            start_date=start_date,
            end_date=end_date,
        )

        if not raw:
            print("⚠  No expense data found for the selected period.")
            raise 

        # Cap at top_n; merge remainder into "Others"
        if len(raw) > top_n:
            others_total = sum(r["total"] for r in raw[top_n:])
            display      = raw[:top_n] + [{
                "category_name": "Others",
                "total":         others_total,
                "percentage":    round(others_total / sum(r["total"] for r in raw) * 100, 1),
                "count":         sum(r["count"] for r in raw[top_n:]),
            }]
        else:
            display = raw

        labels  = [r["category_name"]  for r in display]
        sizes   = [r["total"]          for r in display]
        pcts    = [r["percentage"]      for r in display]
        colours = (CATEGORY_PALETTE * 3)[:len(display)]

        # Explode the largest slice slightly
        max_i   = sizes.index(max(sizes))
        explode = [0.04 if i == max_i else 0.01 for i in range(len(sizes))]

        fig, (ax_donut, ax_legend) = plt.subplots(
            1, 2, figsize=(14, 7),
            gridspec_kw={"width_ratios": [1.2, 0.8]},
        )
        fig.suptitle(
            f"Spending by Category\n"
            f"{start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}",
            fontsize=15, fontweight="bold", color="#ffffff",
        )

        wedges, texts = ax_donut.pie(
            sizes,
            labels=None,
            colors=colours,
            explode=explode,
            startangle=140,
            wedgeprops=dict(width=0.52, edgecolor="#0f1117", linewidth=1.8),
            pctdistance=0.78,
        )

        # Percentage labels inside wedges
        for i, (wedge, pct) in enumerate(zip(wedges, pcts)):
            angle  = (wedge.theta1 + wedge.theta2) / 2
            x      = 0.68 * np.cos(np.radians(angle))
            y      = 0.68 * np.sin(np.radians(angle))
            colour = "#ffffff" if pct > 5 else colours[i]
            ax_donut.text(
                x, y, f"{pct:.1f}%",
                ha="center", va="center",
                fontsize=8.5, fontweight="bold", color=colour,
            )

        # Centre annotation
        total_expense = sum(sizes)
        ax_donut.text(
            0, 0.12, "Total\nExpenses",
            ha="center", va="center", fontsize=10, color="#9a9db0",
        )
        ax_donut.text(
            0, -0.18, self._c(total_expense),
            ha="center", va="center", fontsize=13, fontweight="bold",
            color=COLORS["expenses"],
        )

        ax_donut.set_aspect("equal")
        ax_donut.axis("off")

        # Legend table on the right
        ax_legend.axis("off")
        col_headers = ["Category", "Amount", "%", "Txns"]
        col_x       = [0.0,        0.40,     0.72, 0.88]
        row_height  = 0.072
        y_start     = 0.93

        for col_i, header in enumerate(col_headers):
            ax_legend.text(
                col_x[col_i], y_start, header,
                transform=ax_legend.transAxes,
                fontsize=9, fontweight="bold", color="#9a9db0",
            )

        ax_legend.axhline(
            y=y_start - 0.025,
            xmin=0, xmax=1,
            color="#3a3d4d", linewidth=0.8,
        )

        for i, row in enumerate(display):
            y = y_start - row_height * (i + 1) - 0.03
            if y < 0.02:
                break

            # colour swatch
            ax_legend.add_patch(mpatches.FancyBboxPatch(
                (col_x[0], y - 0.010), 0.025, 0.028,
                boxstyle="round,pad=0.002",
                facecolor=colours[i], edgecolor="none",
                transform=ax_legend.transAxes,
            ))

            ax_legend.text(col_x[0] + 0.035, y + 0.005,
                           row["category_name"][:18],
                           transform=ax_legend.transAxes,
                           fontsize=8.5, color="#d0d3e0")
            ax_legend.text(col_x[1], y + 0.005,
                           self._c(row["total"]),
                           transform=ax_legend.transAxes,
                           fontsize=8.5, color="#d0d3e0")
            ax_legend.text(col_x[2], y + 0.005,
                           f"{row['percentage']:.1f}%",
                           transform=ax_legend.transAxes,
                           fontsize=8.5, color="#d0d3e0")
            ax_legend.text(col_x[3], y + 0.005,
                           str(row.get("count", "—")),
                           transform=ax_legend.transAxes,
                           fontsize=8.5, color="#d0d3e0")

        fig.tight_layout(rect=[0, 0, 1, 0.93])
        _add_watermark(fig)
        plt.show()


    # ════════════════════════════════════════════════════════════════════════
    # Chart 3 — Daily Spending Calendar Heatmap
    # ════════════════════════════════════════════════════════════════════════

    def daily_heatmap(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> None:
        """
        GitHub-style calendar heatmap of daily expense intensity.
        Uses AnalyticsModel.daily_spending().
        """
        today      = date.today()
        end_date   = end_date   or today
        start_date = start_date or date(today.year, 1, 1)

        raw = self._analytics.daily_spending(
            start_date=start_date, end_date=end_date
        )

        # Build a lookup: date_str → total
        spend_map: Dict[str, float] = {r["date"][:10]: float(r["total"]) for r in raw}

        # Enumerate all days in range
        all_days: List[date] = []
        cur = start_date
        while cur <= end_date:
            all_days.append(cur)
            cur += timedelta(days=1)

        if not all_days:
            print("⚠  No daily data found for the selected period.")
            return

        # Calendar grid: row = weekday (0=Mon … 6=Sun), col = week index
        first_monday = all_days[0] - timedelta(days=all_days[0].weekday())
        week_cols: Dict[int, Dict[int, float]] = {}   # week_idx → {weekday: amount}
        month_positions: Dict[int, int] = {}          # month_num → first col idx

        for d in all_days:
            week_idx = (d - first_monday).days // 7
            wd       = d.weekday()
            amount   = spend_map.get(d.strftime("%Y-%m-%d"), 0.0)
            week_cols.setdefault(week_idx, {})[wd] = amount

            # Record first occurrence of each month
            if d.month not in month_positions:
                month_positions[d.month] = week_idx

        n_weeks  = max(week_cols.keys()) + 1
        grid     = np.zeros((7, n_weeks))
        day_grid = {}   # (row, col) → date object for tooltip labels

        for d in all_days:
            week_idx = (d - first_monday).days // 7
            wd       = d.weekday()
            grid[wd, week_idx] = spend_map.get(d.strftime("%Y-%m-%d"), 0.0)
            day_grid[(wd, week_idx)] = d

        # Mask days outside our range (before start or after end)
        mask = np.ones((7, n_weeks), dtype=bool)
        for (wd, wi) in day_grid:
            mask[wd, wi] = False
        grid_masked = np.ma.masked_where(mask, grid)
        

        # Colour map: dark bg → pale yellow → deep red
        cmap = mcolors.LinearSegmentedColormap.from_list(
            "github_green",
            ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
        )
        cmap.set_bad(color="#0f1117")   # masked cells

        fig_w  = max(14, n_weeks * 0.28 + 2)
        fig, ax = plt.subplots(figsize=(fig_w, 4.2))
        fig.suptitle(
            f"Daily Spending Heatmap  —  "
            f"{start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}",
            fontsize=14, fontweight="bold", color="#ffffff",
        )

        vmax = grid_masked.max() if grid_masked.max() else 1
        im   = ax.imshow(
            grid_masked,
            aspect="equal",
            cmap=cmap,
            vmin=0,
            vmax=vmax,
            interpolation="nearest",
        )

        # Weekday labels
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        ax.set_yticks(range(7))
        ax.set_yticklabels(day_names, fontsize=8.5)

        # Month labels on x-axis
        month_ticks   = sorted(month_positions.items(), key=lambda kv: kv[1])
        month_abbrevs = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        ax.set_xticks([pos for _, pos in month_ticks])
        ax.set_xticklabels([month_abbrevs[m] for m, _ in month_ticks], fontsize=9)

        # Day-number annotations (only when ≤ 16 weeks to keep it readable)
        if n_weeks <= 16:
            for (wd, wi), d in day_grid.items():
                val = grid[wd, wi]
                txt_color = "#ffffff" if val > vmax * 0.4 else "#5a5d70"
                ax.text(
                    wi, wd, str(d.day),
                    ha="center", va="center",
                    fontsize=6.5, color=txt_color,
                )

        # Weekend highlight lines
        for y_line in [4.5, 5.5]:
            ax.axhline(y_line, color="#3a3d4d", linewidth=0.8, linestyle="--")

        # Month separator lines
        for _, col in month_ticks[1:]:
            ax.axvline(col - 0.5, color="#3a3d4d", linewidth=0.8)

        # Colourbar
        cbar = fig.colorbar(im, ax=ax, orientation="vertical",
                            fraction=0.015, pad=0.02)
        cbar.set_label(f"Daily Spend ({self.currency})", fontsize=9, color="#d0d3e0")
        cbar.ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: self._c(x))
        )
        cbar.ax.tick_params(colors="#9a9db0", labelsize=8)

        # Stats
        total_days  = len([v for v in spend_map.values() if v > 0])
        total_spend = sum(spend_map.values())
        avg_spend   = total_spend / total_days if total_days else 0
        peak_day    = max(spend_map, key=spend_map.get, default="—")
        peak_val    = spend_map.get(peak_day, 0)

        stats = (
            f"Total Spent: {self._c(total_spend)}   "
            f"Active Days: {total_days}   "
            f"Daily Avg: {self._c(avg_spend)}   "
            f"Peak: {peak_day} ({self._c(peak_val)})"
        )
        ax.set_xlabel(stats, fontsize=8.5, color="#9a9db0", labelpad=8)

        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)

        fig.tight_layout(rect=[0, 0, 1, 0.93])
        _add_watermark(fig)
        plt.show()

    # ════════════════════════════════════════════════════════════════════════
    # Chart 4 — Net Worth Over Time Line Chart
    # ════════════════════════════════════════════════════════════════════════

    def net_worth_over_time(self, year: Optional[int] = None) -> None:
        """
        Reconstruct and plot approximate monthly net-worth for the year.

        Strategy
        --------
        1. Get current net worth from BalanceService (anchor).
        2. Get monthly_comparison(year) for monthly net deltas.
        3. Walk backwards from current month to Jan, subtracting each month's net.
        This gives a faithful month-by-month net-worth curve.
        """
        yr           = year or self.year
        today        = date.today()
        monthly_data = self._analytics.monthly_comparison(year=yr)
        current_nw   = self._balance.get_net_worth().get("total_net_worth", 0.0)

        # Build net-worth series going backwards from current month
        current_month = today.month if yr == today.year else 12
        nw_by_month   = {}
        running_nw    = current_nw

        for m in range(current_month, 0, -1):
            row           = monthly_data[m - 1]          # list is 0-indexed
            nw_by_month[m] = running_nw
            running_nw    -= row["net"]                   # subtract to go backwards

        # Filter to months that either have data or are before current month
        labels    = []
        nw_values = []
        for row in monthly_data:
            m = row["month"]
            if m > current_month and yr == today.year:
                break
            labels.append(row["month_label"])
            nw_values.append(nw_by_month.get(m, 0.0))

        if not nw_values:
            print("⚠  No net-worth data available.")
            return

        x = np.arange(len(labels))

        fig, ax = plt.subplots(figsize=(13, 6))
        fig.suptitle(
            f"Net Worth Over Time — {yr}",
            fontsize=15, fontweight="bold", color="#ffffff",
        )

        # Split into positive / negative segments for dual-colour fill
        nw_arr = np.array(nw_values, dtype=float)
        pos    = np.where(nw_arr >= 0, nw_arr, 0)
        neg    = np.where(nw_arr <  0, nw_arr, 0)

        ax.fill_between(x, pos, alpha=0.18, color=COLORS["positive"], zorder=1)
        ax.fill_between(x, neg, alpha=0.18, color=COLORS["negative"], zorder=1)

        # Gradient line effect: draw each segment in its own colour
        for i in range(len(x) - 1):
            seg_col = COLORS["positive"] if nw_arr[i] >= 0 else COLORS["negative"]
            ax.plot(
                x[i:i+2], nw_arr[i:i+2],
                color=seg_col, linewidth=2.5, solid_capstyle="round", zorder=3,
            )

        # Scatter markers
        scatter_cols = [COLORS["positive"] if v >= 0 else COLORS["negative"]
                        for v in nw_values]
        ax.scatter(x, nw_arr, c=scatter_cols, s=55, zorder=4,
                   edgecolors="#0f1117", linewidths=1.2)

        # Data labels on every other point to avoid crowding
        for i, (xi, val) in enumerate(zip(x, nw_values)):
            if i % 2 == 0 or i == len(x) - 1:
                vert   = "bottom" if val >= 0 else "top"
                offset = 10 if val >= 0 else -10
                ax.annotate(
                    self._c(val),
                    xy=(xi, val),
                    xytext=(0, offset),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                    color=scatter_cols[i],
                    fontweight="bold",
                )

        # Mark min and max
        max_i = int(np.argmax(nw_arr))
        min_i = int(np.argmin(nw_arr))

        for idx, label_str, col in [
            (max_i, f"Peak\n{self._c(nw_arr[max_i])}", COLORS["positive"]),
            (min_i, f"Low\n{self._c(nw_arr[min_i])}", COLORS["negative"]),
        ]:
            if max_i != min_i:
                ax.annotate(
                    label_str,
                    xy=(x[idx], nw_arr[idx]),
                    xytext=(18, 18 if nw_arr[idx] >= 0 else -28),
                    textcoords="offset points",
                    fontsize=8,
                    color=col,
                    fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=col, lw=1.2),
                    bbox=dict(boxstyle="round,pad=0.3",
                              facecolor="#1e2130", edgecolor=col, alpha=0.9),
                )

        # Zero baseline
        ax.axhline(0, color="#3a3d4d", linewidth=1, linestyle="--", zorder=2)

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10)
        ax.yaxis.set_major_formatter(self._yformatter())
        ax.set_xlabel("Month", labelpad=10)
        ax.set_ylabel(f"Net Worth ({self.currency})", labelpad=10)
        ax.set_title(
            "Reconstructed from monthly net cash flow  •  Current net worth anchors the series",
            fontsize=9, color="#9a9db0", pad=6,
        )

        # Current net worth box (top-right)
        nw_col = COLORS["positive"] if current_nw >= 0 else COLORS["negative"]
        ax.text(
            0.99, 0.97,
            f"Current Net Worth\n{self._c(current_nw)}",
            transform=ax.transAxes,
            ha="right", va="top",
            fontsize=10, fontweight="bold", color=nw_col,
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#1e2130",
                      edgecolor=nw_col, alpha=0.9),
        )

        fig.tight_layout(rect=[0, 0, 1, 0.95])
        _add_watermark(fig)
        plt.show()

    # ════════════════════════════════════════════════════════════════════════
    # Convenience — render all charts sequentially
    # ════════════════════════════════════════════════════════════════════════

    def show_all(self, year: Optional[int] = None) -> None:
        """Render all four charts one after another."""
        yr = year or self.year
        self.monthly_transactions(year=yr)
        self.category_donut()
        self.daily_heatmap()
        self.net_worth_over_time(year=yr)


