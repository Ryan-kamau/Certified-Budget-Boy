# models/accounts_model.py
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import mysql.connector
import json


# ==========================
# Exceptions
# ==========================
class AccountError(Exception): pass
class AccountNotFoundError(AccountError): pass
class AccountValidationError(AccountError): pass
class AccountDataBaseError(AccountError):pass


# ==========================
# DataClass
# ==========================
@dataclass
class Accounts:
    account_id: int
    owner_id: int 
    name: str 
    account_type: str          
    description: Optional[str]
    balance: float 
    opening_balance: float
    is_global: int = 0
    is_active: int = 1
    is_deleted: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    db: Any = field(default=None, repr=False)


    def to_dict(self) -> Dict[str, Any]:
        """Convert dataclass to clean dict for API responses."""
        return asdict(self)
    
class AccountModel:
    def __init__(self, conn, current_user: Dict[str, Any]):
        self.conn = conn
        self.user = current_user

    # ==========================
    # Internal Helpers
    # ==========================
    def _execute(self, sql: str, params: Tuple[Any, ...], *, fetchone: bool = False, fetchall: bool = False):
        """Unified SQL executor with error wrapping"""
        # validate flags
        if fetchone and fetchall:
            raise AccountDataBaseError("Invalid flags: fetchone and fetchall cannot both be True")
        
        try:
            with self.conn.cursor(dictionary=True) as cursor:
                cursor.execute(sql, params)
                if fetchone:
                    result = cursor.fetchone()
                    if not sql.strip().upper().startswith("SELECT"):
                        self.conn.commit()
                    return result
                if fetchall:
                    result = cursor.fetchall()
                    if not sql.strip().upper().startswith("SELECT"):
                        self.conn.commit()
                    return result
                else:
                    if sql.strip().upper().startswith("UPDATE"):
                        self.conn.commit()
                        return cursor.rowcount
                    self.conn.commit()
                    return cursor.lastrowid
        except mysql.connector.Error as e:
            try:
                self.conn.rollback()
            except:
                pass
            raise AccountDataBaseError(f"MySQL Error: {str(e)}")
        
        
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
                raise AccountValidationError("Users can only view and control own data")
            
    def _audit_logs(self, account_id: int, action: str,
                    transaction_id: Optional[int] = None,
                    old_balance: Optional[int] = None, new_balance: Optional[int] = None,
                   old_values: Optional[Dict[str, Any]] = None,
                   new_values: Optional[Dict[str, Any]] = None,
                   changed_fields: Optional[List[str]] = None):
        """Insert into account_logs."""
        query = """
        INSERT INTO account_logs (account_id, owner_id, action, transaction_id, old_balance, new_balance,
                                  old_data, new_data, changed_fields)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        if new_values:
            for k in ("transaction_date","created_at","updated_at"):
                if k in new_values and new_values[k]:
                    new_values[k] = new_values[k].isoformat()

        old_json = json.dumps(old_values, default=str) if old_values else None
        new_json = json.dumps(new_values, default=str) if new_values else None
        changed_json = json.dumps(changed_fields, default=str) if changed_fields else None

        params = (account_id, self.user["user_id"], action, transaction_id, old_balance, new_balance, old_json, new_json, changed_json)
        self._execute(query, params)
    
    def _build_account(self, row: Dict[str, Any]) -> Accounts:
        # Convert DB row keys into appropriate types if needed
        return Accounts(**row)
    
    #public helper
    def audit_logs(self, accout_id: int,
            action: str,
            transaction_id: int,
            old_balance: float,
            new_balance: float,
            new_values: Dict[str, Any]):
        return self._audit_logs(account_id=accout_id, action=action, transaction_id=transaction_id,
                                old_balance=old_balance, new_balance=new_balance, new_values=new_values)
    
    
    #--------------------
    # CRUD OPERATIONS
    #--------------------
    def create(self, **data: Dict[str, Any]) -> Dict[str, Any]:
        required = ["name", "account_type", "balance", "opening_balance"]
        missing = [f for f in required if f not in data]

        if missing:
            raise AccountValidationError(f"Missing required fields: {missing}")
        
        sql = """
            INSERT INTO accounts
            (owner_id, is_global, name, description, account_type, balance,
             opening_balance)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """

        params = (
            self.user["user_id"],
            data.get("is_global", 0),
            data["name"],
            data.get("description"),
            data["account_type"],
            data["balance"],
            data["opening_balance"],
        )

        new_id = self._execute(sql, params)
        new_values = self.get_account(new_id)

        self._audit_logs(new_id, action="create", new_values=new_values)
        return {"success": True, "account_id": new_id}
    
    def get_account(self, account_id: int, * , include_deleted: bool = False, global_view: bool = False) -> Dict[str, Any]:
        filter_tenant = f"a.{self._tenant_filter(global_view)}"
        sql = f"""
            SELECT a.*, u1.username AS owned_by_username
            FROM accounts a
            LEFT JOIN users u1 ON a.owner_id = u1.user_id
            WHERE a.account_id = %s AND {filter_tenant}
        """
        params = [account_id]
        if not include_deleted:
            sql += " AND a.is_deleted = 0"
        if "%s" in filter_tenant:
            params.append(self.user["user_id"])

        # using dict param style for tenant filter
        row = self._execute(sql, tuple(params), fetchone=True)

        if not row:
            raise AccountNotFoundError("Account not found.")
        # filter row for dataclass
        model_fields = Accounts.__annotations__.keys()
        clean_row = {k: v for k, v in row.items() if k in model_fields}
 
        result = self._build_account(clean_row).to_dict()
        result["owned_by_username"] = row["owned_by_username"]
        return result
    
    def update_account(self, account_id: int, **updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update account fields."""
        if not updates:
            raise AccountValidationError("No fields provided for update.")
        
        dex = self.get_account(account_id)
        
        fields = ", ".join((f"{k}=%s" for k in updates.keys()))
        params = tuple(updates.values()) + (account_id, self.user["user_id"],)
        
        result = self._execute(
            f"UPDATE accounts SET {fields} WHERE account_id = %s AND owner_id = %s", params
        )
        print(result)
        if result == 0:
            raise AccountNotFoundError(f"Account {account_id} not found or unchanged.")
        
        self._audit_logs(account_id, action= "update", old_values=dex, new_values= updates, changed_fields= list(updates.keys()))
        updated = self.get_account(account_id)
        return {"success": True, "message": "Account updated successfully.", "update": updated}
    
    def list_account(
        self,
        account_type: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None, *,
        include_deleted: bool = False,
        global_view: bool = False
    ) -> Dict[str, Any]:
        """Filter account by user/account type with optional pagination."""
        filter_tenant = f"a.{self._tenant_filter(global_view=global_view)}"
        query = f"""
                SELECT a.*, u1.username AS owned_by_username
                FROM accounts a
                LEFT JOIN users u1 ON a.owner_id = u1.user_id
                WHERE {filter_tenant}
                """
        params = []
        if "%s" in filter_tenant:
            params.append(self.user["user_id"],) 

        if account_type:
            if account_type not in ['cash','bank','mobile_money','credit','savings','other']:
                raise AccountValidationError("Account Type Not Found ...Use: ['cash','bank','mobile_money','credit','savings','other'] ")
            
            query += " AND a.account_type = %s"
            params.append(account_type)

        if not include_deleted:
            query += " AND a.is_deleted = 0"


        query += " ORDER BY a.balance DESC"

        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        if offset is not None:
            query += " OFFSET %s"
            params.append(offset)

        rows = self._execute(query, tuple(params), fetchall=True)
        masuka = []
        for row in rows:
            clean_dict = {k:v for k, v in row.items() if k in Accounts.__annotations__.keys()}
            dm = self._build_account(clean_dict).to_dict()
            dm["owned_by_username"] = row.get("owned_by_username")
            masuka.append(dm)

        return {"success": True, "count": len(masuka), "accounts": masuka}

    def delete_account(self, account_id: int, soft: bool = True) -> Dict[str, Any]:
        """
        Delete a account.
        soft=True → marks as deleted (is_deleted = 1)
        soft=False → permanently deletes
        """
        dm = self.get_account(account_id, include_deleted=True)
        if not dm:
            raise AccountNotFoundError(f"Account {account_id} not found.")
        self._audit_logs(
                account_id=account_id,
                action="delete",
                old_values=dm,
            )
        user_id = self.user["user_id"]

        if soft:
            self._execute("UPDATE accounts SET is_deleted = 1 WHERE account_id = %s AND owner_id = %s", (account_id, user_id,))
        else:
            self._execute("DELETE FROM accounts WHERE account_id = %s AND owner_id = %s", (account_id, user_id,))

        
        return {
            "success": True,
            "message": f"Account {account_id} {'soft' if soft else 'hard'} deleted successfully.",
        }
    
    def restore_account(self, account_id: int) -> Dict[str, Any]:
        """Restore a soft-deleted account."""
        dm = self.get_account(account_id, include_deleted=True)
        if not dm:
            raise AccountNotFoundError(f"Account {account_id} not found.")
        self._audit_logs(
                account_id=account_id,
                action="update",
                old_values={"is_deleted": 1},
                new_values={"is_deleted": 0},
                changed_fields=["is_deleted"],
            )
        
        self._execute("UPDATE accounts SET is_deleted = 0 WHERE account_id = %s AND owner_id = %s", (account_id, self.user["user_id"]))
        return {"success": True, "message": f"Account {account_id} restored successfully."}
    
    def view_audit_logs(
        self,
        account_id: Optional[int] = None,
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
        filter_clause = f"a.{self._tenant_filter(global_view)}"

        # ------------------------------------
        # Base Query
        # ------------------------------------
        q = f"""
            SELECT 
                a.*,
                u.username AS performed_by
            FROM account_logs a
            LEFT JOIN users u ON a.owner_id = u.user_id
            WHERE {filter_clause}
        """
        params=[]
        # Bind user_id if needed
        if "%s" in filter_clause:
            params.append(self.user["user_id"])

        return self._execute(q, tuple(params), fetchall=True)