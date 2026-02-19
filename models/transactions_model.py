#CRUD logic for transactions
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any, Tuple
from datetime import date, datetime
from models.category_model import CategoryModel
from features.balance import BalanceService
from models.account_model import AccountModel
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
    account_id: Optional[int]  = None
    source_account_id: Optional[int] = None  
    destination_account_id: Optional[int] = None  
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
        self.balance_service = BalanceService(connection, current_user)
        self.category_mod = CategoryModel(connection, current_user)
        self.accounts = AccountModel(connection, current_user)

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
            account_id=row.get("account_id"),
            source_account_id=row.get("source_account_id"),
            destination_account_id=row.get("destination_account_id"),
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
            params += (self.user_id,)
        rows = self._execute(query, params, fetch=True)

        children = []
        for row in rows:
            child = self._build_transaction(row)
            child.children = self._get_children_recursive(child.transaction_id, include_deleted=include_deleted)
            children.append(child)
        return children
    
    def _assert_ownership(self, account_id: Optional[int] = None, category_id: Optional[int] =None ):
        """Validate category and account selected belongs to the user"""
        if account_id is not None:
            self.accounts.assert_account_access(account_id=account_id)
        if category_id  is not None:
            self.category_mod.assert_category_access(category_id)
    
    def _assert_parent_transaction_exists(self, parent_id: int):
        row = self._fetchone(
            """
            SELECT 1 FROM transactions
            WHERE transaction_id = %s
            AND user_id = %s
            AND is_deleted = 0
            """,
            (parent_id, self.user_id)
        )
        if not row:
            raise TransactionValidationError("Invalid parent_transaction_id")

    def _validate_transaction_accounts(self, tx_data: Dict[str, Any]):
        """
        Validate that account fields are correctly provided based on transaction type.
        
        Rules:
        - income/expense/debt_borrowed/debt_repaid: requires account_id
        - transfer/investment_deposit/investment_withdraw: requires source_account_id and destination_account_id
        """
        trans_type = tx_data.get("transaction_type")
        source_acc = tx_data.get("source_account_id")
        dest_acc = tx_data.get("destination_account_id")
        
        if trans_type in ["income", "expense", "debt_borrowed", "debt_repaid"]:
            if not tx_data.get("account_id"):
                raise TransactionValidationError(
                    f"{trans_type} transaction requires 'account_id'"
                )
        
        elif trans_type in ["transfer", "investment_deposit", "investment_withdrawal"]:
            if not source_acc:
                raise TransactionValidationError(
                    f"{trans_type} transaction requires 'source_account_id'"
                )
            if not dest_acc:
                raise TransactionValidationError(
                    f"{trans_type} transaction requires 'destination_account_id'"
                )
            if source_acc == dest_acc:
                raise TransactionValidationError(
                    "Cannot transact to the same account"
                )
            self.accounts.assert_account_access(account_id=source_acc)
            self.accounts.assert_account_access(account_id=dest_acc)

        elif source_acc and dest_acc:
            self.accounts.assert_account_access(account_id=source_acc)
            self.accounts.assert_account_access(account_id=dest_acc)
    
    # ------------
    # Public CRUD API
    # ------------
    def create_transaction(self, **tx_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new transaction record."""
        required = ["title", "amount", "transaction_type", "transaction_date"]
        missing = [f for f in required if f not in tx_data]
        if missing:
            raise TransactionValidationError(f"Missing required fields: {missing}")
        
        self._validate_transaction_accounts(tx_data)
        self._assert_ownership(tx_data.get("account_id"), tx_data.get("category_id"))
        self._assert_parent_transaction_exists(tx_data["parent_transaction_id"]) if tx_data.get("parent_transaction_id") else None
        current_user_id = self.user_id
        query = """
                INSERT INTO transactions (
                    user_id,
                    category_id,
                    parent_transaction_id,
                    title,
                    description,
                    amount,
                    transaction_type,
                    payment_method,
                    transaction_date,
                    is_global,
                    account_id,
                    source_account_id,
                    destination_account_id
                )
                SELECT
                    %s AS user_id,
                    c.category_id,
                    ptx.transaction_id AS parent_transaction_id,
                    %s AS title,
                    %s AS description,
                    %s AS amount,
                    %s AS transaction_type,
                    %s AS payment_method,
                    %s AS transaction_date,
                    %s AS is_global,
                    CASE 
                        WHEN %s IN ('income', 'expense', 'debt_borrowed', 'debt_repaid') THEN a.account_id
                        ELSE NULL
                    END AS account_id,
                    CASE 
                        WHEN %s in ('transfer', 'investment_deposit', 'investment_withdraw') THEN src.account_id
                        ELSE NULL
                    END AS source_account_id,
                    CASE 
                        WHEN %s in ('transfer', 'investment_deposit', 'investment_withdraw') THEN dst.account_id
                        ELSE NULL
                    END AS destination_account_id
                FROM (SELECT 1) AS dummy
                LEFT JOIN categories c
                    ON c.category_id = %s
                    AND c.owner_id = %s
                    AND c.is_deleted = 0
                LEFT JOIN transactions ptx
                    ON ptx.transaction_id = %s
                    AND ptx.user_id = %s
                LEFT JOIN accounts a
                    ON a.account_id = %s
                    AND a.owner_id = %s
                    AND a.is_deleted = 0
                LEFT JOIN accounts src
                    ON src.account_id = %s
                    AND src.owner_id = %s
                    AND src.is_deleted = 0
                LEFT JOIN accounts dst
                    ON dst.account_id = %s
                    AND dst.owner_id = %s
                    AND dst.is_deleted = 0
                WHERE
                    (
                        -- income / expense / debt_borrowed / debt_repaid
                        (%s IN ('income', 'expense', 'debt_borrowed', 'debt_repaid')
                        AND a.account_id IS NOT NULL
                        AND (%s IS NULL OR c.category_id IS NOT NULL)
                        AND (%s IS NULL OR ptx.transaction_id IS NOT NULL)
                        )
                    OR
                        -- transfer/investment_deposit/investment_withdraw
                        (%s in ('transfer', 'investment_deposit', 'investment_withdraw')
                        AND src.account_id IS NOT NULL
                        AND dst.account_id IS NOT NULL
                        AND src.account_id <> dst.account_id
                        AND (%s IS NULL OR ptx.transaction_id IS NOT NULL)
                        )
                    )
                LIMIT 1;
            """

        params = (
            # SELECT
            current_user_id,
            tx_data["title"],
            tx_data.get("description"),
            tx_data["amount"],
            tx_data["transaction_type"],
            tx_data.get("payment_method", "mobile_money"),
            tx_data["transaction_date"],
            tx_data.get("is_global", 0),
            
            # CASE statements for account columns
            tx_data["transaction_type"],  # for account_id CASE
            tx_data["transaction_type"],  # for source_account_id CASE
            tx_data["transaction_type"],  # for destination_account_id CASE

            # category join
            tx_data.get("category_id"),
            current_user_id,

            # parent transaction join
            tx_data.get("parent_transaction_id"),
            current_user_id,

            # accounts join (for income/expense/debt_repaid/debt_borrowed)
            tx_data.get("account_id"),
            current_user_id,

            # transfer/investment joins
            tx_data.get("source_account_id"),
            current_user_id,
            tx_data.get("destination_account_id"),
            current_user_id,

            # WHERE (income/expense/debt_borrowed/debt_repaid)
            tx_data["transaction_type"],
            tx_data.get("category_id"),
            tx_data.get("parent_transaction_id"),

            # WHERE (transfer/investments)
            tx_data["transaction_type"],
            tx_data.get("parent_transaction_id"),
        )
        new_id = self._execute(query, params)
        if new_id == 0:
            raise TransactionError("Ownership validation failed.... Invalid Account, Category or Parent trasaction selected")

        # Apply balance changes automatically
        try:
            self.balance_service.apply_transaction_change(
                transaction_id=new_id,
                transaction_type=tx_data["transaction_type"],
                amount=float(tx_data["amount"]),
                account_id=tx_data.get("account_id"),
                source_account_id=tx_data.get("source_account_id"),
                destination_account_id=tx_data.get("destination_account_id"),
                allow_overdraft=tx_data.get("allow_overdraft", False)
            )
        except Exception as e:
            # Rollback transaction if balance update fails
            self._execute(
                "DELETE FROM transactions WHERE transaction_id = %s",
                (new_id,)
            )
            raise TransactionValidationError(
                f"Transaction created but balance update failed: {str(e)}"
            )
    
        self._audit_log(new_id, action="TRANSACTION_CREATED",
                        new_values={
                            "name": tx_data["title"], 
                            "amount": tx_data["amount"], 
                            "trans_type": tx_data["transaction_type"],
                            "transaction_date": tx_data["transaction_date"],
                            "account_id": tx_data.get("account_id"),
                            "source_account_id": tx_data.get("source_account_id"),
                            "destination_account_id": tx_data.get("destination_account_id"),
                        }
                        )
        return self.get_transaction(new_id)
    
    def get_transaction(self, transaction_id: int, include_children: bool = False, *, include_deleted: bool = False, global_view: bool = False) -> Dict[str, Any]:
        """Fetch a transaction (optionally including nested children)."""
        filter_tenant = self._tenant_filter("t", global_view=global_view)
        query = f"""
                SELECT t.*, 
                       c.name AS category_name, 
                       c.description AS category_description, 
                       u.username AS owned_by_username,
                       a.name AS account_name,
                       sa.name AS source_account_name,
                       da.name AS destination_account_name
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.category_id
                LEFT JOIN users u ON t.user_id = u.user_id
                LEFT JOIN accounts a ON t.account_id = a.account_id
                LEFT JOIN accounts sa ON t.source_account_id = sa.account_id
                LEFT JOIN accounts da ON t.destination_account_id = da.account_id
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
        result["account_name"] = rows[0].get("account_name")
        result["source_account_name"] = rows[0].get("source_account_name")
        result["destination_account_name"] = rows[0].get("destination_account_name")
        return result
    
    def _update_safe_fields(self, transaction_id: int,  safe: Dict[str, Any]) -> int:
        #Update transaction for safe fields
        fields = ", ".join((f"{k}=%s" for k in safe.keys()))
        params = tuple(safe.values()) + (transaction_id, self.user_id)
        result = self._execute(
            f"UPDATE transactions SET {fields} WHERE transaction_id = %s AND user_id = %s AND is_deleted = 0", params
        )
        if result == 0:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found or unchanged.")
        return result
        
    def _update_sensitive_fields(self, transaction_id: int, sensitive_fields: dict
        ) -> int:
        current_tx = self.get_transaction(transaction_id)
        if not current_tx:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found")

        tx_type = sensitive_fields.get(
            "transaction_type",
            current_tx["transaction_type"]
        )

        updates = {}

        # -----------------------------
        # TRANSACTION TYPE RULES
        # -----------------------------
        if tx_type in {"income", "expense", "debt_borrowed", "debt_repaid"}:
            updates["account_id"] = sensitive_fields.get("account_id")
            updates["source_account_id"] = None
            updates["destination_account_id"] = None

        elif tx_type in {"transfer", "investment_deposit", "investment_withdraw"}:
            updates["account_id"] = None
            updates["source_account_id"] = sensitive_fields.get("source_account_id")
            updates["destination_account_id"] = sensitive_fields.get("destination_account_id")

        else:
            raise TransactionValidationError("Unknown transaction type")

        if "parent_transaction_id" in sensitive_fields:
            self._assert_parent_transaction_exists(sensitive_fields["parent_transaction_id"])
            updates["parent_transaction_id"] = sensitive_fields["parent_transaction_id"]

        if "transaction_type" in sensitive_fields:
            updates["transaction_type"] = sensitive_fields["transaction_type"]

        if not updates:
            return 0
        # -----------------------------
        # BUILD SAFE UPDATE
        # -----------------------------
        fields = ", ".join(f"{k} = %s" for k in updates)
        params = list(updates.values()) + [transaction_id, self.user_id]

        query = f"""
            UPDATE transactions
            SET {fields}
            WHERE transaction_id = %s
            AND user_id = %s
            AND is_deleted = 0
        """

        result = self._execute(query, tuple(params))
        if result == 0:
            raise TransactionNotFoundError(
                f"Transaction {transaction_id} not updated"
            )

        return result

        
    def update_transaction(self, transaction_id: int, **updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update transaction fields."""
        if not updates:
            raise TransactionValidationError("No fields provided for update.")
        
        old_trans = self.get_transaction(transaction_id)
        old_trans_type = old_trans["transaction_type"]
        self._validate_transaction_accounts(updates)
        self._assert_ownership(updates.get("account_id"), updates.get("category_id"))
        
        # Separate safe and sensitive fields
        SAFE = {"title", "amount", "transaction_date", "description", "payment_method"}
        SENSITIVE = {"account_id", "category_id", "transaction_type", "parent_transaction_id", "source_account_id", "destination_account_id"}
        safe_fields = {key: value for key, value in updates.items() if key in SAFE}
        sensitive_fields = {key: value for key, value in updates.items() if key in SENSITIVE}
        # Update fields
        if sensitive_fields:
            self._update_sensitive_fields(transaction_id, sensitive_fields)

        if safe_fields:
            self._update_safe_fields(transaction_id, safe_fields)
        
        # If updating amount or accounts, validate and handle balance changes
        balance_affecting_fields = {"amount", "transaction_type", "account_id", 
                                   "source_account_id", "destination_account_id"}
        affects_balance = any(field in updates for field in balance_affecting_fields)
        
        if affects_balance and self.balance_service:
            # Reverse old transaction's balance effects
            try:
                self.balance_service.reverse_transaction_change(
                    transaction_id=transaction_id,
                    source=f"REVERSED_{old_trans_type}",
                    transaction_data=old_trans
                )
            except Exception as e:
                raise TransactionValidationError(
                    f"Failed to reverse old balance: {str(e)}"
                )
        
        # Apply new transaction's balance effects
        if affects_balance and self.balance_service:
            # Get updated transaction data
            updated_trans = self.get_transaction(transaction_id)
            
            try:
                self.balance_service.apply_transaction_change(
                    transaction_id=transaction_id,
                    transaction_type=updated_trans["transaction_type"],
                    amount=float(updated_trans["amount"]),
                    account_id=updated_trans.get("account_id"),
                    source_account_id=updated_trans.get("source_account_id"),
                    destination_account_id=updated_trans.get("destination_account_id"),
                    allow_overdraft=updates.get("allow_overdraft", False)
                )
            except Exception as e:
                # Try to reapply old balance if new one fails
                try:
                    self.balance_service.apply_transaction_change(
                        transaction_id=transaction_id,
                        transaction_type=old_trans["transaction_type"],
                        amount=float(old_trans["amount"]),
                        account_id=old_trans.get("account_id"),
                        source_account_id=old_trans.get("source_account_id"),
                        destination_account_id=old_trans.get("destination_account_id"),
                        allow_overdraft=True
                    )
                except:
                    pass
                
                raise TransactionValidationError(
                    f"Transaction updated but balance update failed: {str(e)}"
                )
        
        self._audit_log(transaction_id, action="TRANSACTION_UPDATED", old_values=old_trans, 
                       new_values=updates, changed_fields=list(updates.keys()))
        updated = self.get_transaction(transaction_id)
        return {"success": True, "message": "Transaction updated successfully.", "update": updated}
    
    def list_transactions(
        self,
        transaction_type: Optional[str] = None,
        payment_method: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        category_id: Optional[int] = None,
        account_id: Optional[int] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None, *,
        include_deleted: bool = False,
        global_view: bool = False
    ) -> Dict[str, Any]:
        """Filter transactions by user/date/category with optional pagination."""
        filter_tenant = self._tenant_filter("t", global_view=global_view)
        query = f"""
                SELECT t.*, 
                       c.name AS category_name, 
                       c.description AS category_description, 
                       u.username AS owned_by_username,
                       a.name AS account_name,
                       sa.name AS source_account_name,
                       da.name AS destination_account_name
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.category_id
                LEFT JOIN users u ON t.user_id = u.user_id
                LEFT JOIN accounts a ON t.account_id = a.account_id
                LEFT JOIN accounts sa ON t.source_account_id = sa.account_id
                LEFT JOIN accounts da ON t.destination_account_id = da.account_id
                WHERE 1=1 AND {filter_tenant}
                """
        params = []
        if "%s" in filter_tenant:
            params.append(self.user_id,)

        if transaction_type:
            if transaction_type not in {'income', 'expense', 'transfer', 'debt_repaid', 'debt_borrowed', 'investment_deposit', 'investment_withdraw'}:
                raise TransactionValidationError(f"Transaction type Not Found ...Use: {'income', 'expense', 'transfer', 'debt_repaid', 'debt_borrowed', 'investment_deposit', 'investment_withdraw'} ")
                
            query += " AND transaction_type = %s"
            params.append(transaction_type) 

        if payment_method:
            if payment_method not in ['cash','bank','mobile_money','credit_card','other']:
                raise TransactionValidationError(f"Payment Method Not Found ...Use: {'income', 'expense', 'transfer', 'debt_repaid', 'debt_borrowed', 'investment_deposit', 'investment_withdraw'} ")
            
            query += " AND payment_method = %s"
            params.append(payment_method)
        
        if account_id:
            query += " AND (t.account_id = %s OR t.source_account_id = %s OR t.destination_account_id = %s)"
            params.extend([account_id, account_id, account_id])

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
            tx["account_name"] = row.get("account_name")
            tx["source_account_name"] = row.get("source_account_name")
            tx["destination_account_name"] = row.get("destination_account_name")
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
        tx_trans_type = tx["transaction_type"]

        if soft:
            self._execute("UPDATE transactions SET is_deleted = 1 WHERE transaction_id = %s AND user_id = %s", (transaction_id, user_id,))
        else:
            self._execute("DELETE FROM transactions WHERE transaction_id = %s AND user_id = %s", (transaction_id, user_id,))

        if recursive:
            children = self._get_children_recursive(transaction_id, include_deleted=True)
            for child in children:
                # Reverse balance for children too
                try:
                    child_data = self.get_transaction(child.transaction_id, include_deleted=True)
                    child_trans_type = child_data["transaction_type"]
                    self.balance_service.reverse_transaction_change(
                        transaction_id=child.transaction_id,
                        source=f"REVERSED_{child_trans_type}",
                        transaction_data=child_data
                    )
                except:
                    pass 
                if soft:
                    self._execute("UPDATE transactions SET is_deleted= 1 WHERE transaction_id = %s", (child.transaction_id,))
                else:
                    self._execute("DELETE FROM transactions WHERE transaction_id = %s", (child.transaction_id,))
        # ✨ NEW: Reverse balance changes when deleting
        
        try:
            self.balance_service.reverse_transaction_change(
                transaction_id=transaction_id,
                source=f"REVERSED_{tx_trans_type}",
                transaction_data=tx
            )
        except Exception as e:
            raise TransactionValidationError(
                f"Failed to reverse balance on delete: {str(e)}"
            )
        
        self._audit_log(
                target_id=transaction_id,
                action="TRANSACTION_DELETED",
                old_values=tx,
            )
        user_id = self.user_id
        if not tx:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found.")


        return {
            "success": True,
            "message": f"Transaction {transaction_id} {'soft' if soft else 'hard'} deleted successfully.",
        }
    
    def restore_transaction(self, transaction_id: int, recursive: bool = False) -> Dict[str, Any]:
        """Restore a soft-deleted transaction (and optionally its children)."""
        tx = self.get_transaction(transaction_id, include_deleted=True)
        if not tx:
            raise TransactionNotFoundError(f"Transaction {transaction_id} not found.")
        
        try:
                self.balance_service.apply_transaction_change(
                    transaction_id=transaction_id,
                    transaction_type=tx["transaction_type"],
                    amount=float(tx["amount"]),
                    account_id=tx.get("account_id"),
                    source_account_id=tx.get("source_account_id"),
                    destination_account_id=tx.get("destination_account_id"),
                    allow_overdraft=True  # Allow overdraft on restore
                )
        except Exception as e:
            raise TransactionValidationError(
                f"Failed to reapply balance on restore: {str(e)}"
            )
        self._audit_log(
                target_id=transaction_id,
                action="TRANSACTION_UPDATED",
                old_values={"is_deleted": True},
                new_values={"is_deleted": False},
                changed_fields=["is_deleted"],
            )
        
        self._execute("UPDATE transactions SET is_deleted = 0 WHERE transaction_id = %s AND user_id = %s", (transaction_id, self.user_id))

        if recursive:
            children = self._get_children_recursive(transaction_id, include_deleted=True)
            for child in children:
                child_data = self.get_transaction(child.transaction_id, include_deleted=True)
                self.balance_service.apply_transaction_change(
                    transaction_id=child.transaction_id,
                    transaction_type=child_data["transaction_type"],
                    amount=float(child_data["amount"]),
                    account_id=child_data.get("account_id"),
                    source_account_id=child_data.get("source_account_id"),
                    destination_account_id=child_data.get("destination_account_id"),
                    allow_overdraft=True
                )
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
