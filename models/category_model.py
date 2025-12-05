"""""
============================================================
 Assumptions
 ------------------------------------------------------------
 - MySQL 8.0+ (required for recursive CTE operations)
 - `mysql.connector` connection object is injected externally
 - Categories support soft delete (via `is_deleted` flag)
 - Tracks `owner_id` and `updated_by` referencing users table
 - Prevents duplicate names under the same parent
 - Prevents cyclic relationships when moving nodes
 - Supports recursive delete/restore for entire subtrees
 - Hard delete only allowed if leaf node or recursive=True
 - Returns dicts for easy integration with CLI/REST layer

============================================================
 Public API
 ------------------------------------------------------------
 CategoryManager.add_category(name, parent_id=None, ...)
 CategoryManager.list_categories(flat=True, include_deleted=False)
 CategoryManager.get_category(category_id, include_deleted=False)
 CategoryManager.update_category(category_id, ...)
 CategoryManager.move_category(category_id, new_parent_id)
 CategoryManager.delete_category(category_id, soft=True, recursive=False)
 CategoryManager.restore_category(category_id, recursive=False)
 CategoryManager.list_subcategories(parent_id=None, include_deleted=False)
 CategoryManager.close()

============================================================
 Notes
 ------------------------------------------------------------
 - UNIQUE (parent_id, name) enforced at DB level or checked in code
 - Recursive operations use CTEs for subtree traversal
 - Tree building for nested representation done in Python
 - Designed for integration with a shared MySQL connection pool
============================================================
"""

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional, List, Tuple
import mysql.connector
from datetime import datetime
import json

# ============================================================
# Exceptions
# ============================================================
class CategoryError(Exception):
    """Base exception for category errors."""
    pass


class NotFoundError(CategoryError):
    pass


class DuplicateNameError(CategoryError):
    pass


class ConstraintError(CategoryError):
    pass


class InvalidOperationError(CategoryError):
    pass


