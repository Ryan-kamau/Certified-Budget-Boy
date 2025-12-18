#Logic for recurrin transactions
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, date
from models.transactions_model import TransactionModel
from models.category_model import CategoryModel
from models.account_model import AccountModel
import mysql.connector
import json


# ================================================================
# Custom Exceptions (same style as your models)
# ================================================================
class RecurringError(Exception):
    pass

class RecurringNotFoundError(RecurringError):
    pass

class RecurringValidationError(RecurringError):
    pass

class RecurringDatabaseError(RecurringError):
    pass


# ================================================================
# Dataclass: RecurringTransaction (mirrors DB table)
# ================================================================
@dataclass
class RecurringTransaction:
    recurring_id: Optional[int] = None
    owner_id: int = 0
    is_global: int = 0
    name: str = ""
    description: Optional[str] = None
    frequency: str = "monthly"
    interval_value: int = 1
    next_due: datetime = None
    last_run: Optional[datetime] = None
    max_missed_runs: int = 12
    last_run_status: str = "success"
    pause_until: Optional[datetime] = None
    skip_next: int = 0
    override_amount: Optional[float] = None
    amount: float = 0.0
    category_id: int = None
    transaction_type: str = "expense"
    payment_method: str = "mobile_money"
    notes: Optional[str] = None
    is_active: int = 1
    is_deleted: int = 0
    account_id: Optional[int] = None  
    source_account_id: Optional[int] = None 
    destination_account_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert dataclass to clean dict for API responses."""
        return asdict(self)


# ================================================================
# Model Class: RecurringModel
# Structure matches your TransactionModel style
# ================================================================
class RecurringModel:
    def __init__(self, db_conn, current_user: Dict[str, Any]):
        self.conn = db_conn
        self.user = current_user  # { user_id, role }
        self.transaction_model = TransactionModel(db_conn, current_user)
        self.cat_man = CategoryModel(db_conn, current_user)
        self.accounts = AccountModel(db_conn, current_user)

    # ================================================================
    # Internal Helpers
    # ================================================================
    def _execute(self, sql: str, params: Tuple[Any, ...], *, fetchone: bool = False, fetchall: bool = False):
        """Unified SQL executor with error wrapping"""
        # validate flags
        if fetchone and fetchall:
            raise RecurringDatabaseError("Invalid flags: fetchone and fetchall cannot both be True")
        
        try:
            with self.conn.cursor(dictionary=True) as cursor:
                cursor.execute(sql, params)
                if fetchone:
                    result = cursor.fetchone()
                    self.conn.commit()
                    return result

                if fetchall:
                    result = cursor.fetchall()
                    self.conn.commit()
                    return result

                self.conn.commit()
                if sql.strip().upper().startswith("UPDATE"):
                    return cursor.rowcount
                return cursor.lastrowid

        except mysql.connector.Error as e:
            try:
                self.conn.rollback()
            except:
                pass

            raise RecurringDatabaseError(f"MySQL Error: {str(e)}")
        
    def _tenant_filter(self, global_view: bool =False):
        "Row-level isolation."
        if self.user.get("role") == "admin":
            if global_view:
                return "is_global = 1"
            else:
                return "owner_id = %s"
            
        else:
            if not global_view:
                return "owner_id = %s"
            else:
                raise RecurringValidationError("Users can only view and control own data")
            
    def _audit_log(self, target_id: int, action: str, **new_values: Dict[str, Any]):
        """Simple JSON audit logger ."""
        sql = """
                INSERT INTO audit_log
                    (user_id, target_table, target_id, action, new_values,
                    timestamp)
                    VALUES (%s, %s, %s, %s, %s, NOW())
            """
        
        if new_values:
            for k in ("transaction_date","created_at","updated_at"):
                if k in new_values and new_values[k]:
                    new_values[k] = new_values[k].isoformat()

        params = (self.user.get("user_id"), "recurring_transactions", target_id, action,
                  json.dumps(new_values or {}, default=str))
        affected = self._execute(sql, params)

        if not affected:
            raise RecurringValidationError("Audit ot completed")
        
    def _build_recurring(self, row: Dict[str, Any]) -> RecurringTransaction:
        # Convert DB row keys into appropriate types if needed
        return RecurringTransaction(**row)
    
    #Internal mini-transaction abstraction
    def _validate_recurring_accounts(self, data: Dict[str, Any]):
        """
        Validate that account fields are correctly provided based on transaction type.
        
        Rules:
        - income/expense: requires account_id
        - transfer: requires source_account_id and destination_account_id
        """
        trans_type = data.get("transaction_type")
        
        if trans_type in ["income", "expense", "debt"]:
            if not data.get("account_id"):
                raise RecurringValidationError(
                    f"{trans_type} recurring transaction requires 'account_id'"
                )
        
        elif trans_type == "transfer":
            source_acc = data.get("source_account_id")
            dest_acc = data.get("destination_account_id")
            if not source_acc:
                raise RecurringValidationError(
                    "transfer recurring transaction requires 'source_account_id'"
                )
            if not dest_acc:
                raise RecurringValidationError(
                    "transfer recurring transaction requires 'destination_account_id'"
                )
            if source_acc == dest_acc:
                raise RecurringValidationError(
                    "Cannot transfer to the same account"
                )
            self.accounts.assert_account_access(account_id=source_acc)
            self.accounts.assert_account_access(account_id=dest_acc)
            
    def _create_transaction(self, recurring: RecurringTransaction, amount: float) -> int:
        """
        Create a transaction using TransactionModel.
        This ensures balance updates and all business logic is applied.
        """
        if not self.transaction_model:
            raise RecurringDatabaseError(
                "TransactionModel not available. Cannot create transaction."
            )
        
        # Build transaction data from recurring
        tx_data = {
            "title": recurring.name,
            "description": recurring.notes or f"Auto-generated from recurring: {recurring.name}",
            "amount": amount,
            "category_id": recurring.category_id,
            "transaction_type": recurring.transaction_type,
            "payment_method": recurring.payment_method,
            "transaction_date": date.today(),
            "is_global": recurring.is_global,
            "account_id": recurring.account_id,
            "source_account_id": recurring.source_account_id,
            "destination_account_id": recurring.destination_account_id,
        }
        
        # Create transaction using TransactionModel
        # This automatically handles balance updates via BalanceService
        result = self.transaction_model.create_transaction(**tx_data)
        
        return result["transaction_id"]
    
    def _assert_ownership(self, account_id: Optional[int] = None, category_id: Optional[int] =None ):
        """Validate category and account selected belongs to the user"""
        if account_id:
            self.accounts.assert_account_access(account_id=account_id)
        if category_id:
            self.cat_man.assert_category_access(category_id)

    def _record_history(self,
                        owner_id: int,
                        recurring_id: int,
                        run_date: datetime,
                        amount_used: float,
                        status: str,
                        override_used: bool,
                        posted_transaction_id: Optional[int] = None,
                        message: Optional[str] = None):
        """
        Insert a history row into recurring_logs.
        """
        insert_sql = """
            INSERT INTO recurring_logs
            (owner_id, recurring_id, run_date, amount_used, status, override_used, posted_transaction_id, message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            owner_id,
            recurring_id,
            run_date,
            amount_used,
            status,
            1 if override_used else 0,
            posted_transaction_id,
            message
        )
        try:
            self._execute(insert_sql, params)
        except RecurringDatabaseError:
            # never let logging break the main flow; swallow after optionally recording to audit log
            try:
                self._audit_log(recurring_id, action="FAILED TO INSERT")
            except Exception:
                pass

    #--------------------
    # CRUD OPERATIONS
    #--------------------
    def create(self, **data: Dict[str, Any]) -> Dict[str, Any]:
        required = ["name", "frequency", "next_due", "amount", "category_id", "transaction_type"]
        missing = [f for f in required if f not in data]
        if missing:
            raise RecurringValidationError(f"Missing required fields: {missing}")
        
        # Validate account and category fields
        self._validate_recurring_accounts(data)
        current_user_id = self.user["user_id"]
        # Include account fields in INSERT
        sql = """
            INSERT INTO recurring_transactions
            (owner_id, is_global, name, description, frequency, interval_value,
             next_due, amount, category_id, transaction_type, payment_method, notes,
             account_id, source_account_id, destination_account_id)
            SELECT 
                %s AS owner_id, %s AS is_global, %s AS name, %s AS description, %s AS frequency, %s AS interval_value,
                %s AS next_due, %s AS amount, c.category_id, %s AS transaction_type, %s AS payment_method, %s AS notes,
                a.account_id, src.account_id, dst.account_id

            FROM accounts a
            LEFT JOIN categories c
                ON c.category_id = %s
                AND c.owner_id = %s
                AND c.is_deleted = 0
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
                -- income / expense
                (%s IN ('income','expense')
                AND a.account_id = %s
                AND a.owner_id = %s
                AND a.is_deleted = 0
                AND (%s IS NULL OR c.category_id IS NOT NULL)
                )
            OR
                -- transfer
                (%s = 'transfer'
                AND src.account_id IS NOT NULL
                AND dst.account_id IS NOT NULL
                AND src.account_id <> dst.account_id
                )
            )
        LIMIT 1;
            
        """

        params = (
            self.user["user_id"],
            data.get("is_global", 0),
            data["name"],
            data.get("description"),
            data["frequency"],
            data.get("interval_value", 1),
            data["next_due"],
            data["amount"],
            data["transaction_type"],
            data.get("payment_method", "mobile_money"),
            data.get("notes"),
            # category join
            data.get("category_id"),
            current_user_id,

            # transfer joins
            data.get("source_account_id"),
            current_user_id,
            data.get("destination_account_id"),
            current_user_id,

            # WHERE (income/expense)
            data["transaction_type"],
            data.get("account_id"),
            current_user_id,
            data.get("category_id"),

            # WHERE (transfer)
            data["transaction_type"],
        )


        new_id = self._execute(sql, params)
        if new_id == 0:
            raise RecurringDatabaseError("OWNERSHIP VALIDATION FAILED.... Invalid Account or Category selected")
        new_details = self.get_recurring(new_id)

        self._audit_log(new_id, "INSERT", **new_details)
        return {"success": True, "recurring_id": new_id}
    
    def get_recurring(self, recurring_id: int, * , include_deleted: bool = False, global_view: bool = False) -> Dict[str, Any]:
        filter_tenant = f"r.{self._tenant_filter(global_view)}"
        sql = f"""
            SELECT r.*, 
                   u1.username AS owned_by_username, 
                   c.name AS category_name,
                   a.name AS account_name,
                   sa.name AS source_account_name,
                   da.name AS destination_account_name
            FROM recurring_transactions r
            LEFT JOIN users u1 ON r.owner_id = u1.user_id
            LEFT JOIN categories c ON r.category_id = c.category_id
            LEFT JOIN accounts a ON r.account_id = a.account_id
            LEFT JOIN accounts sa ON r.source_account_id = sa.account_id
            LEFT JOIN accounts da ON r.destination_account_id = da.account_id
            WHERE r.recurring_id = %s AND {filter_tenant}
        """
        params = [recurring_id]
        if not include_deleted:
            sql += " AND r.is_deleted = 0"
        if "%s" in filter_tenant:
            params.append(self.user["user_id"])

        # using dict param style for tenant filter
        row = self._execute(sql, tuple(params), fetchone=True)

        if not row:
            raise RecurringNotFoundError("Recurring transaction not found.")
        # filter row for dataclass
        model_fields = RecurringTransaction.__annotations__.keys()
        clean_row = {k: v for k, v in row.items() if k in model_fields}
 
        result = self._build_recurring(clean_row).to_dict()
        result["category_name"] = row["category_name"]
        result["owned_by_username"] = row["owned_by_username"]
        result["account_name"] = row.get("account_name")
        result["source_account_name"] = row.get("source_account_name")
        result["destination_account_name"] = row.get("destination_account_name")
        return result
    
    def list(self,frequency: str, trans_type: str,*, include_deleted: bool = False, global_view: bool = False) -> List[Dict[str, Any]]:
        filter_tenant = f"r.{self._tenant_filter(global_view)}"
        sql = f"""
            SELECT r.*,  
                   u1.username AS owned_by_username, 
                   c.name AS category_name,
                   a.name AS account_name,
                   sa.name AS source_account_name,
                   da.name AS destination_account_name
            FROM recurring_transactions r
            LEFT JOIN users u1 ON r.owner_id = u1.user_id
            LEFT JOIN categories c ON r.category_id = c.category_id
            LEFT JOIN accounts a ON r.account_id = a.account_id
            LEFT JOIN accounts sa ON r.source_account_id = sa.account_id
            LEFT JOIN accounts da ON r.destination_account_id = da.account_id
            WHERE 1=1
            {"" if include_deleted else "AND r.is_deleted = 0"}
            AND {filter_tenant}
        """
        params = []
        if "%s" in filter_tenant:
            params.append(self.user["user_id"])
        
        #filters used to list
        if frequency:
            if frequency not in ['daily','weekly','monthly','yearly']:
                raise RecurringValidationError("Frequency not Found......USE:('daily','weekly','monthly','yearly')")
            
            sql += " AND r.frequency = %s"
            params.append(frequency)
        if trans_type:
            if trans_type not in ['income', 'expense', 'transfer', 'debts']:
                raise  RecurringValidationError("Transaction type Not Found ...Use: ('income','expense','transfer','debts') ")
                
            sql += " AND r.transaction_type = %s"
            params.append(trans_type) 
        
        sql += " ORDER BY next_due ASC"
        rows = self._execute(sql, tuple(params), fetchall=True)
        rt = []
        # filter row for dataclass
        model_fields = RecurringTransaction.__annotations__.keys()
        for r in rows:
            clean_row = {k: v for k, v in r.items() if k in model_fields}
            result = self._build_recurring(clean_row).to_dict()
            result["owned_by_username"] = r.get("owned_by_username")
            result["category_name"] = r.get("category_name")
            result["account_name"] = r.get("account_name")
            result["source_account_name"] = r.get("source_account_name")
            result["destination_account_name"] = r.get("destination_account_name")
            rt.append(result)
        return rt
    
    def _update_safe_fields(self, recurring_id: int, current_user_id: int,  safe: Dict[str, Any]) -> int:
        #Update recurring transaction for safe fields
        fields = ", ".join((f"{k}=%s" for k in safe.keys()))
        params = tuple(safe.values()) + (recurring_id, current_user_id,)
        result = self._execute(
            f"UPDATE recurring_transactions SET {fields} WHERE recurring_id = %s AND owner_id = %s", params
        )
        if result == 0:
            raise RecurringNotFoundError(f"Recurring {recurring_id} not found or unchanged.")
        return result
        
    def _update_sensitive_fields(self, recurring_id:int, current_user_id: int, sensitive_fields: Dict) -> int:
        #update recurring transactions with sensitive fields with ownership validation
        set_clauses = []
        join_clauses = []
        where_clauses = ["r.recurring_id = %s", "r.owner_id = %s"]
        params = []

        # Account validation
        if "account_id" in sensitive_fields:
            join_clauses.append("""
                LEFT JOIN accounts a
                ON a.account_id = %s
                AND a.owner_id = %s
                AND a.is_deleted = 0
            """)
            set_clauses.append("r.account_id = a.account_id")
            where_clauses.append("(%s IS NULL OR a.account_id IS NOT NULL)")
            params.extend([sensitive_fields["account_id"], current_user_id, sensitive_fields["account_id"]])
        
        # Category validation
        if "category_id" in sensitive_fields:
            join_clauses.append("""
                LEFT JOIN categories c
                ON c.category_id = %s
                AND c.owner_id = %s
                AND c.is_deleted = 0
            """)
            set_clauses.append("r.category_id = c.category_id")
            where_clauses.append("(%s IS NULL OR c.category_id IS NOT NULL)")
            params.extend([sensitive_fields["category_id"], current_user_id, sensitive_fields["category_id"]])
        
        
        # Source account validation (for transfers)
        if "source_account_id" in sensitive_fields:
            join_clauses.append("""
                LEFT JOIN accounts src
                ON src.account_id = %s
                AND src.owner_id = %s
                AND src.is_deleted = 0
            """)
            set_clauses.append("r.source_account_id = src.account_id")
            where_clauses.append("(%s IS NULL OR src.account_id IS NOT NULL)")
            params.extend([
                sensitive_fields["source_account_id"], 
                current_user_id, 
                sensitive_fields["source_account_id"]
            ])
        
        # Destination account validation (for transfers)
        if "destination_account_id" in sensitive_fields:
            join_clauses.append("""
                LEFT JOIN accounts dest
                ON dest.account_id = %s
                AND dest.owner_id = %s
                AND dest.is_deleted = 0
            """)
            set_clauses.append("r.destination_account_id = dest.account_id")
            where_clauses.append("(%s IS NULL OR dest.account_id IS NOT NULL)")
            params.extend([
                sensitive_fields["destination_account_id"], 
                current_user_id, 
                sensitive_fields["destination_account_id"]
            ])
        
        if not set_clauses:
            return 0  # Nothing to update
        
        # Add WHERE params at the end
        params.extend([recurring_id, current_user_id])
        
        query = f"""
            UPDATE recurring_transactions r
            {' '.join(join_clauses)}
            SET {', '.join(set_clauses)}
            WHERE {' AND '.join(where_clauses)}
        """
        
        result = self._execute(query, tuple(params))
        if result == 0:
            raise RecurringDatabaseError(
                f"Recurring transaction {recurring_id} not UPDATED or VALIDATION failed."
            )
        return result
        

    def update(self, recurring_id: int, **updates: Dict[str, Any]) -> Dict[str, Any]:
        if not updates:
            raise RecurringValidationError("No update fields provided.")
        
        current_user_id = self.user["user_id"]
        #Separate safe and sensitive fields
        SAFE = ["is_global", "name", "description", "frequency", "interval_value", "next_due", "last_run", "max_missed_runs", 
                "pause_until", "skip_next", "override_amount", "amount",  "transaction_type", "payment_method", "notes", "is_active",
                "is_deleted", "created_at",
                ]
        SENSITIVE = ["account_id", "category_id", "parent_transaction_id", "source_account_id", "destination_account_id"]
        safe_fields = {keys: values for keys, values in updates.items() if keys in SAFE}
        sensitive_fields = {key: value for key, value in updates.items() if key in SENSITIVE}
        # Update fields
        if sensitive_fields:
            self._update_sensitive_fields(recurring_id, current_user_id, sensitive_fields)

        if safe_fields:
            self._update_safe_fields(recurring_id, current_user_id, safe_fields)
        
        
        updated = self.get_recurring(recurring_id)
        self._audit_log(recurring_id, "UPDATE", **updated)

        return {"success": True, "Updated": updated}
    
    def delete_recurring(self, recurring_id: int, soft: bool = True) -> Dict[str, Any]:
        """
        Delete a recurring transaction.
        soft=True → marks as deleted (is_deleted = 1)
        soft=False → permanently deletes
        """
        tx = self.get_recurring(recurring_id, include_deleted=True)
        self._audit_log(
                target_id=recurring_id,
                action="DELETE",
            )
        user_id = self.user["user_id"]
        if not tx:
            raise RecurringNotFoundError(f"Recurring Transaction {recurring_id} not found.")

        if soft:
            self._execute("UPDATE recurring_transactions SET is_deleted = 1 WHERE recurring_id = %s AND owner_id = %s", (recurring_id, user_id,))
        else:
            self._execute("DELETE FROM recurring_transactions WHERE recurring_id = %s AND owner_id = %s", (recurring_id, user_id,))

        return {
            "success": True,
            "message": f"Transaction {recurring_id} {'soft' if soft else 'hard'} deleted successfully.",
        }

    def restore(self, recurring_id: int) -> Dict[str, Any]:
        sql = f"""
            UPDATE recurring_transactions
            SET is_deleted = 0
            WHERE recurring_id = %s AND owner_id = %s
        """

        self._execute(sql, (recurring_id, self.user["user_id"]))
        self._audit_log(recurring_id, "UPDATE", is_deleted= False)

        return {"success": True, "message": f"Recurring Transaction {recurring_id} restored successfully."}

    def get_history(self,
                *,
                recurring_id: Optional[int] = None,
                limit: Optional[int] = None,
                status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve execution history for recurring transactions, or specific recurring transaction, 
        filtered by owner_id for tenant isolation.

        Optional filters:
            - recurring id : for specific transaction
            - limit: restrict number of rows
            - status: filter by 'generated', 'skipped', or 'failed'
        """
        owner_id = self.user["user_id"]
        sql = """
            SELECT 
                log_id,
                owner_id,
                recurring_id,
                run_date,
                amount_used,
                status,
                override_used,
                posted_transaction_id,
                message,
                created_at
            FROM recurring_logs
            WHERE owner_id = %s
        """

        params: List[Any] = [owner_id]
        if recurring_id:
            sql += " AND recurring_id = %s"
            params.append(recurring_id)

        if status:
            sql += " AND status = %s"
            params.append(status)

        sql += " ORDER BY run_date DESC"

        if limit:
            sql += " LIMIT %s"
            params.append(limit)

        return self._execute(sql, tuple(params), fetchall=True)
    
    def view_audit_logs(
        self,
        target_table: str = "recurring_transactions",
        target_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        global_view: bool = False
    ) -> List[Dict[str, Any]]:

        
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
        filter_clause = f"a.{self._tenant_filter(global_view)}"

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
            params.append(self.user["user_id"])

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

        return self._execute(q, tuple(params), fetchall=True)

    def run_due(self) -> List[int]:
        """
        Executes all due recurring rules.
        Returns list of created transaction IDs.
        """

        sql = """
            SELECT *
            FROM recurring_transactions
            WHERE is_deleted = 0
              AND is_active = 1
              AND next_due <= NOW()
              AND owner_id = %s
        """

        rows = self._execute(sql, (self.user["user_id"],), fetchall=True)
        created_ids = []

        for row in rows:
            try:
                rec = self._build_recurring(row)

                # Skip if paused until future date
                if rec.pause_until and isinstance(rec.pause_until, date) and rec.pause_until > datetime.now().date():
                    self._record_history(
                        self.user["user_id"],
                        recurring_id=rec.recurring_id,
                        run_date=datetime.now(),
                        amount_used = rec.override_amount if rec.override_amount is not None else rec.amount,
                        status="skipped",
                        override_used=bool(rec.override_used),
                        posted_transaction_id= None,
                        message="paused untill date",
                    )
                    self.update(rec.recurring_id, last_run_status="skipped")
                    continue

                # Skip if skip_next flag set
                if rec.skip_next == 1:
                    self.update(rec.recurring_id, skip_next= 0, last_run_status="skipped")
                    self._record_history(
                        self.user["user_id"],
                        recurring_id=rec.recurring_id,
                        run_date=datetime.now(),
                        amount_used=rec.override_amount if rec.override_amount is not None else rec.amount,
                        status="skipped",
                        override_used=bool(rec.override_amount),
                        posted_transaction_id=None,
                        message="skip_next flag consumed."
                    )
                    continue

                # Determine amount (apply override once)
                override_used = False
                amount_to_use = rec.amount
                if rec.override_amount is not None:
                    amount_to_use = rec.override_amount
                    override_used = True

                new_tx_id = self._create_transaction(rec, amount_to_use)
                created_ids.append(new_tx_id)

                # Prepare next_due
                new_next = self._calculate_next_due(rec.frequency, rec.interval_value, rec.next_due)

                # Update recurring entry (advance next_due, clear override_amount)
                update_fields = {
                    "last_run": datetime.now(),
                    "last_run_status": "success",
                    "next_due": new_next,
                    "override_amount": None  # reset single-use override
                }
                self.update(rec.recurring_id, **update_fields)

                # record success history
                self._record_history(
                    self.user["user_id"],
                    recurring_id=rec.recurring_id,
                    run_date=datetime.now(),
                    amount_used=amount_to_use,
                    status="generated",
                    override_used=override_used,
                    posted_transaction_id=new_tx_id,
                    message="Auto-generated by recurring runner."
                )

            except Exception as exc:
                # Attempt to write failed history and update status
                try:
                    rec_id = row.get("recurring_id") if isinstance(row, dict) else None
                    self._record_history(
                        self.user["user_id"],
                        recurring_id=rec_id,
                        run_date=datetime.now(),
                        amount_used=row.get("amount") if isinstance(row, dict) else 0,
                        status="failed",
                        override_used=False,
                        posted_transaction_id=None,
                        message=str(exc)
                    )
                except Exception:
                    pass

                # update recurring last_run_status to failed if possible
                try:
                    if isinstance(row, dict) and row.get("recurring_id"):
                        self.update(row.get("recurring_id"), last_run_status= "failed")
                except Exception:
                    pass

        return created_ids

    def preview_next_run(self, recurring_id: int) -> Dict[str, Any]:
        """
        Preview the next scheduled execution of a recurring transaction without
        actually creating a transaction or updating logs.

        Returns details such as:
        - recurring info
        - computed next run date
        - expected amount
        """

        owner_id = self.user["user_id"]

        # 1️⃣ Fetch recurring transaction
        sql = """
            SELECT recurring_id, owner_id, name, frequency, amount, last_run, next_due, last_run_status
            FROM recurring_transactions
            WHERE recurring_id = %s AND owner_id = %s
            LIMIT 1
        """
        row = self._execute(sql, (recurring_id, owner_id), fetchone=True)

        if not row:
            raise ValueError("Recurring transaction not found or access denied.")

        # Extract fields

        freq = row["frequency"]
        last = row["last_run"]  # can be NULL
        amount = row["amount"]

        # 2️⃣ Compute next run date

        last = None if not last else last


        # 3️⃣ Return preview
        return {
            "recurring_id": row["recurring_id"],
            "name": row["name"],
            "frequency": freq,
            "amount": amount,
            "last_run": last,
            "next_due": row["next_due"],
            "preview_status": row["last_run_status"],
        }




    def _add_months(self, src: datetime, months: int) -> datetime:
        """
        Add `months` to `src`, capping the day to the end-of-month when needed,
        and preserve time-of-day. Negative months behave as no-op here.
        """
        if months <= 0:
            return src

        # total months zero-based
        total = src.month - 1 + months
        year = src.year + total // 12
        month = total % 12 + 1

        # compute next month/year to get last day of 'month' safely
        if month == 12:
            next_month = 1
            next_month_year = year + 1
        else:
            next_month = month + 1
            next_month_year = year

        last_day_of_month = (datetime(next_month_year, next_month, 1) - timedelta(days=1)).day
        day = min(src.day, last_day_of_month)

        return datetime(year, month, day, src.hour, src.minute, src.second, src.microsecond)


    def _calculate_next_due(self, frequency: str, interval: int, last_due: datetime) -> datetime:
            if frequency == "daily":
                return last_due + timedelta(days=interval)
            if frequency == "weekly":
                return last_due + timedelta(weeks=interval)
            if frequency == "monthly":
                return self._add_months(last_due, interval)
            if frequency == "yearly":
                return self._add_months(last_due, 12 * interval)

            raise RecurringValidationError(f"Invalid frequency: {frequency}")            

