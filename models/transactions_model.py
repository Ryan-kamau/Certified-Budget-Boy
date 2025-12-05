#CRUD logic for transactions
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any, Tuple
from datetime import date, datetime
import mysql.connector
import json

# ==========================
# Custom Exceptions
# ==========================

class TransactionError(Exception):
    """Base class for transaction-related exceptions."""


class TransactionNotFoundError(TransactionError):
    """Raised when a transaction is not found."""


class TransactionValidationError(TransactionError):
    """Raised when invalid transaction data is provided."""


class DatabaseError(TransactionError):
    """Raised when a database-level error occurs."""


# ==========================
# Dataclass: Transaction
# ==========================

@dataclass
class Transaction:
    transaction_id: Optional[int]
    user_id: int
    category_id: Optional[int]
    parent_transaction_id: Optional[int]
    title: str
    description: Optional[str]
    amount: float
    transaction_type: str
    payment_method: str
    transaction_date: date
    is_global: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: int = 0
    children: List["Transaction"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Recursively convert Transaction dataclass (and its children) into dict form."""
        data = asdict(self)
        data["children"] = [child.to_dict() for child in self.children]
        return data
    
# ==========================
# Model: TransactionModel
# ==========================

class TransactionModel:
    """Encapsulates CRUD operations and helpers for the transactions table."""

    def __init__(self, connection: mysql.connector.MySQLConnection, current_user: Optional[Dict[str, Any]] = None):
        self.conn = connection
        self.current_user = current_user or {}
        self.user_id = self.current_user.get("user_id")
        self.role = self.current_user.get("role")

    # ------------
    # Internal Helpers
    # ------------

    def _execute(self, query: str, params: Tuple = (), fetch: bool = False, many: bool = False):
        """Internal DB executor with error handling."""
        try:
            with self.conn.cursor(dictionary=True) as cursor:
                if many:
                    cursor.executemany(query, params)
                else:
                    cursor.execute(query, params)
                if fetch:
                    rows = cursor.fetchall()
                    cursor.close()
                    return rows
                else:
                    self.conn.commit()
                    if query.strip().upper().startswith("UPDATE"):
                        affected = cursor.rowcount
                        return affected
                    affected = cursor.lastrowid
                    return affected
        except mysql.connector.Error as err:
            try:
                self.conn.rollback()
            except Exception:
                pass
            raise DatabaseError(f"Database error: {err}")
        
    # Tenant Filter & Audit Logging

    def _tenant_filter(self, alias: str = "t", global_view: bool = False) -> str:
        """
        Generate WHERE clause enforcing tenant visibility.

        global_view:
            - False    => admin sees only their own rows and regular user sees their own rows
            - True => admin sees only global rows
        """
        if self.role == "admin":
            if global_view:
                return f"{alias}.is_global = 1"
            else:
                return f"{alias}.user_id = %s"
        if not global_view:
            return f"{alias}.user_id = %s"
        else:
            raise ValueError("Invalid global view for user")

    def _audit_log(self,
        target_id: int,
        action: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        changed_fields: Optional[List[str]] = None,
    ):
        """Internal helper for inserting audit logs"""
        query = """
                INSERT INTO audit_log
                    (user_id, target_table, target_id, action, changed_fields, old_values, new_values,
                    user_agent, is_global, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s,%s, %s, NOW())
            """
        if old_values:
            for k in ("transaction_date","created_at","updated_at"):
                if k in old_values and isinstance(old_values[k], (date, datetime)):
                    old_values[k] = old_values[k].isoformat()

        if new_values:
            for k in ("transaction_date","created_at","updated_at"):
                if k in new_values and new_values[k]:
                    new_values[k] = new_values[k].isoformat()

            
        params =         (
                    self.user_id,
                    "transactions",
                    target_id,
                    action,
                    json.dumps(changed_fields or [], default=str),
                    json.dumps(old_values or {}, default=str),
                    json.dumps(new_values or {}, default=str),
                    None,
                    int(self.current_user.get("is_global", 0)),
                )
        affected = self._execute(query, params)
        if not affected:
            raise TransactionValidationError("No Audit logged")
        return True
    
    def _build_transaction(self, row: Dict[str, Any]) -> Transaction:
        """Convert a DB row to a Transaction dataclass."""
        return Transaction(
            transaction_id=row.get("transaction_id"),
            user_id=row["user_id"],
            category_id=row.get("category_id"),
            parent_transaction_id=row.get("parent_transaction_id"),
            title=row["title"],
            description=row.get("description"),
            amount=float(row["amount"]),
            transaction_type=row["transaction_type"],
            payment_method=row["payment_method"],
            transaction_date=row["transaction_date"],
            is_global=row.get("is_global"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            is_deleted=row.get("is_deleted", 0),
        )
    
    def _get_children_recursive(self, parent_id: int, *, include_deleted: bool = False, global_view: bool = False) -> List[Transaction]:
        """Fetch child transactions recursively for a given parent."""
        filter_tenant = self._tenant_filter("t", global_view=global_view)

        query = f"SELECT * FROM transactions t WHERE t.parent_transaction_id = %s AND {filter_tenant}"
        if not include_deleted:
            query += " AND t.is_deleted = 0"
        params = (parent_id,)
        if "%s" in filter_tenant:
            params += self.user_id
        rows = self._execute(query, params, fetch=True)

        children = []
        for row in rows:
            child = self._build_transaction(row)
            child.children = self._get_children_recursive(child.category_id, include_deleted)
            children.append(child)
        return children
    
    # ------------
    # Public CRUD API
    # ------------
    def create_transaction(self, **tx_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new transaction record."""
        required = ["title", "amount", "transaction_type", "transaction_date"]
        missing = [f for f in required if f not in tx_data]
        if missing:
            raise TransactionValidationError(f"Missing required fields: {missing}")
        
        current_user_id = self.user_id
        query = """
            INSERT INTO transactions 
            (user_id, category_id, parent_transaction_id, title, description, amount, 
             transaction_type, payment_method, transaction_date, is_global)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            current_user_id,
            tx_data.get("category_id"),
            tx_data.get("parent_transaction_id"),
            tx_data["title"],
            tx_data.get("description"),
            tx_data["amount"],
            tx_data["transaction_type"],
            tx_data.get("payment_method", "mobile_money"),
            tx_data["transaction_date"],
            tx_data.get("is_global", 0),
        )

        new_id = self._execute(query, params)
        self._audit_log(new_id, action="INSERT",
                        new_values={"name": tx_data["title"], "amount": tx_data["amount"], "trans_type": tx_data["transaction_type"],
                                    "transaction_date": tx_data["transaction_date"]}
                        )
        return self.get_transaction(new_id)
    
    def get_transaction(self, transaction_id: int, include_children: bool = False, *, include_deleted: bool = False, global_view: bool = False) -> Dict[str, Any]:
        """Fetch a transaction (optionally including nested children)."""
        filter_tenant = self._tenant_filter("t", global_view=global_view)
        query = f"""
                SELECT t.*, c.name AS category_name, c.description AS category_description, u.username AS owned_by_username
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.category_id
                LEFT JOIN users u ON t.user_id = u.user_id
                WHERE t.transaction_id = %s AND {filter_tenant}
                """
        if not include_deleted:
            query += " AND t.is_deleted = 0"
        params = (transaction_id,)
        if "%s" in filter_tenant:
            params += (self.user_id,)

        
        rows = self._execute(query, params, fetch=True)
        if not rows:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found.")

        tx = self._build_transaction(rows[0])
        if include_children:
            tx.children = self._get_children_recursive(tx.transaction_id, include_deleted)

        result = tx.to_dict()
        result["category_name"] = rows[0].get("category_name")
        result["category_description"] = rows[0].get("category_description")
        result["owned_by_username"] = rows[0].get("owned_by_username")
        return result
    
    def update_transaction(self, transaction_id: int, **updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update transaction fields."""
        if not updates:
            raise TransactionValidationError("No fields provided for update.")
        
        trans = self.get_transaction(transaction_id)
        
        fields = ", ".join((f"{k}=%s" for k in updates.keys()))
        params = tuple(updates.values()) + (transaction_id, self.user_id,)
        
        result = self._execute(
            f"UPDATE transactions SET {fields} WHERE transaction_id = %s AND user_id = %s", params
        )
        print(result)
        if result == 0:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found or unchanged.")
        
        self._audit_log(transaction_id, action= "UPDATE", old_values=trans, new_values= updates, changed_fields= list[updates.keys()])
        updated = self.get_transaction(transaction_id)
        return {"success": True, "message": "Transaction updated successfully.", "update": updated}
    
    def list_transactions(
        self,
        transaction_type: Optional[str] = None,
        payment_method: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        category_id: Optional[int] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None, *,
        include_deleted: bool = False,
        global_view: bool = False
    ) -> Dict[str, Any]:
        """Filter transactions by user/date/category with optional pagination."""
        filter_tenant = self._tenant_filter("t", global_view=global_view)
        query = f"""
                SELECT t.*, c.name AS category_name, c.description AS category_description, u.username AS owned_by_username
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.category_id
                LEFT JOIN users u ON t.user_id = u.user_id
                WHERE 1=1 AND {filter_tenant}
                """
        params = []
        if "%s" in filter_tenant:
            params.append(self.user_id,)

        if transaction_type:
            if transaction_type not in ['income', 'expense', 'transfer', 'debts']:
                raise TransactionValidationError(f"Transaction type Not Found ...Use: {'income','expense','transfer','debts'} ")
                
            query += " AND transaction_type = %s"
            params.append(transaction_type) 

        if payment_method:
            if payment_method not in ['cash','bank','mobile_money','credit_card','other']:
                raise TransactionValidationError(f"Payment Method Not Found ...Use: {'income','expense','transfer','debts'} ")
            
            query += " AND payment_method = %s"
            params.append(payment_method)

        if not include_deleted:
            query += " AND t.is_deleted = 0"

        if start_date:
            query += " AND t.transaction_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND t.transaction_date <= %s"
            params.append(end_date)
        if category_id:
            query += " AND t.category_id = %s"
            params.append(category_id)

        query += " ORDER BY t.transaction_date DESC, t.title"

        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        if offset is not None:
            query += " OFFSET %s"
            params.append(offset)

        rows = self._execute(query, tuple(params), fetch=True)
        transactions = []
        for row in rows:
            tx = self._build_transaction(row).to_dict()
            tx["category_name"] = row.get("category_name")
            tx["category_description"] = row.get("category_description")
            tx["owned_by_username"] = row.get("owned_by_username")
            transactions.append(tx)

        return {"success": True, "count": len(transactions), "transactions": transactions}

    def delete_transaction(self, transaction_id: int, soft: bool = True, recursive: bool = False) -> Dict[str, Any]:
        """
        Delete a transaction.
        soft=True → marks as deleted (is_deleted = 1)
        soft=False → permanently deletes
        recursive=True → also delete all children recursively
        """
        tx = self.get_transaction(transaction_id, include_deleted=True)
        self._audit_log(
                target_id=transaction_id,
                action="DELETE",
                old_values=tx,
            )
        user_id = self.user_id
        if not tx:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found.")

        if soft:
            self._execute("UPDATE transactions SET is_deleted = 1 WHERE transaction_id = %s AND user_id = %s", (transaction_id, user_id,))
        else:
            self._execute("DELETE FROM transactions WHERE transaction_id = %s AND user_id = %s", (transaction_id, user_id,))

        if recursive:
            children = self._get_children_recursive(transaction_id, include_deleted=True)
            for child in children:
                if soft:
                    self._execute("UPDATE transactions SET is_deleted= 1 WHERE transaction_id = %s", (child.transaction_id,))
                else:
                    self._execute("DELETE FROM transactions WHERE transaction_id = %s", (child.transaction_id,))

        return {
            "success": True,
            "message": f"Transaction {transaction_id} {'soft' if soft else 'hard'} deleted successfully.",
        }
    
    def restore_transaction(self, transaction_id: int, recursive: bool = False) -> Dict[str, Any]:
        """Restore a soft-deleted transaction (and optionally its children)."""
        tx = self.get_transaction(transaction_id, include_deleted=True)
        if not tx:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found.")
        self._audit_log(
                target_id=transaction_id,
                action="UPDATE",
                old_values={"is_deleted": True},
                new_values={"is_deleted": False},
                changed_fields=["is_deleted"],
            )
        
        self._execute("UPDATE transactions SET is_deleted = 0 WHERE transaction_id = %s AND user_id = %s", (transaction_id, self.user_id))

        if recursive:
            children = self._get_children_recursive(transaction_id, include_deleted=True)
            for child in children:
                self._execute("UPDATE transactions SET is_deleted = 0 WHERE transaction_id = %s", (child.transaction_id,))


        return {"success": True, "message": f"Transaction {transaction_id} restored successfully."}
    
    def view_audit_logs(
        self,
        target_table: str = "transactions",
        target_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        global_view: bool = False
    ) -> List[Dict[str, Any]]:

        alias = "a"   # audit_log alias
        
        # ------------------------------------
        # Tenant Filter
        # ------------------------------------
        # Admin:
        #    Global_view="True" => show only global logs
        #    Global_view="False"    => show only their own logs
        #
        # Users:
        #    always show only their own logs
        # ------------------------------------
        filter_clause = self._tenant_filter(alias, global_view)

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