# ============================================================
# Data Model
# ============================================================
@dataclass
class Category:
    category_id: int
    name: str
    parent_id: Optional[int]
    is_global: bool
    owner_id: Optional[int]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_deleted: bool
    owned_by_username: Optional[str] = None
    updated_by_username: Optional[str] = None
    children: List["Category"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Recursively convert Category dataclass (and children) to dict."""
        data = asdict(self)
        if self.children:
            data["children"] = [child.to_dict() for child in self.children]
        return data


class CategoryModel:
    def __init__(self, conn: mysql.connector.MySQLConnection, current_user: Optional[Dict[str, Any]]):
        self.conn = conn
        self.current_user = current_user or {}
        self.user_id = self.current_user.get("user_id")
        self.role = self.current_user.get("role")

    # -------------------------
    # Low-Level Helpers
    # -------------------------
    def _execute(self, query: str, params: Tuple = (), fetch: bool = False) -> Any:
        """Execute a query safely with commit/rollback and error handling."""
        cursor = self.conn.cursor(dictionary=True)
        try:
            cursor.execute(query, params)
            if fetch:
                rows = cursor.fetchall()
                cursor.close()
                return rows
            self.conn.commit()
            affected = cursor.rowcount
            cursor.close()
            return affected
        except mysql.connector.Error as err:
            try:
                self.conn.rollback()
            except Exception:
                pass
            raise CategoryError(f"Database error: {err}")

    def _exists_category(self, category_id: int, include_deleted: bool = True) -> bool:
        q = "SELECT 1 FROM categories WHERE category_id = %s"
        if not include_deleted:
            q += " AND is_deleted = 0"
        q += " LIMIT 1"
        rows = self._execute(q, (category_id,), fetch=True)
        return bool(rows)
    
    def _tenant_filter(self, alias: str = "c", section: str = "own") -> str:
        """
        Generate WHERE clause enforcing tenant visibility.

        section: 
            - "own"    => admin sees only their own rows
            - "global" => admin sees only global rows
            - "user"   => regular user sees their own rows
        """
        if self.role == "admin":
            if section == "global":
                return f"{alias}.is_global = 1"
            elif section == "own":
                return f"{alias}.owner_id = %s"
            else:
                raise ValueError("Invalid section for admin filter")
        
        # Regular users always see their own rows
        return f"{alias}.owner_id = %s"

    def _log_audit(
        self,
        target_id: int,
        action: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        changed_fields: Optional[List[str]] = None,
    ):
        """Internal helper for inserting audit logs."""
        query = """
            INSERT INTO audit_log 
                (user_id, target_table, target_id, action, changed_fields, old_values, new_values,
                user_agent, is_global, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s,%s, %s, NOW())
        """
        if old_values:
            for k in ("created_at", "updated_at"):
                if k in list(old_values.keys()) and isinstance(old_values[k], datetime):
                    old_values[k] = old_values[k].isoformat()
        
        params =         (
                    self.user_id,
                    "categories",
                    target_id,
                    action,
                    json.dumps(changed_fields or []),
                    json.dumps(old_values or {}),
                    json.dumps(new_values or {}),
                    None,
                    int(self.current_user.get("is_global", 0)),
                )
        affected = self._execute(query, params)
        if not affected:
            raise InvalidOperationError("No Audit logged")
        return True



        
    def _validate_unique_name(self, name: str, parent_id: Optional[int], exclude_id: Optional[int]= None):
        """Ensure category name is unique under same parent (excluding deleted)."""
        where = "name = %s AND is_deleted = 0 AND "
        params: Tuple[Any, ...]
        if parent_id is None:
            where += "parent_id is NULL"
            params = (name,)

        else:
            where += "parent_id = %s "
            params = (name, parent_id,)

        if exclude_id:
            where += " AND category_id <> %s"
            params += (exclude_id,) 

        q = f"SELECT 1 FROM categories WHERE {where} LIMIT 1"
        rows = self._execute(q, params, fetch=True)
        if rows:
            raise DuplicateNameError(f"Category '{name}' already exists under this parent.")

    def _is_descendant(self, ancestor_id: int, possible_child_id: int) -> bool:
        """Check if `possible_child_id` is within the subtree of `ancestor_id`."""
        if ancestor_id == possible_child_id:
            return True
        q = """
            WITH RECURSIVE sub AS (
                SELECT category_id, parent_id FROM categories WHERE category_id = %s AND is_deleted = 0
                UNION ALL
                SELECT c.category_id, c.parent_id FROM categories c
                INNER JOIN sub s ON c.parent_id = s.category_id
                AND is_deleted = 0
            )
            SELECT 1 FROM sub WHERE category_id = %s LIMIT 1
            """
        params = (ancestor_id, possible_child_id,)
        rows = self._execute(q, params, fetch=True)
        return bool(rows)  

    # ============================================================
    # CRUD OPERATIONS
    # ============================================================
    def add_category(
            self, name: str, parent_id: Optional[int] = None,
            description: Optional[str] = None, is_global: bool = False
    ) -> Dict[str, Any]:
        #create New category
        name = (name or "").strip()
        if not name:
            raise CategoryError("Category name is required")
        
        if parent_id is not None and not self._exists_category(parent_id, include_deleted=False):
            raise NotFoundError(f"Parent category {parent_id} not found.")
        
        self._validate_unique_name(name, parent_id)
        owner_id = self.user_id
        print(owner_id)
        query = """
            INSERT INTO categories (name, parent_id, is_global, owner_id, updated_by,
                                     description, created_at, updated_at, is_deleted)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), 0)
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(query, (name, parent_id, int(is_global), owner_id, owner_id, description))
            self.conn.commit()
            new_id = cursor.lastrowid
            cursor.close()

            self._log_audit(
                target_id=new_id,
                action="INSERT",
                new_values={"name": name, "parent_id": parent_id, "description": description, "is_global": is_global},
            )

            return self.get_category(new_id)
        except mysql.connector.Error as err:
            self.conn.rollback()
            cursor.close()
            raise CategoryError(f"Insert failed: {err}")

    def get_category(self, category_id: int, include_deleted: bool = False, section: str = "own") -> Dict[str, Any]:
        """Fetch category by ID, applying tenant visibility (own/global/user)."""
        alias = "c"
        filter_clause = self._tenant_filter(alias, section)
        q = f"""
            SELECT c.*,
                u1.username AS owned_by_username,
                u2.username AS updated_by_username
            FROM categories c
            LEFT JOIN users u1 ON c.owner_id = u1.user_id
            LEFT JOIN users u2 ON c.updated_by = u2.user_id
            WHERE c.category_id = %s AND {filter_clause}
            """
        params = (category_id,)
        if "%s" in filter_clause:
            params += (self.user_id,)

        if not include_deleted:
            q += " AND c.is_deleted = 0"
        rows = self._execute(q, params, fetch=True)
        if not rows:
            raise NotFoundError(f"Category {category_id} not found.")
        return rows[0]
    
    def update_category(self, category_id: int, name: Optional[str] = None, description: Optional[str] = None, is_global: bool = False) -> Dict[str, Any]:
        """Rename or update description for a category."""
        cat = self.get_category(category_id)
        new_name = (name or cat["name"]).strip()
        if new_name != cat["name"]:
            self._validate_unique_name(new_name, cat["parent_id"], exclude_id=category_id)
        updated_by = self.current_user.get("user_id")
        new_desc = (description or cat["description"])

        fields = ["c.name = %s, c.description = %s, c.updated_by = %s, c.updated_at = NOW()"]
        values = [new_name, new_desc, updated_by]

        alias = "c"
        filter_clause = self._tenant_filter(alias, "own" if self.role == "admin" else "user")


        if is_global is not None:
            fields.append("c.is_global = %s")
            values.append(is_global)

        q = f"""
            UPDATE categories c
            SET {", ".join(fields)}
            WHERE c.category_id = %s AND {filter_clause}
        """
        values.append(category_id)
        values.append(self.user_id)
       
        affected = self._execute(q, tuple(values))

        if affected == 0:
            raise CategoryError("Update failed: no rows affected.")
        #log update to audit table
    
        self._log_audit(
            target_id=category_id,
            action="UPDATE",
            old_values=cat,
            new_values={"name": new_name, "description": new_desc, "is_global": is_global},
            changed_fields=["name", "description", "is_global"],
        )

        return self.get_category(category_id,)
        
    def move_category(self, category_id: int, new_parent_id: Optional[int]) -> Dict[str, Any]:
        """Move a category to a different parent or to root."""
        if category_id == new_parent_id:
            raise InvalidOperationError("Cannot move category under itself.")

        if not self._exists_category(category_id, include_deleted=False):
            raise NotFoundError("Category not found.")
        
        if new_parent_id:
            if not self._exists_category(new_parent_id, include_deleted=False):
                raise NotFoundError("New parent not found.")
            if self._is_descendant(new_parent_id, category_id):
                raise InvalidOperationError("Cannot move under descendant (cycle).")
        cat =self.get_category(category_id)
        
        alias = "c"
        section = str("own" if self.role == "admin" else "user")
        filter_clause = self._tenant_filter(alias, section)
            
        updated_by = self.current_user.get("user_id")
        q = f"UPDATE categories c SET c.parent_id = %s, c.updated_by = %s, c.updated_at = NOW() WHERE c.category_id = %s AND {filter_clause}"
        params = (new_parent_id, updated_by, category_id, self.user_id,)
    
        self._execute(q, params)

        self._log_audit(
                target_id=category_id,
                action="UPDATE",
                old_values={"old_parent_id": cat.get("parent_id")},
                new_values={"parent_id": new_parent_id},
                changed_fields=["parent_id"],
            )

        return self.get_category(category_id, section=section)

    def view_audit_logs(
        self,
        target_table: str = "categories",
        target_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        section: str = "own"
    ) -> List[Dict[str, Any]]:

        alias = "a"   # audit_log alias
        
        # ------------------------------------
        # Tenant Filter
        # ------------------------------------
        # Admin:
        #    section="global" => show only global logs
        #    section="own"    => show only their own logs
        #
        # Users:
        #    always show only their own logs
        # ------------------------------------
        filter_clause = self._tenant_filter(alias, section)

        # ------------------------------------
        # Base Query
        # ------------------------------------
        q = f"""
            SELECT 
                a.*,
                u.username AS performed_by
            FROM audit_log a
            LEFT JOIN users u ON a.user_id = u.user_id
            WHERE a.target_table = %s 
            AND {filter_clause}
        """

        params = [target_table]

        # Bind user_id if needed
        if "%s" in filter_clause:
            params.append(self.user_id)

        # ------------------------------------
        # Optional filtering
        # ------------------------------------
        if target_id:
            q += " AND a.target_id = %s"
            params.append(target_id)

        if start_date:
            q += " AND a.timestamp >= %s"
            params.append(start_date)

        if end_date:
            q += " AND a.timestamp <= %s"
            params.append(end_date)

        # Final ordering
        q += " ORDER BY a.timestamp DESC"

        return self._execute(q, tuple(params), fetch=True)


    def delete_category(self, category_id: int, soft: bool = True, recursive: bool = False) -> int:
        """Soft or hard delete a category (optionally recursive) with tenant restrictions."""
        # Enforce ownership
        alias = "c"
        tenant_clause = self._tenant_filter(alias, "own" if self.role == "admin" else "user")

        base = self.get_category(category_id, include_deleted=True)
        self._log_audit(
                target_id=category_id,
                action="DELETE",
                old_values=base,
            )

        if not base:
            raise NotFoundError("Category not found or not accessible to this user.")

        # Check if category has children when not recursive
        if not recursive:
            has_children = self._execute(
                "SELECT 1 FROM categories WHERE parent_id = %s AND is_deleted = 0 LIMIT 1",
                (category_id,),
                fetch=True,
            )
            if has_children:
                raise ConstraintError("Cannot delete category with children unless recursive=True.")

        user_id = self.user_id

        if soft:
            # 🔹 Soft delete
            if recursive:
                q = f"""
                    WITH RECURSIVE subtree AS (
                        SELECT c.category_id FROM categories c WHERE c.category_id = %s AND {tenant_clause}
                        UNION ALL
                        SELECT c2.category_id
                        FROM categories c2
                        INNER JOIN subtree s ON c2.parent_id = s.category_id
                    )
                    UPDATE categories
                    SET is_deleted = 1, updated_at = NOW(), updated_by = %s
                    WHERE category_id IN (SELECT category_id FROM subtree)
                """
                params = (category_id, user_id, user_id)
            else:
                q = f"""
                    UPDATE categories c
                    SET c.is_deleted = 1, c.updated_at = NOW(), c.updated_by = %s
                    WHERE c.category_id = %s AND {tenant_clause}
                """
                params = (user_id, category_id, user_id)

        else:
            # 🔹 Hard delete
            if recursive:
                q = f"""
                    WITH RECURSIVE subtree AS (
                        SELECT c.category_id FROM categories c WHERE c.category_id = %s AND {tenant_clause}
                        UNION ALL
                        SELECT c2.category_id
                        FROM categories c2
                        INNER JOIN subtree s ON c2.parent_id = s.category_id
                    )
                    DELETE FROM categories
                    WHERE category_id IN (SELECT category_id FROM subtree)
                """
                params = (category_id, user_id)
            else:
                # Must ensure it's a leaf
                count = self._execute(
                    "SELECT COUNT(*) AS cnt FROM categories WHERE parent_id = %s AND is_deleted = 0",
                    (category_id,),
                    fetch=True,
                )
                if count and count[0]["cnt"] > 0:
                    raise ConstraintError("Cannot hard-delete category with children unless recursive=True.")
                q = f"DELETE FROM categories c WHERE c.category_id = %s AND {tenant_clause}"
                params = (category_id, user_id)

        return self._execute(q, params)
    
    def restore_category(self, category_id: int, recursive: bool = False) -> int:
        """Restore soft-deleted category (optionally recursive) with tenant restrictions."""
        alias = "c"
        tenant_clause = self._tenant_filter(alias, "own" if self.role == "admin" else "user")

        cat = self.get_category(category_id, include_deleted=True)
        if not cat:
            raise NotFoundError("Category not found or not accessible to this user.")
        if not cat["is_deleted"]:
            return 0

        user_id = self.user_id
        self._log_audit(
                target_id=category_id,
                action="UPDATE",
                old_values={"is_deleted": True},
                new_values={"is_deleted": False},
                changed_fields=["is_deleted"],
            )


        if recursive:
            q = f"""
                WITH RECURSIVE subtree AS (
                    SELECT c.category_id FROM categories c WHERE c.category_id = %s AND {tenant_clause}
                    UNION ALL
                    SELECT c2.category_id
                    FROM categories c2
                    INNER JOIN subtree s ON c2.parent_id = s.category_id
                )
                UPDATE categories
                SET is_deleted = 0, updated_at = NOW(), updated_by = %s
                WHERE category_id IN (SELECT category_id FROM subtree)
            """
            params = (category_id, user_id, user_id)
        else:
            q = f"""
                UPDATE categories c
                SET c.is_deleted = 0, c.updated_at = NOW(), c.updated_by = %s
                WHERE c.category_id = %s AND {tenant_clause}
            """
            params = (user_id, category_id, user_id)

        return self._execute(q, params)


    
    # ============================================================
    # Listing / Utilities
    # ============================================================
    def list_categories(self, flat: bool = True, include_deleted: bool = False, section: str = "own") -> List[Dict[str, Any]]:
        """Return all categories (flat or hierarchical tree)."""
        alias = "c"
        filter_clause = self._tenant_filter(alias, section)
        deleted = "" if include_deleted else "AND c.is_deleted = 0"

        q= f"""
            SELECT c.*, u1.username AS owned_by_username, u2.username AS updated_by_username
            FROM categories c
            LEFT JOIN users u1 ON c.owner_id = u1.user_id
            LEFT JOIN users u2 ON c.updated_by = u2.user_id
            WHERE {filter_clause} {deleted}
            ORDER BY COALESCE(c.parent_id, 0), c.name
        """
        params = (self.user_id,) if "%s" in filter_clause else ()

        rows = self._execute(q, params, fetch=True)

        if flat:
            return rows

        # ============================================================
        # Hybrid One-Pass Tree Builder (order-independent, O(n))
        # ============================================================
        lookup: Dict[int, Dict[str, Any]] = {}
        roots: List[Dict[str, Any]] = []

        for r in rows:
            r["children"] = lookup.get(r["category_id"], {}).get("children", [])
            lookup[r["category_id"]] = r

            pid = r["parent_id"]
            if pid:
                parent = lookup.get(pid)
                if parent:
                    # Parent already exists — attach directly
                    parent.setdefault("children", []).append(r)
                else:
                    # Parent not yet seen — create a placeholder
                    lookup[pid] = {"children": [r]}
            else:
                roots.append(r)

        return roots

    def list_subcategories(self, parent_id: Optional[int] = None, include_deleted: bool = False, section : Optional[str] = "own") -> List[Dict[str, Any]]:
        """List immediate child categories under a given parent."""
        params: Tuple[Any, ...]
        alias = "c"
        filter_clause = self._tenant_filter(alias, section)
        deleted = "" if include_deleted else "AND c.is_deleted = 0"
        params = []

        # Build query (with JOINs ALWAYS)
        base_query = """
            SELECT c.*, u1.username AS owned_by_username, u2.username AS updated_by_username
            FROM categories c
            LEFT JOIN users u1 ON c.owner_id = u1.user_id
            LEFT JOIN users u2 ON c.updated_by = u2.user_id
        """

        if parent_id is None:
            q = (
                base_query +
                f"WHERE c.parent_id IS NULL AND {filter_clause} {deleted}"
            )
            if "%s" in filter_clause:
                params.append(self.user_id)
        else:
            q = (
                base_query +
                f"WHERE c.parent_id = %s AND {filter_clause} {deleted}"
            )
            params.append(parent_id)

            if "%s" in filter_clause:  # CORRECT FIX
                params.append(self.user_id)

        q += " ORDER BY c.name"

        return self._execute(q, tuple(params), fetch=True)

    # -------------------------
    # Cleanup
    # -------------------------
    def close(self):
        """Gracefully close the database connection."""
        try:
            self.conn.close()
        except Exception:
            pass