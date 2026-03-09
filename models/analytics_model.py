#Queriees for reports insights and analytics
# models/analytics_model.py
# Queries for reports, insights and analytics
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal

import mysql.connector


# ================================================================
# Custom Exceptions
# ================================================================

class AnalyticsError(Exception):
    """Base exception for analytics operations."""


class AnalyticsValidationError(AnalyticsError):
    """Raised when invalid parameters are supplied."""


class AnalyticsDatabaseError(AnalyticsError):
    """Raised when a database-level error occurs."""


# ================================================================
# Valid Enums (mirrors TransactionModel)
# ================================================================

VALID_TRANSACTION_TYPES = {
    "income", "expense", "transfer",
    "debt_repaid", "debt_borrowed",
    "investment_deposit", "investment_withdraw",
}

VALID_PAYMENT_METHODS = {"cash", "bank", "mobile_money", "credit_card", "other"}

VALID_PERIODS = {"daily", "weekly", "monthly", "yearly"}


# ================================================================
# AnalyticsModel
# ================================================================

class AnalyticsModel:
    """
    Read-only analytics engine for the budget tracker.

    All queries respect row-level tenant isolation:
      - Regular users  → see only their own transactions.
      - Admins         → global_view=True shows all data; False shows own.

    Public API
    ----------
    summary()                  – Total income, expenses, net cash flow, savings rate.
    top_categories()           – Ranked categories by total spend or income.
    trends()                   – Income/expense totals grouped by period.
    payment_method_breakdown() – Spending split by payment method.
    monthly_comparison()       – Side-by-side month comparisons for a given year.
    daily_spending()           – Day-by-day expense totals over a date range.
    """

    def __init__(
        self,
        conn: mysql.connector.MySQLConnection,
        current_user: Dict[str, Any],
    ) -> None:
        self.conn = conn
        self.user = current_user
        self.user_id: Optional[int] = current_user.get("user_id")
        self.role: Optional[str] = current_user.get("role")

    # ----------------------------------------------------------------
    # Internal Helpers
    # ----------------------------------------------------------------

    def _execute(
        self,
        sql: str,
        params: Tuple[Any, ...] = (),
        *,
        fetchone: bool = False,
        fetchall: bool = False,
    ) -> Any:
        """Unified SQL executor — analytics queries are always SELECT."""
        if fetchone and fetchall:
            raise AnalyticsDatabaseError("fetchone and fetchall cannot both be True.")
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
        except mysql.connector.Error as e:
            raise AnalyticsDatabaseError(f"MySQL Error: {e}") from e

    def _tenant_filter(self, alias: str = "t", *, global_view: bool = False) -> str:
        """
        Row-level isolation — mirrors the pattern used across all models.

        Admin + global_view=True  → no user filter (sees everything).
        Admin + global_view=False → scoped to admin's own user_id.
        User  + global_view=True  → raises AnalyticsValidationError.
        User  + global_view=False → scoped to user's own user_id.
        """
        if self.role == "admin":
            if global_view:
                return f"{alias}.is_global = 1"            # No filter — admin global view
            return f"{alias}.user_id = %s"

        # Regular user
        if global_view:
            raise AnalyticsValidationError("Users can only view their own data.")
        return f"{alias}.user_id = %s"

    def _needs_user_param(self, global_view: bool) -> bool:
        """True when _tenant_filter() produced a %s placeholder."""
        return not (self.role == "admin" and global_view)

    def _validate_dates(
        self,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> None:
        if start_date and end_date and start_date > end_date:
            raise AnalyticsValidationError(
                "start_date cannot be after end_date."
            )

    def _decimal_to_float(self, value: Any) -> float:
        """Safely coerce Decimal / None to float."""
        if value is None:
            return 0.0
        return float(value)
    
    # ----------------------------------------------------------------
    # 1. Summary — Total Income vs Expenses
    # ----------------------------------------------------------------

    def summary(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        *,
        global_view: bool = False,
    ) -> Dict[str, Any]:
        """
        Return an aggregated financial summary for the given period.

        Returns
        -------
        {
            "total_income":      float,
            "total_expenses":    float,
            "total_debt_in":     float,   # debt_borrowed
            "total_debt_out":    float,   # debt_repaid
            "total_invested":    float,   # investment_deposit
            "total_withdrawn":   float,   # investment_withdraw
            "net_cash_flow":     float,   # income - expenses
            "savings_rate":      float,   # (net / income) * 100  or 0
            "period": { "start": ..., "end": ... }
        }
        """
        self._validate_dates(start_date, end_date)
        tenant = self._tenant_filter("t", global_view=global_view)

        sql = f"""
            SELECT
                COALESCE(SUM(CASE WHEN t.transaction_type = 'income'               THEN t.amount ELSE 0 END), 0) AS total_income,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'expense'              THEN t.amount ELSE 0 END), 0) AS total_expenses,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'debt_borrowed'        THEN t.amount ELSE 0 END), 0) AS total_debt_in,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'debt_repaid'          THEN t.amount ELSE 0 END), 0) AS total_debt_out,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'investment_deposit'   THEN t.amount ELSE 0 END), 0) AS total_invested,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'investment_withdraw'  THEN t.amount ELSE 0 END), 0) AS total_withdrawn,
                COUNT(*) AS transaction_count
            FROM transactions t
            WHERE t.is_deleted = 0
              AND {tenant}
        """
        params: List[Any] = []
        if self._needs_user_param(global_view):
            params.append(self.user_id)

        if start_date:
            sql += " AND t.transaction_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND t.transaction_date <= %s"
            params.append(end_date)

        row = self._execute(sql, tuple(params), fetchone=True) or {}

        income   = self._decimal_to_float(row.get("total_income"))
        expenses = self._decimal_to_float(row.get("total_expenses"))
        net      = income - expenses
        savings_rate = round((net / income * 100), 2) if income > 0 else 0.0

        return {
            "total_income":    round(income, 2),
            "total_expenses":  round(expenses, 2),
            "total_debt_in":   round(self._decimal_to_float(row.get("total_debt_in")), 2),
            "total_debt_out":  round(self._decimal_to_float(row.get("total_debt_out")), 2),
            "total_invested":  round(self._decimal_to_float(row.get("total_invested")), 2),
            "total_withdrawn": round(self._decimal_to_float(row.get("total_withdrawn")), 2),
            "net_cash_flow":   round(net, 2),
            "savings_rate":    savings_rate,
            "transaction_count": int(row.get("transaction_count") or 0),
            "period": {
                "start": str(start_date) if start_date else None,
                "end":   str(end_date)   if end_date   else None,
            },
        }

    # ----------------------------------------------------------------
    # 2. Top Categories
    # ----------------------------------------------------------------

    def top_categories(
        self,
        transaction_type: str = "expense",
        limit: int = 100,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        *,
        global_view: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Return the top `limit` categories ranked by total amount.

        Parameters
        ----------
        transaction_type : one of VALID_TRANSACTION_TYPES (default 'expense')
        limit            : max number of categories to return (default 50)

        Returns
        -------
        [
            {
                "category_id":   int | None,
                "category_name": str,          # 'Uncategorised' if NULL
                "total":         float,
                "count":         int,
                "percentage":    float          # share of the type's grand total
            },
            ...
        ]
        """
        if transaction_type not in VALID_TRANSACTION_TYPES:
            raise AnalyticsValidationError(
                f"Invalid transaction_type '{transaction_type}'. "
                f"Choose from: {sorted(VALID_TRANSACTION_TYPES)}"
            )
        if limit < 1:
            raise AnalyticsValidationError("limit must be >= 1.")
        self._validate_dates(start_date, end_date)

        tenant = self._tenant_filter("t", global_view=global_view)

        sql = f"""
            SELECT
                t.category_id,
                COALESCE(c.name, 'Uncategorised') AS category_name,
                COALESCE(SUM(t.amount), 0)        AS total,
                COUNT(*)                           AS tx_count
            FROM transactions t
            LEFT JOIN categories c ON c.category_id = t.category_id
            WHERE t.is_deleted = 0
              AND t.transaction_type = %s
              AND {tenant}
        """
        params: List[Any] = [transaction_type]
        if self._needs_user_param(global_view):
            params.append(self.user_id)

        if start_date:
            sql += " AND t.transaction_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND t.transaction_date <= %s"
            params.append(end_date)

        sql += " GROUP BY t.category_id, c.name ORDER BY total DESC LIMIT %s"
        params.append(limit)

        rows = self._execute(sql, tuple(params), fetchall=True) or []

        grand_total = sum(self._decimal_to_float(r["total"]) for r in rows)

        result = []
        for row in rows:
            total = self._decimal_to_float(row["total"])
            result.append({
                "category_id":   row["category_id"],
                "category_name": row["category_name"],
                "total":         round(total, 2),
                "count":         int(row["tx_count"]),
                "percentage":    round((total / grand_total * 100), 2) if grand_total > 0 else 0.0,
            })
        return result

    # ----------------------------------------------------------------
    # 3. Trends Over Time
    # ----------------------------------------------------------------

    def trends(
        self,
        period: str = "monthly",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        *,
        global_view: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Return income, expense and debt_borrowed, debt_repaid, investment_deposit and
         investment_withdrawal totals grouped by time period.

        Parameters
        ----------
        period : 'daily' | 'weekly' | 'monthly' | 'yearly'

        Returns
        -------
        [
            {
                "period":        str,    # e.g. '2024-03' for monthly
                "total_income":  float,
                "total_expenses":float,
                "total_debt_in": float,
                "total_debt_out":float,
                "total_investment_deposit": float,
                "total_investment_withdrawal": float,
                "net":           float
            },
            ...
        ]  sorted ascending by period.
        """
        if period not in VALID_PERIODS:
            raise AnalyticsValidationError(
                f"Invalid period '{period}'. Choose from: {sorted(VALID_PERIODS)}"
            )
        self._validate_dates(start_date, end_date)

        # Build the GROUP BY expression per period
        period_expr = {
            "daily":   "DATE_FORMAT(t.transaction_date, '%Y-%m-%d')",
            "weekly":  "DATE_FORMAT(t.transaction_date, '%x-W%v')",   # ISO week
            "monthly": "DATE_FORMAT(t.transaction_date, '%Y-%m')",
            "yearly":  "DATE_FORMAT(t.transaction_date, '%Y')",
        }[period]

        tenant = self._tenant_filter("t", global_view=global_view)

        sql = f"""
            SELECT
                {period_expr} AS period_label,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'income'  THEN t.amount ELSE 0 END), 0) AS total_income,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'expense' THEN t.amount ELSE 0 END), 0) AS total_expenses,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'debt_borrowed' THEN t.amount ELSE 0 END), 0) AS total_debt_in,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'debt_repaid' THEN t.amount ELSE 0 END), 0) AS total_debt_out,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'investment_deposit' THEN t.amount ELSE 0 END), 0) AS total_investment_deposit,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'investment_withdraw' THEN t.amount ELSE 0 END), 0) AS total_investment_withdrawal
            FROM transactions t
            WHERE t.is_deleted = 0
              AND t.transaction_type IN ('income', 'expense', 
              'debt_borrowed', 'debt_repaid', 'investment_deposit', 'investment_withdraw')
              AND {tenant}
        """
        params: List[Any] = []
        if self._needs_user_param(global_view):
            params.append(self.user_id)

        if start_date:
            sql += " AND t.transaction_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND t.transaction_date <= %s"
            params.append(end_date)

        sql += f" GROUP BY {period_expr} ORDER BY period_label ASC"

        rows = self._execute(sql, tuple(params), fetchall=True) or []

        result = []
        for row in rows:
            income   = self._decimal_to_float(row["total_income"])
            expenses = self._decimal_to_float(row["total_expenses"])
            debt_in  = self._decimal_to_float(row["total_debt_in"])
            debt_out = self._decimal_to_float(row["total_debt_out"])
            invest_deposit = self._decimal_to_float(row["total_investment_deposit"])
            invest_withdraw = self._decimal_to_float(row["total_investment_withdrawal"])
            result.append({
                "period":         row["period_label"],
                "total_income":   round(income, 2),
                "total_expenses": round(expenses, 2),
                "total_debt_in":  round(debt_in, 2),
                "total_debt_out": round(debt_out, 2),
                "total_investment_deposit": round(invest_deposit, 2),
                "total_investment_withdrawal": round(invest_withdraw, 2),
                "net":            round(income - expenses - debt_out + debt_in + invest_withdraw - invest_deposit, 2),
            })
        return result

    # ----------------------------------------------------------------
    # 4. Payment Method Breakdown
    # ----------------------------------------------------------------

    def payment_method_breakdown(
        self,
        transaction_type: str = "expense",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        *,
        global_view: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Return spending (or income) split by payment method.

        Returns
        -------
        [
            {
                "payment_method": str,
                "total":          float,
                "count":          int,
                "percentage":     float
            },
            ...
        ]
        """
        if transaction_type not in VALID_TRANSACTION_TYPES:
            raise AnalyticsValidationError(
                f"Invalid transaction_type '{transaction_type}'. "
                f"Choose from: {sorted(VALID_TRANSACTION_TYPES)}"
            )
        self._validate_dates(start_date, end_date)

        tenant = self._tenant_filter("t", global_view=global_view)

        sql = f"""
            SELECT
                t.payment_method,
                COALESCE(SUM(t.amount), 0) AS total,
                COUNT(*)                    AS tx_count
            FROM transactions t
            WHERE t.is_deleted = 0
              AND t.transaction_type = %s
              AND {tenant}
        """
        params: List[Any] = [transaction_type]
        if self._needs_user_param(global_view):
            params.append(self.user_id)

        if start_date:
            sql += " AND t.transaction_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND t.transaction_date <= %s"
            params.append(end_date)

        sql += " GROUP BY t.payment_method ORDER BY total DESC"

        rows = self._execute(sql, tuple(params), fetchall=True) or []

        grand_total = sum(self._decimal_to_float(r["total"]) for r in rows)

        result = []
        for row in rows:
            total = self._decimal_to_float(row["total"])
            result.append({
                "payment_method": row["payment_method"],
                "total":          round(total, 2),
                "count":          int(row["tx_count"]),
                "percentage":     round((total / grand_total * 100), 2) if grand_total > 0 else 0.0,
            })
        return result
    
    # ----------------------------------------------------------------
    # 5. Monthly Comparison (year view)
    # ----------------------------------------------------------------

    def monthly_comparison(
        self,
        year: int,
        *,
        global_view: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Return a 12-row breakdown (Jan–Dec) for a given year,
        showing income, expenses, debt_borrowed, debt_repaid, investment_deposit, investment_withdrawal, and net for each month.

        Returns
        -------
        [
            {
                "month":          int,    # 1–12
                "month_label":    str,    # 'Jan', 'Feb', …
                "total_income":   float,
                "total_expenses": float,
                "total_debt_in":  float,
                "total_debt_out": float,
                "total_investment_deposit": float,
                "total_investment_withdrawal": float,
                "net":            float
            },
            ...
        ]
        """
        if not (2000 <= year <= 2100):
            raise AnalyticsValidationError("year must be between 2000 and 2100.")

        tenant = self._tenant_filter("t", global_view=global_view)

        sql = f"""
            SELECT
                MONTH(t.transaction_date)  AS month_num,
                DATE_FORMAT(t.transaction_date, '%b') AS month_label,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'income'  THEN t.amount ELSE 0 END), 0) AS total_income,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'expense' THEN t.amount ELSE 0 END), 0) AS total_expenses,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'debt_borrowed' THEN t.amount ELSE 0 END), 0) AS total_debt_in,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'debt_repaid' THEN t.amount ELSE 0 END), 0) AS total_debt_out,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'investment_deposit' THEN t.amount ELSE 0 END), 0) AS total_investment_deposit,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'investment_withdraw' THEN t.amount ELSE 0 END), 0) AS total_investment_withdrawal
            FROM transactions t
            WHERE t.is_deleted = 0
              AND YEAR(t.transaction_date) = %s
              AND t.transaction_type IN ('income', 'expense', 
              'debt_borrowed', 'debt_repaid', 'investment_deposit', 'investment_withdraw')
              AND {tenant}
            GROUP BY month_num, month_label
            ORDER BY month_num ASC
        """
        params: List[Any] = [year]
        if self._needs_user_param(global_view):
            params.append(self.user_id)

        rows = self._execute(sql, tuple(params), fetchall=True) or []

        # Build a full 12-month scaffold (fill missing months with zeros)
        MONTH_LABELS = ["Jan","Feb","Mar","Apr","May","Jun",
                        "Jul","Aug","Sep","Oct","Nov","Dec"]

        row_map: Dict[int, Dict] = {row["month_num"]: row for row in rows}

        result = []
        for m in range(1, 13):
            row = row_map.get(m, {})
            income   = self._decimal_to_float(row.get("total_income"))
            expenses = self._decimal_to_float(row.get("total_expenses"))
            debt_in  = self._decimal_to_float(row.get("total_debt_in"))
            debt_out = self._decimal_to_float(row.get("total_debt_out"))
            invest_deposit = self._decimal_to_float(row.get("total_investment_deposit"))
            invest_withdraw = self._decimal_to_float(row.get("total_investment_withdrawal"))
            result.append({
                "month":          m,
                "month_label":    MONTH_LABELS[m - 1],
                "total_income":   round(income, 2),
                "total_expenses": round(expenses, 2),
                "total_debt_in":  round(debt_in, 2),
                "total_debt_out": round(debt_out, 2),
                "total_investment_deposit": round(invest_deposit, 2),
                "total_investment_withdrawal": round(invest_withdraw, 2),
                "net":            round(income - expenses, 2),
            })
        return result

    # ----------------------------------------------------------------
    # 6. Daily Spending
    # ----------------------------------------------------------------

    def daily_spending(
        self,
        start_date: date,
        end_date: date,
        *,
        global_view: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Return day-by-day expense totals over a date range.
        Useful for heatmaps and granular spending analysis.

        Returns
        -------
        [
            {
                "date":  str,   # 'YYYY-MM-DD'
                "total": float,
                "count": int
            },
            ...
        ]  — only days WITH transactions are included.
        """
        self._validate_dates(start_date, end_date)

        tenant = self._tenant_filter("t", global_view=global_view)

        sql = f"""
            SELECT
                DATE_FORMAT(t.transaction_date, '%Y-%m-%d') AS tx_date,
                COALESCE(SUM(t.amount), 0)                  AS total,
                COUNT(*)                                     AS tx_count
            FROM transactions t
            WHERE t.is_deleted = 0
              AND t.transaction_type = 'expense'
              AND t.transaction_date BETWEEN %s AND %s
              AND {tenant}
            GROUP BY tx_date
            ORDER BY tx_date ASC
        """
        params: List[Any] = [start_date, end_date]
        if self._needs_user_param(global_view):
            params.append(self.user_id)

        rows = self._execute(sql, tuple(params), fetchall=True) or []

        return [
            {
                "date":  row["tx_date"],
                "total": round(self._decimal_to_float(row["total"]), 2),
                "count": int(row["tx_count"]),
            }
            for row in rows
        ]



