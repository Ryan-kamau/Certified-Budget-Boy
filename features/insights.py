#smart insights and speending comparisonss
# features/insights.py
"""
============================================================
 InsightsEngine — Smart Financial Tips & Anomaly Detection
 ------------------------------------------------------------
 Generates actionable, threshold-driven insights by comparing
 current-period metrics against prior-period baselines.

 All queries are raw SQL (no ORM) — same pattern as AnalyticsModel.
 All tenant isolation mirrors the _tenant_filter() pattern used
 throughout the rest of the codebase.

 Insight Categories
 ------------------
 SPENDING        → spending_spike, spending_streak, daily_avg_up
 INCOME          → income_drop, no_income_this_month
 SAVINGS         → savings_rate_low, net_worth_change
 CATEGORY        → category_spike, category_budget_cap,
                   top_category_shift
 TRANSACTION     → large_transaction
 DEBT            → debt_growing
 PAYMENT         → payment_method_shift

 Severity Levels
 ---------------
 "info"     → positive or neutral observation
 "warning"  → notable change needing attention
 "critical" → threshold breached — action recommended

 Public API
 ----------
 InsightsEngine.get_all_insights(...)       → List[InsightDict]
 InsightsEngine.get_insights_by_category(category, ...) → List[InsightDict]
 InsightsEngine.get_spending_insights(...)  → List[InsightDict]
 InsightsEngine.get_income_insights(...)    → List[InsightDict]
 InsightsEngine.get_category_insights(...) → List[InsightDict]
 InsightsEngine.get_debt_insights(...)      → List[InsightDict]
 InsightsEngine.get_transaction_insights(...)→ List[InsightDict]
 InsightsEngine.get_summary(...)            → Dict

============================================================
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import mysql.connector

from models.analytics_model import AnalyticsModel
from core.utils import DatabaseError, ValidationError, error_logger


# ============================================================
# Custom Exceptions
# ============================================================

class InsightsError(Exception):
    """Base exception for InsightsEngine errors."""


class InsightsValidationError(ValidationError):
    """Raised when invalid parameters are supplied."""


class InsightsDatabaseError(DatabaseError):
    """Raised on raw DB / MySQL failures."""


# ============================================================
# Insight Severity & Category Constants
# ============================================================

class Severity:
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"


class InsightCategory:
    SPENDING     = "spending"
    INCOME       = "income"
    SAVINGS      = "savings"
    CATEGORY     = "category"
    TRANSACTION  = "transaction"
    DEBT         = "debt"
    PAYMENT      = "payment"

    ALL = {SPENDING, INCOME, SAVINGS, CATEGORY, TRANSACTION, DEBT, PAYMENT}


# ============================================================
# Insight Dataclass
# ============================================================

@dataclass
class Insight:
    """
    Represents a single generated insight/tip.

    Fields
    ------
    insight_id   : slug identifier, e.g. "spending_spike"
    category     : InsightCategory constant
    severity     : Severity constant
    title        : Short headline, e.g. "Spending Spike Detected"
    message      : Human-readable tip, e.g. "Spending 18% higher than last month"
    data         : Raw numbers used to generate the insight (for UI rendering)
    generated_at : ISO-8601 timestamp
    """
    insight_id   : str
    category     : str
    severity     : str
    title        : str
    message      : str
    data         : Dict[str, Any] = field(default_factory=dict)
    generated_at : str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
# ============================================================
# Default Thresholds
# ============================================================

DEFAULT_THRESHOLDS: Dict[str, Any] = {
    # Spending spike: warn at +10%, critical at +25%
    "spending_spike_warning_pct"    : 10.0,
    "spending_spike_critical_pct"   : 25.0,

    # Income drop: warn at -10%, critical at -25%
    "income_drop_warning_pct"       : 10.0,
    "income_drop_critical_pct"      : 25.0,

    # Savings rate: warn below 20%, critical below 10%
    "savings_rate_warning_pct"      : 20.0,
    "savings_rate_critical_pct"     : 10.0,

    # Per-category spending spike: warn at +20%, critical at +40%
    "category_spike_warning_pct"    : 20.0,
    "category_spike_critical_pct"   : 40.0,

    # Budget cap: warn when >75% used, critical when >100%
    "budget_cap_warning_pct"        : 75.0,
    "budget_cap_critical_pct"       : 100.0,

    # Large transaction: flag if single txn > X% of monthly income
    "large_txn_income_pct"          : 30.0,

    # Daily average spending spike: warn at +15%
    "daily_avg_spike_warning_pct"   : 15.0,
    "daily_avg_spike_critical_pct"  : 35.0,

    # Net worth drop: warn at -5%
    "net_worth_drop_warning_pct"    : 5.0,

    # Debt ratio: warn when debt_borrowed > X% of income
    "debt_income_ratio_warning_pct" : 40.0,

    # How many top categories to analyse per run
    "top_categories_to_analyse"     : 8,

    # How many months back to check spending streak
    "streak_months_to_check"        : 3,
}

# ============================================================
# InsightsEngine
# ============================================================

class InsightsEngine:
    """
    Generates smart financial insights by comparing current-period
    metrics against prior-period baselines using threshold logic.

    Parameters
    ----------
    conn         : Live MySQL connection (mysql.connector)
    current_user : Authenticated user dict {"user_id": int, "role": str}
    currency     : Display currency label (default "KES")
    thresholds   : Optional dict to override DEFAULT_THRESHOLDS
    """

    def __init__(
        self,
        conn            : mysql.connector.MySQLConnection,
        current_user    : Dict[str, Any],
        currency        : str = "KES",
        thresholds      : Optional[Dict[str, Any]] = None,
    ) -> None:
        self.conn     = conn
        self.user     = current_user
        self.user_id  : Optional[int] = current_user.get("user_id")
        self.role     : Optional[str] = current_user.get("role")
        self.currency = currency

        # Merge caller overrides on top of defaults
        self._thresholds: Dict[str, Any] = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

        # Delegate complex analytics queries to the existing model
        self._analytics = AnalyticsModel(conn, current_user)

    # ================================================================
    # Internal SQL Helpers  (mirrors analytics_model.py patterns)
    # ================================================================

    def _execute(
        self,
        sql    : str,
        params : Tuple[Any, ...] = (),
        *,
        fetchone : bool = False,
        fetchall : bool = False,
    ) -> Any:
        """Unified SQL executor — all insights queries are SELECT."""
        if fetchone and fetchall:
            raise InsightsDatabaseError("fetchone and fetchall cannot both be True.")
        try:
            with self.conn.cursor(dictionary=True) as cursor:
                cursor.execute(sql, params)
                if fetchone:
                    result = cursor.fetchone()
                    self.conn.commit()
                    return result
                if fetchall:
                    results = cursor.fetchall()
                    self.conn.commit()
                    return results
                return None
        except mysql.connector.Error as exc:
            error_logger.log_error(
                exc,
                location="InsightsEngine._execute",
                user_id=self.user_id,
            )
            raise InsightsDatabaseError(f"MySQL Error: {exc}") from exc
    

    def _tenant_filter(self, alias: str = "t") -> str:
        """
        Row-level tenant isolation.
        Regular users → scoped to own user_id.
        Admins        → scoped to own user_id (global view not needed for insights).
        """
        return f"{alias}.user_id = %s"

    def _f(self, value: Any) -> float:
        """Safely coerce Decimal / None → float."""
        if value is None:
            return 0.0
        return float(value)

    def _pct_change(self, current: float, previous: float) -> Optional[float]:
        """
        Return percentage change from previous → current.
        Returns None when previous is 0 (avoids divide-by-zero).
        """
        if previous == 0:
            return None
        return round(((current - previous) / previous) * 100, 2)

    def _fmt(self, amount: float) -> str:
        """Format an amount with currency label."""
        return f"{self.currency} {amount:,.2f}"

    def _th(self, key: str) -> Any:
        """Convenience accessor for thresholds."""
        return self._thresholds[key]

    # ================================================================
    # Date Helpers
    # ================================================================

    @staticmethod
    def _current_month_range() -> Tuple[date, date]:
        today = date.today()
        start = today.replace(day=1)
        return start, today

    @staticmethod
    def _prior_month_range() -> Tuple[date, date]:
        today  = date.today()
        first  = today.replace(day=1)
        # Last day of previous month = day before 1st of current
        from datetime import timedelta
        last   = first - timedelta(days=1)
        start  = last.replace(day=1)
        return start, last

    # ================================================================
    # LOW-LEVEL QUERY METHODS
    # ================================================================

    def _fetch_period_totals(
        self,
        start : date,
        end   : date,
    ) -> Dict[str, float]:
        """
        Return aggregated totals for all transaction types in a period.
        Used for spending, income, and savings-rate comparisons.
        """
        tenant = self._tenant_filter("t")
        sql = f"""
            SELECT
                COALESCE(SUM(CASE WHEN t.transaction_type = 'income'
                                  THEN t.amount ELSE 0 END), 0) AS total_income,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'expense'
                                  THEN t.amount ELSE 0 END), 0) AS total_expenses,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'debt_borrowed'
                                  THEN t.amount ELSE 0 END), 0) AS total_debt_in,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'debt_repaid'
                                  THEN t.amount ELSE 0 END), 0) AS total_debt_out,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'investment_deposit'
                                  THEN t.amount ELSE 0 END), 0) AS total_invested,
                COUNT(*) AS transaction_count
            FROM transactions t
            WHERE t.is_deleted = 0
              AND {tenant}
              AND t.transaction_date BETWEEN %s AND %s
        """
        row = self._execute(sql, (self.user_id, start, end), fetchone=True) or {}
        return {
            "total_income"    : self._f(row.get("total_income")),
            "total_expenses"  : self._f(row.get("total_expenses")),
            "total_debt_in"   : self._f(row.get("total_debt_in")),
            "total_debt_out"  : self._f(row.get("total_debt_out")),
            "total_invested"  : self._f(row.get("total_invested")),
            "transaction_count": int(row.get("transaction_count") or 0),
        }
    
    def _fetch_category_totals(
        self,
        start : date,
        end   : date,
        limit : int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Return top-N expense categories (with total & count) for a period.
        """
        tenant = self._tenant_filter("t")
        sql = f"""
            SELECT
                t.category_id,
                COALESCE(c.name, 'Uncategorised') AS category_name,
                COALESCE(SUM(t.amount), 0)         AS total,
                COUNT(*)                            AS tx_count
            FROM transactions t
            LEFT JOIN categories c ON c.category_id = t.category_id
            WHERE t.is_deleted = 0
              AND t.transaction_type = 'expense'
              AND {tenant}
              AND t.transaction_date BETWEEN %s AND %s
            GROUP BY t.category_id, c.name
            ORDER BY total DESC
            LIMIT %s
        """
        rows = self._execute(
            sql, (self.user_id, start, end, limit), fetchall=True
        ) or []
        return [
            {
                "category_id"  : row["category_id"],
                "category_name": row["category_name"],
                "total"        : round(self._f(row["total"]), 2),
                "count"        : int(row["tx_count"]),
            }
            for row in rows
        ]

    def _fetch_budget_cap_goals(self) -> List[Dict[str, Any]]:
        """
        Return all active budget_cap goals belonging to the user,
        with their category_id and target_amount.
        """
        sql = """
            SELECT goal_id, name, category_id, account_id,
                   target_amount, start_date, end_date
            FROM goals
            WHERE owner_id  = %s
              AND goal_type = 'budget_cap'
              AND status    = 'active'
              AND is_deleted = 0
        """
        rows = self._execute(sql, (self.user_id,), fetchall=True) or []
        return [
            {
                "goal_id"      : row["goal_id"],
                "name"         : row["name"],
                "category_id"  : row["category_id"],
                "account_id"   : row["account_id"],
                "target_amount": self._f(row["target_amount"]),
                "start_date"   : row["start_date"],
                "end_date"     : row["end_date"],
            }
            for row in rows
        ]

    def _fetch_category_spending_in_period(
        self,
        category_id : int,
        start       : date,
        end         : date,
    ) -> float:
        """Return total expense amount for a category in a given period."""
        sql = """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE is_deleted = 0
              AND user_id          = %s
              AND transaction_type = 'expense'
              AND category_id      = %s
              AND transaction_date BETWEEN %s AND %s
        """
        row = self._execute(
            sql, (self.user_id, category_id, start, end), fetchone=True
        ) or {}
        return self._f(row.get("total"))

    def _fetch_largest_transactions(
        self,
        start : date,
        end   : date,
        limit : int = 10,
    ) -> List[Dict[str, Any]]:
        """Return the N largest individual expense transactions in a period."""
        tenant = self._tenant_filter("t")
        sql = f"""
            SELECT
                t.transaction_id,
                t.title,
                t.amount,
                t.transaction_date,
                COALESCE(c.name, 'Uncategorised') AS category_name
            FROM transactions t
            LEFT JOIN categories c ON c.category_id = t.category_id
            WHERE t.is_deleted = 0
              AND t.transaction_type = 'expense'
              AND {tenant}
              AND t.transaction_date BETWEEN %s AND %s
            ORDER BY t.amount DESC
            LIMIT %s
        """
        rows = self._execute(
            sql, (self.user_id, start, end, limit), fetchall=True
        ) or []
        return [
            {
                "transaction_id" : row["transaction_id"],
                "title"          : row["title"],
                "amount"         : self._f(row["amount"]),
                "date"           : str(row["transaction_date"]),
                "category_name"  : row["category_name"],
            }
            for row in rows
        ]
    
    def _fetch_daily_expense_avg(
        self,
        start : date,
        end   : date,
    ) -> float:
        """
        Return the average daily expense amount between start and end.
        Only counts days that actually have transactions.
        """
        tenant = self._tenant_filter("t")
        sql = f"""
            SELECT AVG(daily_total) AS avg_daily
            FROM (
                SELECT DATE(t.transaction_date) AS tx_day,
                       SUM(t.amount)             AS daily_total
                FROM transactions t
                WHERE t.is_deleted = 0
                  AND t.transaction_type = 'expense'
                  AND {tenant}
                  AND t.transaction_date BETWEEN %s AND %s
                GROUP BY tx_day
            ) sub
        """
        row = self._execute(sql, (self.user_id, start, end), fetchone=True) or {}
        return self._f(row.get("avg_daily"))
    
    def _fetch_payment_method_breakdown(
        self,
        start : date,
        end   : date,
    ) -> Dict[str, float]:
        """Return expense totals keyed by payment_method for a period."""
        tenant = self._tenant_filter("t")
        sql = f"""
            SELECT
                t.payment_method,
                COALESCE(SUM(t.amount), 0) AS total
            FROM transactions t
            WHERE t.is_deleted = 0
              AND t.transaction_type = 'expense'
              AND {tenant}
              AND t.transaction_date BETWEEN %s AND %s
            GROUP BY t.payment_method
        """
        rows = self._execute(sql, (self.user_id, start, end), fetchall=True) or []
        return {row["payment_method"]: self._f(row["total"]) for row in rows}
    
    # ================================================================
    # INSIGHT GENERATORS
    # ================================================================

    # ----------------------------------------------------------------
    # 1. Spending Spike / Drop
    # ----------------------------------------------------------------

    def _insight_spending_spike(
        self,
        curr_start : date,
        curr_end   : date,
        prev_start : date,
        prev_end   : date,
    ) -> Optional[Insight]:
        """
        Compare total expenses this period vs the prior period.
        Emits a warning/critical when spending is significantly higher,
        or an 'info' when it is lower (positive feedback).
        """
        curr = self._fetch_period_totals(curr_start, curr_end)
        prev = self._fetch_period_totals(prev_start, prev_end)

        curr_exp = curr["total_expenses"]
        prev_exp = prev["total_expenses"]

        pct = self._pct_change(curr_exp, prev_exp)
        if pct is None:
            return None  # No prior data → skip

        warn_th  = self._th("spending_spike_warning_pct")
        crit_th  = self._th("spending_spike_critical_pct")

        data = {
            "current_spending" : curr_exp,
            "prior_spending"   : prev_exp,
            "change_pct"       : pct,
            "current_period"   : f"{curr_start} → {curr_end}",
            "prior_period"     : f"{prev_start} → {prev_end}",
        }

        if pct >= crit_th:
            return Insight(
                insight_id = "spending_spike",
                category   = InsightCategory.SPENDING,
                severity   = Severity.CRITICAL,
                title      = "⚠️  Spending Spike Detected",
                message    = (
                    f"Spending is {pct:.1f}% higher than the prior period "
                    f"({self._fmt(curr_exp)} vs {self._fmt(prev_exp)}). "
                    "Review your recent transactions."
                ),
                data = data,
            )
        elif pct >= warn_th:
            return Insight(
                insight_id = "spending_spike",
                category   = InsightCategory.SPENDING,
                severity   = Severity.WARNING,
                title      = "📈 Spending Up This Period",
                message    = (
                    f"Spending is {pct:.1f}% higher than the prior period "
                    f"({self._fmt(curr_exp)} vs {self._fmt(prev_exp)})."
                ),
                data = data,
            )
        elif pct <= -warn_th:
            return Insight(
                insight_id = "spending_down",
                category   = InsightCategory.SPENDING,
                severity   = Severity.INFO,
                title      = "✅ Spending Down — Great Work!",
                message    = (
                    f"Spending is {abs(pct):.1f}% lower than the prior period "
                    f"({self._fmt(curr_exp)} vs {self._fmt(prev_exp)}). "
                    "Keep it up!"
                ),
                data = data,
            )
        return None  # Change within normal range — no insight needed

    # ----------------------------------------------------------------
    # 2. Income Drop
    # ----------------------------------------------------------------

    def _insight_income_drop(
        self,
        curr_start : date,
        curr_end   : date,
        prev_start : date,
        prev_end   : date,
    ) -> Optional[Insight]:
        """Warn when income drops significantly vs the prior period."""
        curr = self._fetch_period_totals(curr_start, curr_end)
        prev = self._fetch_period_totals(prev_start, prev_end)

        curr_inc = curr["total_income"]
        prev_inc = prev["total_income"]

        pct = self._pct_change(curr_inc, prev_inc)
        if pct is None or pct >= 0:
            return None  # No prior data or income increased

        drop = abs(pct)
        warn_th = self._th("income_drop_warning_pct")
        crit_th = self._th("income_drop_critical_pct")

        data = {
            "current_income" : curr_inc,
            "prior_income"   : prev_inc,
            "change_pct"     : pct,
        }

        if drop >= crit_th:
            return Insight(
                insight_id = "income_drop",
                category   = InsightCategory.INCOME,
                severity   = Severity.CRITICAL,
                title      = "🚨 Significant Income Drop",
                message    = (
                    f"Income dropped {drop:.1f}% compared to the prior period "
                    f"({self._fmt(curr_inc)} vs {self._fmt(prev_inc)}). "
                    "Check your income sources."
                ),
                data = data,
            )
        elif drop >= warn_th:
            return Insight(
                insight_id = "income_drop",
                category   = InsightCategory.INCOME,
                severity   = Severity.WARNING,
                title      = "📉 Income Lower Than Usual",
                message    = (
                    f"Income is {drop:.1f}% lower than the prior period "
                    f"({self._fmt(curr_inc)} vs {self._fmt(prev_inc)})."
                ),
                data = data,
            )
        return None
    
    # ----------------------------------------------------------------
    # 3. No Income This Month
    # ----------------------------------------------------------------

    def _insight_no_income(
        self,
        curr_start : date,
        curr_end   : date,
    ) -> Optional[Insight]:
        """Emit a warning if no income has been recorded this month."""
        curr = self._fetch_period_totals(curr_start, curr_end)
        if curr["total_income"] > 0:
            return None

        return Insight(
            insight_id = "no_income_this_month",
            category   = InsightCategory.INCOME,
            severity   = Severity.WARNING,
            title      = "📭 No Income Recorded Yet",
            message    = (
                f"No income transactions found between {curr_start} and {curr_end}. "
                "Remember to log your income."
            ),
            data = {"period": f"{curr_start} → {curr_end}"},
        )

    # ----------------------------------------------------------------
    # 4. Savings Rate
    # ----------------------------------------------------------------

    def _insight_savings_rate(
        self,
        curr_start : date,
        curr_end   : date,
    ) -> Optional[Insight]:
        """
        Warn when the savings rate (net / income) falls below configured thresholds.
        Also celebrates a healthy savings rate.
        """
        curr = self._fetch_period_totals(curr_start, curr_end)
        income   = curr["total_income"]
        expenses = curr["total_expenses"]

        if income == 0:
            return None  # Can't compute rate with no income

        net  = income - expenses
        rate = round((net / income) * 100, 2)

        warn_th = self._th("savings_rate_warning_pct")
        crit_th = self._th("savings_rate_critical_pct")

        data = {
            "income"       : income,
            "expenses"     : expenses,
            "net_savings"  : net,
            "savings_rate" : rate,
        }

        if rate < crit_th:
            return Insight(
                insight_id = "savings_rate_low",
                category   = InsightCategory.SAVINGS,
                severity   = Severity.CRITICAL,
                title      = "🚨 Savings Rate Critically Low",
                message    = (
                    f"Your savings rate is {rate:.1f}% — below the critical threshold of "
                    f"{crit_th:.0f}%. You are spending {self._fmt(expenses)} against "
                    f"income of {self._fmt(income)}."
                ),
                data = data,
            )
        elif rate < warn_th:
            return Insight(
                insight_id = "savings_rate_low",
                category   = InsightCategory.SAVINGS,
                severity   = Severity.WARNING,
                title      = "⚠️  Savings Rate Below Target",
                message    = (
                    f"Your savings rate is {rate:.1f}%, below the recommended "
                    f"{warn_th:.0f}%. Consider reducing discretionary spending."
                ),
                data = data,
            )
        elif rate >= 30:
            return Insight(
                insight_id = "savings_rate_healthy",
                category   = InsightCategory.SAVINGS,
                severity   = Severity.INFO,
                title      = "🌟 Excellent Savings Rate",
                message    = (
                    f"Your savings rate is {rate:.1f}% — great financial discipline! "
                    f"Net savings this period: {self._fmt(net)}."
                ),
                data = data,
            )
        return None
    
    # ----------------------------------------------------------------
    # 5. Per-Category Spending Spike
    # ----------------------------------------------------------------

    def _insight_category_spikes(
        self,
        curr_start : date,
        curr_end   : date,
        prev_start : date,
        prev_end   : date,
    ) -> List[Insight]:
        """
        Compare per-category expense totals for current vs prior period.
        Returns one insight per category that breaches the threshold.
        """
        top_n    = self._th("top_categories_to_analyse")
        warn_th  = self._th("category_spike_warning_pct")
        crit_th  = self._th("category_spike_critical_pct")

        curr_cats = self._fetch_category_totals(curr_start, curr_end, limit=top_n)
        insights  : List[Insight] = []

        for cat in curr_cats:
            cid    = cat["category_id"]
            cname  = cat["category_name"]
            curr_t = cat["total"]
            prev_t = self._fetch_category_spending_in_period(cid, prev_start, prev_end)

            pct = self._pct_change(curr_t, prev_t)
            if pct is None or pct < warn_th:
                continue

            data = {
                "category_id"    : cid,
                "category_name"  : cname,
                "current_total"  : curr_t,
                "prior_total"    : prev_t,
                "change_pct"     : pct,
            }

            if pct >= crit_th:
                insights.append(Insight(
                    insight_id = f"category_spike_{cid}",
                    category   = InsightCategory.CATEGORY,
                    severity   = Severity.CRITICAL,
                    title      = f"🔥 {cname} Spending Surged",
                    message    = (
                        f"{cname} spending jumped {pct:.1f}% vs the prior period "
                        f"({self._fmt(curr_t)} vs {self._fmt(prev_t)}). "
                        "Consider reviewing these transactions."
                    ),
                    data = data,
                ))
            else:
                insights.append(Insight(
                    insight_id = f"category_spike_{cid}",
                    category   = InsightCategory.CATEGORY,
                    severity   = Severity.WARNING,
                    title      = f"📈 {cname} Spending Up",
                    message    = (
                        f"{cname} spending is {pct:.1f}% higher than the prior period "
                        f"({self._fmt(curr_t)} vs {self._fmt(prev_t)})."
                    ),
                    data = data,
                ))

        return insights

    # ----------------------------------------------------------------
    # 6. Budget Cap Alerts (from Goals)
    # ----------------------------------------------------------------

    def _insight_budget_caps(self) -> List[Insight]:
        """
        Check all active budget_cap goals and emit insights when
        spending is approaching or has exceeded the cap.
        """
        goals    = self._fetch_budget_cap_goals()
        insights : List[Insight] = []

        warn_th = self._th("budget_cap_warning_pct")
        crit_th = self._th("budget_cap_critical_pct")

        for goal in goals:
            cid    = goal["category_id"]
            if cid is None:
                continue

            start  = goal["start_date"]
            end    = goal["end_date"]
            cap    = goal["target_amount"]
            spent  = self._fetch_category_spending_in_period(cid, start, end)
            usage  = round((spent / cap) * 100, 2) if cap > 0 else 0.0
            remain = max(cap - spent, 0.0)

            data = {
                "goal_id"     : goal["goal_id"],
                "goal_name"   : goal["name"],
                "category_id" : cid,
                "cap_amount"  : cap,
                "spent"       : spent,
                "usage_pct"   : usage,
                "remaining"   : remain,
            }

            if usage >= crit_th:
                insights.append(Insight(
                    insight_id = f"budget_cap_exceeded_{goal['goal_id']}",
                    category   = InsightCategory.CATEGORY,
                    severity   = Severity.CRITICAL,
                    title      = f"🚨 Budget Cap Exceeded: {goal['name']}",
                    message    = (
                        f"You have spent {self._fmt(spent)} against a budget cap of "
                        f"{self._fmt(cap)} ({usage:.1f}% used). "
                        "You are over your set limit."
                    ),
                    data = data,
                ))
            elif usage >= warn_th:
                insights.append(Insight(
                    insight_id = f"budget_cap_warning_{goal['goal_id']}",
                    category   = InsightCategory.CATEGORY,
                    severity   = Severity.WARNING,
                    title      = f"⚠️  Approaching Budget Cap: {goal['name']}",
                    message    = (
                        f"You have used {usage:.1f}% of your {self._fmt(cap)} budget "
                        f"({self._fmt(spent)} spent, {self._fmt(remain)} remaining)."
                    ),
                    data = data,
                ))

        return insights

    # ----------------------------------------------------------------
    # 7. Top Category Shift
    # ----------------------------------------------------------------

    def _insight_top_category_shift(
        self,
        curr_start : date,
        curr_end   : date,
        prev_start : date,
        prev_end   : date,
    ) -> Optional[Insight]:
        """
        Detect when the top expense category changes between periods.
        """
        curr_cats = self._fetch_category_totals(curr_start, curr_end, limit=1)
        prev_cats = self._fetch_category_totals(prev_start, prev_end, limit=1)

        if not curr_cats or not prev_cats:
            return None

        curr_top = curr_cats[0]
        prev_top = prev_cats[0]

        if curr_top["category_id"] == prev_top["category_id"]:
            return None  # Same top category — no insight

        return Insight(
            insight_id = "top_category_shift",
            category   = InsightCategory.CATEGORY,
            severity   = Severity.INFO,
            title      = "🔄 Top Expense Category Changed",
            message    = (
                f"Your biggest expense category shifted from "
                f"'{prev_top['category_name']}' ({self._fmt(prev_top['total'])}) "
                f"to '{curr_top['category_name']}' ({self._fmt(curr_top['total'])})."
            ),
            data = {
                "current_top"  : curr_top,
                "previous_top" : prev_top,
            },
        )

    # ----------------------------------------------------------------
    # 8. Large Transaction Alert
    # ----------------------------------------------------------------

    def _insight_large_transactions(
        self,
        curr_start : date,
        curr_end   : date,
    ) -> List[Insight]:
        """
        Flag any single expense that exceeds X% of the monthly income.
        Uses the current period's income as the baseline.
        """
        curr     = self._fetch_period_totals(curr_start, curr_end)
        income   = curr["total_income"]
        if income == 0:
            return []

        threshold_pct = self._th("large_txn_income_pct")
        threshold_amt = round((threshold_pct / 100) * income, 2)

        large_txns = self._fetch_largest_transactions(curr_start, curr_end, limit=5)
        insights   : List[Insight] = []

        for txn in large_txns:
            if txn["amount"] < threshold_amt:
                break  # Sorted DESC — no point checking further

            pct_of_income = round((txn["amount"] / income) * 100, 2)
            insights.append(Insight(
                insight_id = f"large_transaction_{txn['transaction_id']}",
                category   = InsightCategory.TRANSACTION,
                severity   = Severity.WARNING,
                title      = "💸 Large Transaction Detected",
                message    = (
                    f"'{txn['title']}' on {txn['date']} cost {self._fmt(txn['amount'])} "
                    f"— that is {pct_of_income:.1f}% of your income this period. "
                    f"Category: {txn['category_name']}."
                ),
                data = {
                    **txn,
                    "pct_of_income"  : pct_of_income,
                    "income_baseline": income,
                    "threshold_amt"  : threshold_amt,
                },
            ))

        return insights

    # ----------------------------------------------------------------
    # 9. Daily Average Spending Spike
    # ----------------------------------------------------------------

    def _insight_daily_avg_spike(
        self,
        curr_start : date,
        curr_end   : date,
        prev_start : date,
        prev_end   : date,
    ) -> Optional[Insight]:
        """
        Compare the average daily spend this period vs the prior period.
        """
        curr_avg = self._fetch_daily_expense_avg(curr_start, curr_end)
        prev_avg = self._fetch_daily_expense_avg(prev_start, prev_end)

        pct = self._pct_change(curr_avg, prev_avg)
        if pct is None:
            return None

        warn_th = self._th("daily_avg_spike_warning_pct")
        crit_th = self._th("daily_avg_spike_critical_pct")

        data = {
            "current_daily_avg" : curr_avg,
            "prior_daily_avg"   : prev_avg,
            "change_pct"        : pct,
        }

        if pct >= crit_th:
            return Insight(
                insight_id = "daily_avg_spike",
                category   = InsightCategory.SPENDING,
                severity   = Severity.CRITICAL,
                title      = "📆 Daily Spending Average Surged",
                message    = (
                    f"Your average daily spending jumped {pct:.1f}% "
                    f"({self._fmt(curr_avg)}/day vs {self._fmt(prev_avg)}/day)."
                ),
                data = data,
            )
        elif pct >= warn_th:
            return Insight(
                insight_id = "daily_avg_spike",
                category   = InsightCategory.SPENDING,
                severity   = Severity.WARNING,
                title      = "📆 Daily Spending Average Up",
                message    = (
                    f"Your average daily spending is {pct:.1f}% higher than usual "
                    f"({self._fmt(curr_avg)}/day vs {self._fmt(prev_avg)}/day)."
                ),
                data = data,
            )
        return None

    # ----------------------------------------------------------------
    # 10. Debt Growing Insight
    # ----------------------------------------------------------------

    def _insight_debt_growing(
        self,
        curr_start : date,
        curr_end   : date,
    ) -> Optional[Insight]:
        """
        Warn when debt borrowed significantly outweighs debt repaid this period.
        """
        curr = self._fetch_period_totals(curr_start, curr_end)
        debt_in  = curr["total_debt_in"]
        debt_out = curr["total_debt_out"]
        income   = curr["total_income"]

        if debt_in == 0:
            return None  # No debt activity

        debt_net   = debt_in - debt_out
        ratio_pct  = round((debt_in / income) * 100, 2) if income > 0 else 0.0
        warn_ratio = self._th("debt_income_ratio_warning_pct")

        data = {
            "debt_borrowed" : debt_in,
            "debt_repaid"   : debt_out,
            "net_debt"      : debt_net,
            "debt_to_income": ratio_pct,
        }

        if ratio_pct >= warn_ratio and debt_net > 0:
            return Insight(
                insight_id = "debt_growing",
                category   = InsightCategory.DEBT,
                severity   = Severity.WARNING,
                title      = "📋 Debt Borrowing High",
                message    = (
                    f"You borrowed {self._fmt(debt_in)} vs repaying {self._fmt(debt_out)} "
                    f"this period. Debt borrowing is {ratio_pct:.1f}% of your income — "
                    f"above the recommended {warn_ratio:.0f}%."
                ),
                data = data,
            )
        elif debt_out > debt_in:
            return Insight(
                insight_id = "debt_reducing",
                category   = InsightCategory.DEBT,
                severity   = Severity.INFO,
                title      = "✅ Net Debt Reducing",
                message    = (
                    f"You repaid {self._fmt(debt_out)} vs borrowing {self._fmt(debt_in)} "
                    "this period. Your net debt position is improving."
                ),
                data = data,
            )
        return None

    # ----------------------------------------------------------------
    # 11. Payment Method Shift
    # ----------------------------------------------------------------

    def _insight_payment_method_shift(
        self,
        curr_start : date,
        curr_end   : date,
        prev_start : date,
        prev_end   : date,
    ) -> Optional[Insight]:
        """
        Detect a significant shift in dominant payment method between periods.
        Useful for flagging unusual card or mobile money usage.
        """
        curr_pm = self._fetch_payment_method_breakdown(curr_start, curr_end)
        prev_pm = self._fetch_payment_method_breakdown(prev_start, prev_end)

        if not curr_pm or not prev_pm:
            return None

        curr_top = max(curr_pm, key=curr_pm.get)
        prev_top = max(prev_pm, key=prev_pm.get)

        if curr_top == prev_top:
            return None  # Same dominant method

        return Insight(
            insight_id = "payment_method_shift",
            category   = InsightCategory.PAYMENT,
            severity   = Severity.INFO,
            title      = "💳 Payment Method Shift Detected",
            message    = (
                f"Your dominant payment method changed from '{prev_top}' "
                f"({self._fmt(prev_pm[prev_top])}) to '{curr_top}' "
                f"({self._fmt(curr_pm[curr_top])}) this period."
            ),
            data = {
                "current_breakdown"  : curr_pm,
                "prior_breakdown"    : prev_pm,
                "current_top_method" : curr_top,
                "prior_top_method"   : prev_top,
            },
        )

    # ----------------------------------------------------------------
    # 12. Spending Streak (consecutive months under prior month)
    # ----------------------------------------------------------------

    def _insight_spending_streak(self) -> Optional[Insight]:
        """
        Detect if spending has been consistently lower month-over-month
        for the past N months — a positive reinforcement insight.
        """
        n = self._th("streak_months_to_check")
        today = date.today()
        from datetime import timedelta

        monthly_totals: List[float] = []
        ref = today.replace(day=1)

        for _ in range(n + 1):  # +1 to have a baseline prior month
            last_day = (ref - timedelta(days=1))
            start    = last_day.replace(day=1)
            end      = last_day
            totals   = self._fetch_period_totals(start, end)
            monthly_totals.append(totals["total_expenses"])
            ref = start  # step back one more month

        monthly_totals.reverse()  # oldest → newest

        # Check if every month is lower than the one before it
        streak = 0
        for i in range(1, len(monthly_totals)):
            if monthly_totals[i] < monthly_totals[i - 1]:
                streak += 1
            else:
                streak = 0

        if streak >= n:
            return Insight(
                insight_id = "spending_streak",
                category   = InsightCategory.SPENDING,
                severity   = Severity.INFO,
                title      = f"🏆 {streak}-Month Spending Streak!",
                message    = (
                    f"You have reduced spending for {streak} consecutive months. "
                    "Excellent financial discipline — keep the momentum going!"
                ),
                data = {"streak_months": streak, "monthly_totals": monthly_totals},
            )
        return None

    # ================================================================
    # PUBLIC API
    # ================================================================

    def get_spending_insights(
        self,
        curr_start : Optional[date] = None,
        curr_end   : Optional[date] = None,
        prev_start : Optional[date] = None,
        prev_end   : Optional[date] = None,
    ) -> List[Insight]:
        """
        Run all spending-related insights.

        Parameters default to the current month vs prior month when omitted.
        """
        cs, ce = curr_start or self._current_month_range()[0], curr_end or self._current_month_range()[1]
        ps, pe = prev_start or self._prior_month_range()[0],   prev_end or self._prior_month_range()[1]

        results: List[Insight] = []

        spike = self._insight_spending_spike(cs, ce, ps, pe)
        if spike:
            results.append(spike)

        daily = self._insight_daily_avg_spike(cs, ce, ps, pe)
        if daily:
            results.append(daily)

        streak = self._insight_spending_streak()
        if streak:
            results.append(streak)

        return results

    def get_income_insights(
        self,
        curr_start : Optional[date] = None,
        curr_end   : Optional[date] = None,
        prev_start : Optional[date] = None,
        prev_end   : Optional[date] = None,
    ) -> List[Insight]:
        """Run all income-related insights."""
        cs, ce = curr_start or self._current_month_range()[0], curr_end or self._current_month_range()[1]
        ps, pe = prev_start or self._prior_month_range()[0],   prev_end or self._prior_month_range()[1]

        results: List[Insight] = []

        drop = self._insight_income_drop(cs, ce, ps, pe)
        if drop:
            results.append(drop)

        no_inc = self._insight_no_income(cs, ce)
        if no_inc:
            results.append(no_inc)

        return results

    def get_category_insights(
        self,
        curr_start : Optional[date] = None,
        curr_end   : Optional[date] = None,
        prev_start : Optional[date] = None,
        prev_end   : Optional[date] = None,
    ) -> List[Insight]:
        """Run all category-level insights (spikes, budget caps, shifts)."""
        cs, ce = curr_start or self._current_month_range()[0], curr_end or self._current_month_range()[1]
        ps, pe = prev_start or self._prior_month_range()[0],   prev_end or self._prior_month_range()[1]

        results: List[Insight] = []
        results.extend(self._insight_category_spikes(cs, ce, ps, pe))
        results.extend(self._insight_budget_caps())

        shift = self._insight_top_category_shift(cs, ce, ps, pe)
        if shift:
            results.append(shift)

        return results

    def get_transaction_insights(
        self,
        curr_start : Optional[date] = None,
        curr_end   : Optional[date] = None,
    ) -> List[Insight]:
        """Run transaction-level insights (large transaction alerts)."""
        cs, ce = curr_start or self._current_month_range()[0], curr_end or self._current_month_range()[1]
        return self._insight_large_transactions(cs, ce)

    def get_debt_insights(
        self,
        curr_start : Optional[date] = None,
        curr_end   : Optional[date] = None,
    ) -> List[Insight]:
        """Run debt-related insights."""
        cs, ce = curr_start or self._current_month_range()[0], curr_end or self._current_month_range()[1]
        result = self._insight_debt_growing(cs, ce)
        return [result] if result else []

    def get_savings_insights(
        self,
        curr_start : Optional[date] = None,
        curr_end   : Optional[date] = None,
    ) -> List[Insight]:
        """Run savings and net-worth insights."""
        cs, ce = curr_start or self._current_month_range()[0], curr_end or self._current_month_range()[1]
        result = self._insight_savings_rate(cs, ce)
        return [result] if result else []

    def get_payment_insights(
        self,
        curr_start : Optional[date] = None,
        curr_end   : Optional[date] = None,
        prev_start : Optional[date] = None,
        prev_end   : Optional[date] = None,
    ) -> List[Insight]:
        """Run payment method insights."""
        cs, ce = curr_start or self._current_month_range()[0], curr_end or self._current_month_range()[1]
        ps, pe = prev_start or self._prior_month_range()[0],   prev_end or self._prior_month_range()[1]
        result = self._insight_payment_method_shift(cs, ce, ps, pe)
        return [result] if result else []

    def get_insights_by_category(
        self,
        category   : str,
        curr_start : Optional[date] = None,
        curr_end   : Optional[date] = None,
        prev_start : Optional[date] = None,
        prev_end   : Optional[date] = None,
    ) -> List[Insight]:
        """
        Return insights for a specific InsightCategory.

        Parameters
        ----------
        category : One of InsightCategory constants
                   ("spending", "income", "savings", "category",
                    "transaction", "debt", "payment")
        """
        if category not in InsightCategory.ALL:
            raise InsightsValidationError(
                f"Invalid category '{category}'. "
                f"Choose from: {sorted(InsightCategory.ALL)}"
            )
        dispatch = {
            InsightCategory.SPENDING    : self.get_spending_insights,
            InsightCategory.INCOME      : self.get_income_insights,
            InsightCategory.SAVINGS     : self.get_savings_insights,
            InsightCategory.CATEGORY    : self.get_category_insights,
            InsightCategory.TRANSACTION : lambda **kw: self.get_transaction_insights(
                                              kw.get("curr_start"), kw.get("curr_end")),
            InsightCategory.DEBT        : lambda **kw: self.get_debt_insights(
                                              kw.get("curr_start"), kw.get("curr_end")),
            InsightCategory.PAYMENT     : self.get_payment_insights,
        }
        return dispatch[category](
            curr_start=curr_start,
            curr_end=curr_end,
            prev_start=prev_start,
            prev_end=prev_end,
        )

    def get_all_insights(
        self,
        curr_start       : Optional[date] = None,
        curr_end         : Optional[date] = None,
        prev_start       : Optional[date] = None,
        prev_end         : Optional[date] = None,
        severity_filter  : Optional[str]  = None,
        category_filter  : Optional[str]  = None,
        as_dicts         : bool = False,
    ) -> List[Any]:
        """
        Run every insight generator and return a unified list.

        Parameters
        ----------
        curr_start      : Start of comparison period  (default: this month)
        curr_end        : End of comparison period    (default: today)
        prev_start      : Start of baseline period    (default: last month)
        prev_end        : End of baseline period      (default: last day of last month)
        severity_filter : Only return insights with this severity level
        category_filter : Only return insights in this category
        as_dicts        : When True, each Insight is returned as a plain dict

        Returns
        -------
        List[Insight] or List[Dict]  — sorted critical → warning → info
        """
        cs = curr_start or self._current_month_range()[0]
        ce = curr_end   or self._current_month_range()[1]
        ps = prev_start or self._prior_month_range()[0]
        pe = prev_end   or self._prior_month_range()[1]

        all_insights: List[Insight] = []
        all_insights.extend(self.get_spending_insights(cs, ce, ps, pe))
        all_insights.extend(self.get_income_insights(cs, ce, ps, pe))
        all_insights.extend(self.get_savings_insights(cs, ce))
        all_insights.extend(self.get_category_insights(cs, ce, ps, pe))
        all_insights.extend(self.get_transaction_insights(cs, ce))
        all_insights.extend(self.get_debt_insights(cs, ce))
        all_insights.extend(self.get_payment_insights(cs, ce, ps, pe))

        # ── Optional filters ────────────────────────────────────────
        if severity_filter:
            all_insights = [i for i in all_insights if i.severity == severity_filter]
        if category_filter:
            all_insights = [i for i in all_insights if i.category == category_filter]

        # ── Sort: critical → warning → info ─────────────────────────
        _order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
        all_insights.sort(key=lambda i: _order.get(i.severity, 99))

        if as_dicts:
            return [i.to_dict() for i in all_insights]
        return all_insights

    def get_summary(
        self,
        curr_start : Optional[date] = None,
        curr_end   : Optional[date] = None,
        prev_start : Optional[date] = None,
        prev_end   : Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Return a high-level summary of all insights.

        Useful for dashboard banners or notification badges.

        Returns
        -------
        {
            "total"          : int,
            "critical"       : int,
            "warning"        : int,
            "info"           : int,
            "by_category"    : {"spending": N, "income": N, ...},
            "top_insight"    : InsightDict | None,   # highest-severity insight
            "insights"       : List[InsightDict],
            "generated_at"   : ISO-8601 str,
            "period"         : {"current": "...", "prior": "..."}
        }
        """
        cs = curr_start or self._current_month_range()[0]
        ce = curr_end   or self._current_month_range()[1]
        ps = prev_start or self._prior_month_range()[0]
        pe = prev_end   or self._prior_month_range()[1]

        insights = self.get_all_insights(cs, ce, ps, pe)

        by_severity  : Dict[str, int] = {Severity.CRITICAL: 0, Severity.WARNING: 0, Severity.INFO: 0}
        by_category  : Dict[str, int] = {c: 0 for c in InsightCategory.ALL}

        for ins in insights:
            by_severity[ins.severity]  = by_severity.get(ins.severity, 0)  + 1
            by_category[ins.category]  = by_category.get(ins.category, 0)  + 1

        return {
            "total"        : len(insights),
            "critical"     : by_severity[Severity.CRITICAL],
            "warning"      : by_severity[Severity.WARNING],
            "info"         : by_severity[Severity.INFO],
            "by_category"  : by_category,
            "top_insight"  : insights[0].to_dict() if insights else None,
            "insights"     : [i.to_dict() for i in insights],
            "generated_at" : datetime.now().isoformat(),
            "period"       : {
                "current" : f"{cs} → {ce}",
                "prior"   : f"{ps} → {pe}",
            },
        }


# ============================================================
# Re-export for clean imports from features.insights
# ============================================================

__all__ = [
    "InsightsEngine",
    "Insight",
    "InsightCategory",
    "Severity",
    "DEFAULT_THRESHOLDS",
    "InsightsError",
    "InsightsValidationError",
    "InsightsDatabaseError",
]