#Manage and evaluate savings ad spendings
# features/goals.py
"""
============================================================
 GoalService — Dynamic Progress Tracking for Financial Goals
 ------------------------------------------------------------
 Sits above GoalModel and computes LIVE progress by querying
 the transactions table — no stored "current_amount" to drift
 out of sync.

 Goal Type Logic:
 ┌─────────────┬─────────────────────────────────────────────┐
 │ saving      │ Sum income/transfer-in on linked account    │
 │             │ from start_date → today (or end_date)       │
 ├─────────────┼─────────────────────────────────────────────┤
 │ spending    │ Sum expenses on linked category within      │
 │             │ the goal period                             │
 ├─────────────┼─────────────────────────────────────────────┤
 │ budget_cap  │ Same as spending — progress > target means  │
 │             │ the cap is EXCEEDED (progress is 'bad')     │
 └─────────────┴─────────────────────────────────────────────┘

 Public API
 ------------------------------------------------------------
 GoalService.create_goal(**data)           → Dict
 GoalService.get_goal(goal_id)             → Dict
 GoalService.update_goal(goal_id, **data)  → Dict
 GoalService.delete_goal(goal_id, soft)    → Dict
 GoalService.list_goals(...)               → Dict  (with progress)
 GoalService.get_progress(goal_id)         → Dict
 GoalService.get_all_progress()            → List[Dict]
 GoalService.check_budget_cap(category_id) → Dict
 GoalService.get_summary()                 → Dict
 GoalService.auto_update_statuses()        → Dict
============================================================
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import mysql.connector

from models.goal_model import (
    GoalModel,
    GoalError,
    GoalNotFoundError,
    GoalValidationError,
    GoalDatabaseError,
)
from models.transactions_model import TransactionModel
from models.account_model import AccountModel
from models.category_model import CategoryModel


# ============================================================
# Re-export exceptions so callers only import from features.goals
# ============================================================
__all__ = [
    "GoalService",
    "GoalError",
    "GoalNotFoundError",
    "GoalValidationError",
    "GoalDatabaseError",
]


class GoalService:
    """
    Orchestrates goal CRUD and live progress tracking.

    Dependencies injected:
      - conn         : active MySQL connection
      - current_user : {"user_id": int, "role": str, "username": str}
    """

    def __init__(self, conn: mysql.connector.MySQLConnection,
                 current_user: Dict[str, Any]) -> None:
        self.conn        = conn
        self.user        = current_user
        self.user_id     = current_user["user_id"]

        # Model layer dependencies
        self.goal_model  = GoalModel(conn, current_user)
        self.tx_model    = TransactionModel(conn, current_user)
        self.acc_model   = AccountModel(conn, current_user)
        self.cat_model   = CategoryModel(conn, current_user)

    # ============================================================
    # Internal Helpers
    # ============================================================

    def _execute(self, sql: str, params: tuple = (), *, fetchone=False, fetchall=False):
        """Thin SQL executor for internal progress queries."""
        try:
            with self.conn.cursor(dictionary=True) as cur:
                cur.execute(sql, params)
                if fetchone:
                    return cur.fetchone()
                if fetchall:
                    return cur.fetchall()
                self.conn.commit()
                return cur.rowcount
        except mysql.connector.Error as exc:
            try:
                self.conn.rollback()
            except Exception:
                pass
            raise GoalDatabaseError(f"GoalService DB error: {exc}") from exc

    # ------------------------------------------------------------------
    # Progress computation — queries transactions directly
    # ------------------------------------------------------------------

    def _compute_saving_progress(
        self, account_id: int, start_date: date, end_date: date
    ) -> float:
        """
        Saving goal progress = total income + transfer-in amounts
        credited to `account_id` within [start_date, end_date].
        """
        sql = """
            SELECT COALESCE(SUM(t.amount), 0) AS total
            FROM transactions t
            WHERE t.is_deleted = 0
              AND t.user_id     = %s
              AND t.transaction_date BETWEEN %s AND %s
              AND (
                    -- direct income to the account
                    (t.transaction_type = 'income'   AND t.account_id = %s)
                    OR
                    -- transfer arriving at this account
                    (t.transaction_type = 'transfer' AND t.destination_account_id = %s)
                  )
        """
        row = self._execute(
            sql,
            (self.user_id, start_date, end_date, account_id, account_id),
            fetchone=True,
        )
        return float(row["total"]) if row else 0.0
    
    def _compute_category_spending_progress(
        self, category_id: int, start_date: date, end_date: date
    ) -> float:
        """
        Spending / budget_cap progress = total expense amount
        in `category_id` (and its descendants) within [start_date, end_date].
        """
        # Collect category and all sub-categories for accurate roll-up
        try:
            subtree_ids = self._get_category_subtree(category_id)
        except Exception:
            subtree_ids = [category_id]

        placeholders = ", ".join(["%s"] * len(subtree_ids))
        sql = f"""
            SELECT COALESCE(SUM(t.amount), 0) AS total
            FROM transactions t
            WHERE t.is_deleted = 0
              AND t.user_id    = %s
              AND t.transaction_date BETWEEN %s AND %s
              AND t.transaction_type = 'expense'
              AND t.category_id IN ({placeholders})
        """
        params = (self.user_id, start_date, end_date, *subtree_ids)
        row    = self._execute(sql, params, fetchone=True)
        return float(row["total"]) if row else 0.0
    
    def _compute_account_spending_progress(
        self, account_id: int, start_date: date, end_date: date
    ) -> float:
        """
        Spending progress based on total expenses from a specific account
        within [start_date, end_date].
        """
        sql = """
            SELECT COALESCE(SUM(t.amount), 0) AS total
            FROM transactions t
            WHERE t.is_deleted = 0
            AND t.user_id = %s
            AND t.transaction_type = 'expense'
            AND t.account_id = %s
            AND t.transaction_date BETWEEN %s AND %s
        """

        params = (self.user_id, account_id, start_date, end_date)

        row = self._execute(sql, params, fetchone=True)

        return float(row["total"]) if row else 0.0
    
    def _get_category_subtree(self, root_id: int) -> List[int]:
        """
        Return `root_id` + all descendant category IDs using a recursive CTE.
        Falls back to [root_id] if CTEs are unavailable.
        """
        sql = """
            WITH RECURSIVE subtree AS (
                SELECT category_id FROM categories WHERE category_id = %s 
                    AND owner_id = %s AND is_deleted = 0
                UNION ALL
                SELECT c.category_id FROM categories c
                JOIN subtree s ON c.parent_id = s.category_id
                WHERE c.is_deleted = 0 
            )
            SELECT category_id FROM subtree
        """
        rows = self._execute(sql, (root_id, self.user_id), fetchall=True) or []
        return [r["category_id"] for r in rows] or [root_id]
    
    def _build_progress_dict(self, goal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Given a goal dict, calculate current progress and enrich the dict
        with progress metadata.

        Returns a NEW dict — does not mutate the original.
        """
        goal_type   = goal["goal_type"]
        target      = float(goal["target_amount"])
        start_date  = goal["start_date"]
        end_date    = goal["end_date"]

        # Convert ISO strings → date objects if needed
        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)

        # Cap the "as-of" date so we don't look beyond goal end
        as_of = min(date.today(), end_date)

        # ── Compute ──────────────────────────────────────────────
        if goal_type == "saving":
            account_id = goal.get("account_id")
            if not account_id:
                current = 0.0
            else:
                current = self._compute_saving_progress(account_id, start_date, as_of)

        elif goal_type in ("spending", "budget_cap"):
            category_id = goal.get("category_id")
            account_id  = goal.get("account_id")
            if not category_id and not account_id:
                current = 0.0
            elif category_id:
                current = self._compute_category_spending_progress(category_id, start_date, as_of)
            elif account_id:
                current = self._compute_account_spending_progress(account_id, start_date, as_of)

        else:
            current = 0.0

        # ── Derived metrics ───────────────────────────────────────
        pct      = round((current / target * 100), 2) if target > 0 else 0.0
        pct      = min(pct, 999.99)                   # cap display at 999.99 %
        remaining = round(target - current, 2)

        today    = date.today()
        total_days    = max((end_date - start_date).days, 1)
        elapsed_days  = max((min(today, end_date) - start_date).days, 0)
        days_left     = max((end_date - today).days, 0)
        time_pct      = round(elapsed_days / total_days * 100, 2)

        # ── Status inference ─────────────────────────────────────
        # Only auto-infer if goal is still "active"
        inferred_status = goal.get("status", "active")
        if inferred_status == "active":
            if goal_type == "saving":
                if current >= target:
                    inferred_status = "completed"
                elif today > end_date and current < target:
                    inferred_status = "failed"
            elif goal_type == "budget_cap":
                if current > target:
                    inferred_status = "failed"     # cap exceeded
            elif goal_type == "spending":
                if current >= target:
                    inferred_status = "completed"  # reached spending target
                elif today > end_date:
                    inferred_status = "failed"

        # For budget_cap: "on_track" means spending is still below cap
        if goal_type == "budget_cap":
            on_track = current <= target
        else:
            on_track = pct >= time_pct           # spending/saving keeps pace with time

        result = dict(goal)  # shallow copy
        result.update({
            "current_amount":  round(current, 2),
            "target_amount":   target,
            "remaining":       remaining,
            "progress_pct":    pct,
            "time_elapsed_pct": time_pct,
            "days_left":       days_left,
            "on_track":        on_track,
            "inferred_status": inferred_status,
        })
        return result
    
    # ============================================================
    # CRUD Pass-through (with enrichment)
    # ============================================================

    def create_goal(self, **data: Any) -> Dict[str, Any]:
        """
        Create a new goal.

        Required: name, goal_type, target_amount, start_date, end_date
        Type-specific:
          saving     → account_id
          spending   → category_id/account_id
          budget_cap → category_id/account_id

        Example:
            svc.create_goal(
                name="Emergency Fund",
                goal_type="saving",
                target_amount=50000,
                start_date="2025-01-01",
                end_date="2025-12-31",
                account_id=3,
            )
        """
        result = self.goal_model.create(**data)
        # Enrich freshly created goal with initial progress
        result["goal"] = self._build_progress_dict(result["goal"])
        return result

    def get_goal(self, goal_id: int, *, include_deleted: bool = False) -> Dict[str, Any]:
        """Fetch a single goal with live progress data."""
        goal = self.goal_model.get_goal(goal_id, include_deleted=include_deleted)
        return self._build_progress_dict(goal)
    
    def update_goal(self, goal_id: int, **updates: Any) -> Dict[str, Any]:
        """Update a goal's fields. Returns updated goal with live progress."""
        result = self.goal_model.update_goal(goal_id, **updates)
        result["goal"] = self._build_progress_dict(result["goal"])
        return result

    def delete_goal(self, goal_id: int, soft: bool = True) -> Dict[str, Any]:
        """Delete (soft by default) a goal."""
        return self.goal_model.delete_goal(goal_id, soft=soft)

    def restore_goal(self, goal_id: int) -> Dict[str, Any]:
        """Restore a soft-deleted goal."""
        return self.goal_model.restore_goal(goal_id)

    def list_goals(
        self,
        *,
        goal_type:   Optional[str] = None,
        status:      Optional[str] = None,
        category_id: Optional[int] = None,
        account_id:  Optional[int] = None,  
        include_deleted: bool = False,
        global_view:     bool = False,
        with_progress:   bool = True,
        limit:  Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        List goals with optional filters.

        Set with_progress=False for a lightweight listing without
        transaction queries (useful for admin dashboards).
        """
        result = self.goal_model.list_goals(
            goal_type=goal_type,
            status=status,
            category_id=category_id,
            account_id=account_id,
            include_deleted=include_deleted,
            global_view=global_view,
            limit=limit,
            offset=offset,
        )

        if with_progress:
            result["goals"] = [
                self._build_progress_dict(g) for g in result["goals"]
            ]

        return result
    
    # ============================================================
    # Progress & Tracking API
    # ============================================================

    def get_progress(self, goal_id: int) -> Dict[str, Any]:
        """
        Return a detailed progress snapshot for a single goal.

        Example response:
        {
            "goal_id": 1,
            "name": "Emergency Fund",
            "goal_type": "saving",
            "target_amount": 50000.0,
            "current_amount": 32500.0,
            "remaining": 17500.0,
            "progress_pct": 65.0,
            "time_elapsed_pct": 58.22,
            "days_left": 153,
            "on_track": True,
            "inferred_status": "active",
            ...
        }
        """
        goal = self.goal_model.get_goal(goal_id)
        return self._build_progress_dict(goal)

    def get_all_progress(self) -> List[Dict[str, Any]]:
        """
        Return live progress for ALL active goals of the current user,
        sorted by urgency (least days_left first).
        """
        result = self.goal_model.list_goals(status="active")
        goals  = result.get("goals", [])
        enriched = [self._build_progress_dict(g) for g in goals]
        enriched.sort(key=lambda g: g.get("days_left", 9999))
        return enriched

    def check_budget_cap(
        self,
        category_id: Optional[int] = None,
        account_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date:   Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Check if ANY active budget_cap goal for the given category has been
        exceeded.  Useful for real-time spend-blocking or UI warnings.

        If start_date / end_date are omitted, the goal's own date range is used.

        Returns:
            {
                "category_id": 5, or "account_id": 3,
                "caps": [
                    {
                        "goal_id": 12,
                        "name": "Food Budget",
                        "target_amount": 15000.0,
                        "current_amount": 17230.0,
                        "exceeded": True,
                        "overspend": 2230.0,
                        "progress_pct": 114.87,
                    },
                    ...
                ],
                "any_exceeded": True,
            }
        """
        result = self.goal_model.list_goals(
            goal_type="budget_cap",
            status="active",
            category_id=category_id if category_id else None,
            account_id=account_id if account_id else None,
        )
        caps  = []
        any_exceeded = False

        for goal in result.get("goals", []):
            s_date = start_date or goal["start_date"]
            e_date = end_date   or goal["end_date"]
            if isinstance(s_date, str):
                s_date = date.fromisoformat(s_date)
            if isinstance(e_date, str):
                e_date = date.fromisoformat(e_date)
            if category_id:
                current  = self._compute_category_spending_progress(category_id, s_date, e_date)
            elif account_id:
                current  = self._compute_account_spending_progress(account_id, s_date, e_date)
            else:
                current  = 0
            target   = float(goal["target_amount"])
            exceeded = current > target
            if exceeded:
                any_exceeded = True

            caps.append({
                "goal_id":       goal["goal_id"],
                "name":          goal["name"],
                "target_amount": target,
                "current_amount": round(current, 2),
                "exceeded":      exceeded,
                "overspend":     round(max(current - target, 0), 2),
                "progress_pct":  round(current / target * 100, 2) if target else 0,
            })

        return {
            "category_id":  category_id if category_id else None,
            "account_id":   account_id if account_id else None,
            "caps":         caps,
            "any_exceeded": any_exceeded,
        }

    # ============================================================
    # Status Management
    # ============================================================

    def auto_update_statuses(self) -> Dict[str, Any]:
        """
        Scan all active goals and automatically transition status to
        'completed' or 'failed' when conditions are met.

        Safe to call on a schedule (e.g. daily cron via Scheduler).

        Returns:
            {"updated": [{"goal_id": ..., "old_status": ..., "new_status": ...}, ...]}
        """
        result  = self.goal_model.list_goals(status="active")
        updated = []

        for goal in result.get("goals", []):
            enriched     = self._build_progress_dict(goal)
            old_status   = goal["status"]
            new_status   = enriched["inferred_status"]

            if new_status != old_status:
                self.goal_model.update_goal(goal["goal_id"], status=new_status)
                updated.append({
                    "goal_id":    goal["goal_id"],
                    "name":       goal["name"],
                    "old_status": old_status,
                    "new_status": new_status,
                })

        return {"updated": updated, "total_changed": len(updated)}

    def mark_complete(self, goal_id: int) -> Dict[str, Any]:
        """Manually mark a goal as completed."""
        return self.goal_model.update_goal(goal_id, status="completed")

    def pause_goal(self, goal_id: int) -> Dict[str, Any]:
        """Pause an active goal."""
        return self.goal_model.update_goal(goal_id, status="paused")

    def resume_goal(self, goal_id: int) -> Dict[str, Any]:
        """Resume a paused goal."""
        return self.goal_model.update_goal(goal_id, status="active")

    # ============================================================
    # Summary / Dashboard
    # ============================================================

    def get_summary(self) -> Dict[str, Any]:
        """
        High-level dashboard summary of all goals for the current user.

        Returns:
        {
            "total_goals": 8,
            "by_status": {"active": 5, "completed": 2, "failed": 1, "paused": 0},
            "by_type":   {"saving": 3, "spending": 2, "budget_cap": 3},
            "active_goals": [
                {
                    "goal_id": ...,
                    "name": ...,
                    "goal_type": ...,
                    "progress_pct": ...,
                    "days_left": ...,
                    "on_track": ...,
                },
                ...
            ],
            "caps_exceeded": [  # budget_cap goals that are over limit
                { "goal_id": ..., "name": ..., "overspend": ... },
                ...
            ],
            "generated_at": "2025-06-10T08:30:00"
        }
        """
        all_goals_result = self.goal_model.list_goals()
        all_goals        = all_goals_result.get("goals", [])

        by_status: Dict[str, int] = {
            "active": 0, "completed": 0, "failed": 0, "paused": 0
        }
        by_type: Dict[str, int] = {
            "saving": 0, "spending": 0, "budget_cap": 0
        }
        active_summary = []
        caps_exceeded  = []

        for goal in all_goals:
            status    = goal.get("status", "active")
            goal_type = goal.get("goal_type", "saving")

            by_status[status]    = by_status.get(status, 0) + 1
            by_type[goal_type]   = by_type.get(goal_type, 0) + 1

            if status == "active":
                enriched = self._build_progress_dict(goal)
                active_summary.append({
                    "goal_id":      goal["goal_id"],
                    "name":         goal["name"],
                    "goal_type":    goal_type,
                    "progress_pct": enriched["progress_pct"],
                    "days_left":    enriched["days_left"],
                    "on_track":     enriched["on_track"],
                    "current_amount": enriched["current_amount"],
                    "target_amount":  enriched["target_amount"],
                })

                if goal_type == "budget_cap":
                    target  = float(goal["target_amount"])
                    current = enriched["current_amount"]
                    if current > target:
                        caps_exceeded.append({
                            "goal_id":  goal["goal_id"],
                            "name":     goal["name"],
                            "overspend": round(current - target, 2),
                        })

        # Sort active goals: at-risk first (not on_track), then by days_left
        active_summary.sort(key=lambda g: (g["on_track"], g["days_left"]))

        return {
            "total_goals":    len(all_goals),
            "by_status":      by_status,
            "by_type":        by_type,
            "active_goals":   active_summary,
            "caps_exceeded":  caps_exceeded,
            "generated_at":   datetime.now().isoformat(),
        }

    def view_audit_logs(
        self,
        goal_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Proxy to GoalModel audit log viewer."""
        return self.goal_model.view_audit_logs(goal_id=goal_id)



