#CRUD for user goals
# models/goal_model.py
"""
============================================================
 GoalModel — CRUD for Financial Goals
 ------------------------------------------------------------
 Supports three goal types:
   - saving    : Track deposits/income toward a target amount
   - spending  : Cap or track spending over a period
   - budget_cap: Hard cap on category spending per period

 Architecture mirrors AccountModel / RecurringModel patterns:
   - owner_id-based tenant isolation
   - Soft deletes (is_deleted)
   - audit_log integration
   - Dataclass ↔ dict round-trips

 Public API
 ------------------------------------------------------------
 GoalModel.create(**data)                → Dict
 GoalModel.get_goal(goal_id)             → Dict
 GoalModel.update_goal(goal_id, **data)  → Dict
 GoalModel.delete_goal(goal_id, soft)    → Dict
 GoalModel.restore_goal(goal_id)         → Dict
 GoalModel.list_goals(...)               → Dict
 GoalModel.view_audit_logs(goal_id)      → List[Dict]

 SQL Migration (run once against your DB):
 ------------------------------------------------------------
 See bottom of this file — search "# === MIGRATION SQL ==="
============================================================
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from models.account_model import AccountModel
from models.category_model import CategoryModel
from core.utils import DatabaseError, ValidationError, NotFoundError, error_logger
import json
import mysql.connector


# ============================================================
# Exceptions
# ============================================================

class GoalError(Exception):
    """Base exception for goal errors."""


class GoalNotFoundError(NotFoundError):
    """Raised when a goal cannot be located."""


class GoalValidationError(ValidationError):
    """Raised when invalid goal data is supplied."""


class GoalDatabaseError(DatabaseError):
    """Raised on raw DB / MySQL failures."""


# ============================================================
# Dataclass
# ============================================================

@dataclass
class Goal:
    goal_id:        int
    owner_id:       int
    name:           str
    goal_type:      str                     # 'saving' | 'spending' | 'budget_cap'
    target_amount:  float
    start_date:     date
    end_date:       date
    description:    Optional[str]   = None
    category_id:    Optional[int]   = None  # budget_cap / spending goals
    account_id:     Optional[int]   = None  # saving goals
    status:         str             = "active"   # active | completed | failed | paused
    is_global:      int             = 0
    is_deleted:     int             = 0
    created_at:     Optional[datetime] = None
    updated_at:     Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for k in ("start_date", "end_date", "created_at", "updated_at"):
            if data[k] and hasattr(data[k], "isoformat"):
                data[k] = data[k].isoformat()
        return data


# ============================================================
# Model
# ============================================================

class GoalModel:
    """
    Handles all CRUD operations for the `goals` table.

    Mirrors the AccountModel / RecurringModel style:
      - Injected DB connection + current_user dict
      - _execute / _tenant_filter / _audit_log helpers
      - Full soft-delete support
    """

    # Valid domain values — validated on create / update
    VALID_TYPES    = {"saving", "spending", "budget_cap"}
    VALID_STATUSES = {"active", "completed", "failed", "paused"}

    def __init__(self, conn: mysql.connector.MySQLConnection,
                 current_user: Dict[str, Any]) -> None:
        self.conn = conn
        self.user = current_user          # {"user_id": ..., "role": ...}
        self.account_model = AccountModel(conn, current_user)  # For cross-checks
        self.category_model = CategoryModel(conn, current_user)  # For cross-checks
    # ============================================================
    # Internal Helpers
    # ============================================================

    def _execute(
        self,
        sql: str,
        params: Tuple[Any, ...] = (),
        *,
        fetchone: bool = False,
        fetchall: bool = False,
    ):
        """Unified SQL executor with rollback-on-error."""
        if fetchone and fetchall:
            raise GoalDatabaseError("fetchone and fetchall cannot both be True")

        try:
            with self.conn.cursor(dictionary=True) as cur:
                cur.execute(sql, params)

                if fetchone:
                    result = cur.fetchone()
                    self.conn.commit()
                    return result

                if fetchall:
                    result = cur.fetchall()
                    self.conn.commit()
                    return result

                self.conn.commit()
                sql_upper = sql.strip().upper()
                if sql_upper.startswith(("UPDATE", "DELETE")):
                    return cur.rowcount
                return cur.lastrowid

        except mysql.connector.Error as exc:
            try:
                self.conn.rollback()
            except Exception:
                pass
            error_logger.log_error(
                exc,
                location="GoalModel._execute",
                user_id=self.user.get("user_id"),
            )
            raise GoalDatabaseError(f"MySQL Error: {exc}") from exc

    def _tenant_filter(self, global_view: bool = False) -> str:
        """
        Row-level security clause.
        Admin  + global_view=True  → is_global = 1
        Admin  + global_view=False → owner_id = %s  (own records)
        User   + any               → owner_id = %s
        """
        role = self.user.get("role")
        if role == "admin":
            return "is_global = 1" if global_view else "owner_id = %s"
        if global_view:
            raise GoalValidationError("Users can only view their own goals.")
        return "owner_id = %s"

    def _audit_log(self, goal_id: int, action: str,
                   old_values: Optional[Dict] = None,
                   new_values: Optional[Dict] = None) -> None:
        """Write a row to the shared audit_log table."""
        sql = """
            INSERT INTO audit_log
                (user_id, target_table, target_id, action, old_values, new_values, timestamp)
            VALUES (%s, 'goals', %s, %s, %s, %s, NOW())
        """

        def _serial(d: Optional[Dict]) -> Optional[str]:
            if not d:
                return None
            out = {}
            for k, v in d.items():
                out[k] = v.isoformat() if hasattr(v, "isoformat") else v
            return json.dumps(out, default=str)

        params = (
            self.user["user_id"],
            goal_id,
            action,
            _serial(old_values),
            _serial(new_values),
        )
        try:
            self._execute(sql, params)
        except GoalDatabaseError:
            # Never let audit logging break the main flow
            pass

    def _build_goal(self, row: Dict[str, Any]) -> Goal:
        """Construct a Goal dataclass from a DB row dict."""
        fields = Goal.__dataclass_fields__.keys()
        clean  = {k: v for k, v in row.items() if k in fields}
        return Goal(**clean)

    # ============================================================
    # Validation
    # ============================================================

    def _validate_goal_data(self, data: Dict[str, Any], *, require_all: bool = True) -> None:
        """
        Validate a data payload for create (require_all=True) or update (require_all=False).
        Raises GoalValidationError on any failure.
        """
        required = {"name", "goal_type", "target_amount", "start_date", "end_date"}
        if require_all:
            missing = [f for f in required if f not in data]
            if missing:
                raise GoalValidationError(f"Missing required fields: {missing}")

        if "goal_type" in data:
            if data["goal_type"] not in self.VALID_TYPES:
                raise GoalValidationError(
                    f"Invalid goal_type '{data['goal_type']}'. "
                    f"Must be one of: {self.VALID_TYPES}"
                )

        if "status" in data and data["status"] not in self.VALID_STATUSES:
            raise GoalValidationError(
                f"Invalid status '{data['status']}'. "
                f"Must be one of: {self.VALID_STATUSES}"
            )

        if "target_amount" in data:
            try:
                amt = float(data["target_amount"])
                if amt <= 0:
                    raise GoalValidationError("target_amount must be greater than 0.")
            except (TypeError, ValueError):
                raise GoalValidationError("target_amount must be a positive number.")

        # Date coherence
        start = data.get("start_date")
        end   = data.get("end_date")
        if start and end:
            if isinstance(start, str):
                start = date.fromisoformat(start)
            if isinstance(end, str):
                end = date.fromisoformat(end)
            if end <= start:
                raise GoalValidationError("end_date must be after start_date.")

        # Type-specific constraints
        goal_type = data.get("goal_type")
        if goal_type == "saving" and require_all and not data.get("account_id"):
            raise GoalValidationError("saving goals require an account_id.")
        if goal_type in ("spending", "budget_cap") and require_all and not data.get("category_id"):
            raise GoalValidationError(
                f"{goal_type} goals require a category_id."
            )
        
    def _assert_ownership(self, account_id: int, category_id: int) -> None:
        """Helper to check if the user owns the referenced account/category."""
        if account_id is not None:
            self.account_model.get_account(account_id)  # Will raise if not found or not owned
        if category_id is not None:
            self.category_model.assert_category_access(category_id)
    # ============================================================
    # CRUD Operations
    # ============================================================

    def create(self, **data: Any) -> Dict[str, Any]:
        """
        Create a new goal.

        Required fields: name, goal_type, target_amount, start_date, end_date
        Optional fields: description, category_id, account_id, status, is_global

        Returns: {"success": True, "goal_id": <int>}
        """
        self._validate_goal_data(data, require_all=True)
        self._assert_ownership(data.get("account_id"), data.get("category_id"))
        sql = """
            INSERT INTO goals
                (owner_id, name, description, goal_type, target_amount,
                 start_date, end_date, category_id, account_id,
                 status, is_global)
            SELECT
                %s AS owner_id, %s AS name, %s AS description, %s AS goal_type, %s AS target_amount,
                %s AS start_date, %s AS end_date, 
                c.category_id, a.account_id,
                %s AS status, %s AS is_global
            FROM (SELECT 1) AS dummy
            LEFT JOIN categories c 
                ON c.category_id = %s 
                AND c.owner_id = %s 
                AND c.is_deleted = 0
            LEFT JOIN accounts a 
                ON a.account_id = %s 
                AND a.owner_id = %s 
                AND a.is_deleted = 0
            WHERE (%s IS NULL OR c.category_id IS NOT NULL)
                AND (%s IS NULL OR a.account_id IS NOT NULL)
            LIMIT 1
        """
        params = (
                # SELECT values
                self.user["user_id"],
                data["name"],
                data.get("description"),
                data["goal_type"],
                float(data["target_amount"]),
                data["start_date"],
                data["end_date"],
                data.get("status", "active"),
                data.get("is_global", 0),

                # category validation
                data.get("category_id"),
                self.user["user_id"],

                # account validation
                data.get("account_id"),
                self.user["user_id"],

                # WHERE checks
                data.get("category_id"),
                data.get("account_id"),
            )

        goal_id = self._execute(sql, params)
        new_record = self.get_goal(goal_id)
        self._audit_log(goal_id, "GOAL_CREATED", new_values=new_record)
        return {"success": True, "goal_id": goal_id, "goal": new_record}

    def get_goal(
        self,
        goal_id: int,
        *,
        include_deleted: bool = False,
        global_view: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch a single goal by ID.
        Raises GoalNotFoundError if not accessible.
        """
        filter_tenant = self._tenant_filter(global_view)
        sql = f"""
            SELECT g.*, u.username AS owner_username, c.name AS category_name, a.name AS account_name
            FROM goals g
            LEFT JOIN users u ON g.owner_id = u.user_id
            LEFT JOIN categories c ON g.category_id = c.category_id
            LEFT JOIN accounts a ON g.account_id = a.account_id
            WHERE g.goal_id = %s AND g.{filter_tenant}
        """
        params: List[Any] = [goal_id]
        if "%s" in filter_tenant:
            params.append(self.user["user_id"])

        if not include_deleted:
            sql += " AND g.is_deleted = 0"

        row = self._execute(sql, tuple(params), fetchone=True)
        if not row:
            raise GoalNotFoundError(f"Goal {goal_id} not found.")

        goal_dict  = self._build_goal(row).to_dict()
        goal_dict["owner_username"] = row.get("owner_username")
        goal_dict["category_name"]  = row.get("category_name")
        goal_dict["account_name"]   = row.get("account_name")   
        return goal_dict

    def update_goal(self, goal_id: int, **updates: Any) -> Dict[str, Any]:
        """
        Update allowed fields on an existing goal.

        Updatable fields:
          name, description, target_amount, start_date, end_date,
          category_id, account_id, status, is_global
        """
        if not updates:
            raise GoalValidationError("No fields provided for update.")

        ALLOWED = {
            "name", "description", "target_amount",
            "start_date", "end_date", "category_id",
            "account_id", "status", "is_global",
        }
        invalid = set(updates) - ALLOWED
        if invalid:
            raise GoalValidationError(f"Cannot update fields: {invalid}")
        #merge old record with updates for validation
        old_record = self.get_goal(goal_id)
        merged = old_record.copy()
        merged.update(updates)

        # Partial validation
        self._validate_goal_data(merged, require_all=False)
        self._assert_ownership(merged.get("account_id"), merged.get("category_id"))

 
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        params     = tuple(updates.values()) + (goal_id, self.user["user_id"])
        affected   = self._execute(
            f"UPDATE goals SET {set_clause} WHERE goal_id = %s AND owner_id = %s AND is_deleted = 0",
            params,
        )

        if affected == 0:
            raise GoalNotFoundError(f"Goal {goal_id} not found or no changes made.")

        new_record = self.get_goal(goal_id)
        self._audit_log(goal_id, "GOAL_UPDATED",
                        old_values=old_record, new_values=new_record)
        return {"success": True, "message": "Goal updated.", "goal": new_record}

    def delete_goal(self, goal_id: int, soft: bool = True) -> Dict[str, Any]:
        """
        Delete a goal.
          soft=True  → marks is_deleted = 1 (default, recoverable)
          soft=False → permanent hard delete
        """
        old_record = self.get_goal(goal_id, include_deleted=True)
        self._audit_log(goal_id, "GOAL_DELETED", old_values=old_record)

        user_id = self.user["user_id"]
        if soft:
            self._execute(
                "UPDATE goals SET is_deleted = 1 WHERE goal_id = %s AND owner_id = %s",
                (goal_id, user_id),
            )
        else:
            self._execute(
                "DELETE FROM goals WHERE goal_id = %s AND owner_id = %s",
                (goal_id, user_id),
            )

        return {
            "success": True,
            "message": f"Goal {goal_id} {'soft-' if soft else 'hard '}deleted.",
        }

    def restore_goal(self, goal_id: int) -> Dict[str, Any]:
        """Restore a previously soft-deleted goal."""
        record = self.get_goal(goal_id, include_deleted=True)
        if not record.get("is_deleted"):
            raise GoalValidationError(f"Goal {goal_id} is not deleted.")

        self._execute(
            "UPDATE goals SET is_deleted = 0 WHERE goal_id = %s AND owner_id = %s",
            (goal_id, self.user["user_id"]),
        )
        self._audit_log(goal_id, "GOAL_RESTORED",
                        old_values={"is_deleted": 1},
                        new_values={"is_deleted": 0})
        return {"success": True, "message": f"Goal {goal_id} restored."}

    def list_goals(
        self,
        *,
        goal_type: Optional[str]   = None,
        status:    Optional[str]   = None,
        category_id: Optional[int] = None,
        account_id:  Optional[int] = None,
        include_deleted: bool      = False,
        global_view:     bool      = False,
        limit:  Optional[int]      = None,
        offset: Optional[int]      = None,
    ) -> Dict[str, Any]:
        """
        List goals with optional filtering.

        Filters: goal_type, status, category_id, account_id
        Pagination: limit, offset
        """
        filter_tenant = self._tenant_filter(global_view)
        sql = f"""
            SELECT g.*, u.username AS owner_username, c.name AS category_name, a.name AS account_name
            FROM goals g
            LEFT JOIN users u ON g.owner_id = u.user_id
            LEFT JOIN categories c ON g.category_id = c.category_id
            LEFT JOIN accounts a ON g.account_id = a.account_id
            WHERE g.{filter_tenant}
        """
        params: List[Any] = []
        if "%s" in filter_tenant:
            params.append(self.user["user_id"])

        if not include_deleted:
            sql += " AND g.is_deleted = 0"

        if goal_type:
            if goal_type not in self.VALID_TYPES:
                raise GoalValidationError(f"Unknown goal_type: {goal_type}")
            sql += " AND g.goal_type = %s"
            params.append(goal_type)

        if status:
            if status not in self.VALID_STATUSES:
                raise GoalValidationError(f"Unknown status: {status}")
            sql += " AND g.status = %s"
            params.append(status)

        if category_id is not None:
            sql += " AND g.category_id = %s"
            params.append(category_id)

        if account_id is not None:
            sql += " AND g.account_id = %s"
            params.append(account_id)

        sql += " ORDER BY g.end_date ASC, g.created_at DESC"

        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        if offset is not None:
            sql += " OFFSET %s"
            params.append(offset)

        rows = self._execute(sql, tuple(params), fetchall=True)
        results = []
        for row in rows:
            gd = self._build_goal(row).to_dict()
            gd["owner_username"] = row.get("owner_username")
            gd["category_name"] = row.get("category_name")
            gd["account_name"] = row.get("account_name")
            results.append(gd)

        return {"success": True, "count": len(results), "goals": results}

    def view_audit_logs(
        self,
        goal_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve audit entries for goals from the shared audit_log table."""
        sql = f"""
            SELECT a.*, u.username AS performed_by
            FROM audit_log a
            LEFT JOIN users u ON a.user_id = u.user_id
            WHERE a.target_table = 'goals'
              AND a.user_id = %s
        """
        params: List[Any] = []
        params.append(self.user["user_id"])

        if goal_id is not None:
            sql += " AND a.target_id = %s"
            params.append(goal_id)

        sql += " ORDER BY a.timestamp DESC"
        return self._execute(sql, tuple(params), fetchall=True) or []
