# features/balance.py
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, date
from decimal import Decimal
import mysql.connector
import json

# Import your existing models
from models.account_model import AccountModel, AccountNotFoundError, AccountValidationError


# ==========================
# Custom Exceptions
# ==========================
class BalanceError(Exception):
    """Base exception for balance operations"""
    pass


class InsufficientFundsError(BalanceError):
    """Raised when account has insufficient funds for operation"""
    pass


class BalanceValidationError(BalanceError):
    """Raised when balance validation fails"""
    pass


class BalanceDatabaseError(BalanceError):
    """Raised when database operations fail"""
    pass


# ==========================
# Balance Service
# ==========================
class BalanceService:
    """
    Centralized service for managing account balances.
    
    Responsibilities:
    - Compute updated balances after transactions
    - Generate real-time balance snapshots
    - Recalculate balances from scratch
    - Sync balance updates with TransactionModel
    - Enforce business rules
    - Maintain balance audit logs
    - Support balance projections
    
    Dependencies:
    - AccountModel (for account operations)
    - Database connection
    """
    
    def __init__(self, conn: mysql.connector.MySQLConnection, current_user: Dict[str, Any]):
        self.conn = conn
        self.user = current_user
        self.user_id = current_user.get("user_id")
        self.role = current_user.get("role")
        
        # Dependencies
        self.account_model = AccountModel(conn, current_user)

    # ================================================================
    # INTERNAL HELPERS
    # ================================================================
    
    def _execute(self, sql: str, params: Tuple[Any, ...], *, fetchone: bool = False, fetchall: bool = False):
        """Unified SQL executor with error wrapping"""
        if fetchone and fetchall:
            raise BalanceDatabaseError("Invalid flags: fetchone and fetchall cannot both be True")
        
        try:
            with self.conn.cursor(dictionary=True) as cursor:
                cursor.execute(sql, params)
                if fetchone:
                    result = cursor.fetchone()
                    return result
                if fetchall:
                    result = cursor.fetchall()
                    return result
                sql_upper = sql.strip().upper()
                if not sql_upper.startswith("SELECT"):
                    self.conn.commit()
                self.conn.commit()
                if sql_upper.startswith(("UPDATE", "DELETE")):
                    return cursor.rowcount
                else:
                    return cursor.lastrowid
                
        except mysql.connector.Error as e:
            try:
                self.conn.rollback()
            except:
                pass
            raise BalanceDatabaseError(f"Balance DB Error: {str(e)}")
    
    def _validate_account_active(self, account_id: int) -> Dict[str, Any]:
        """Ensure account exists and is active"""
        try:
            account = self.account_model.get_account(account_id)
        except AccountNotFoundError:
            raise BalanceValidationError(f"Account {account_id} not found")
        
        if not account.get("is_active"):
            raise BalanceValidationError(f"Account {account_id} is not active")
        
        return account

    def _log_balance_change(self,
                           account_id: int,
                           transaction_id: Optional[int],
                           old_balance: float,
                           new_balance: float,
                           change_amount: float, action: str, source= Optional[str],
                           notes: Optional[str] = None):
        """
        Log balance changes for audit trail.
        Uses AccountModel's audit logging system.
        """
        self.account_model.audit_logs(
            account_id=account_id,
            action=action,
            source= source,
            transaction_id=transaction_id,
            old_balance=old_balance,
            new_balance=new_balance,
            new_values={
                "change_amount": change_amount,
                "notes": notes
            }
        )
    
    def _check_sufficient_funds(self, account_id: int, amount: float, allow_overdraft: bool = False):
        """Check if account has sufficient funds"""
        account = self._validate_account_active(account_id)
        current_balance = float(account["balance"])
        
        if not allow_overdraft and current_balance < amount:
            raise InsufficientFundsError(
                f"Insufficient funds in account {account_id}...You are Broke :( "
                f"Required: {amount}, Available: {current_balance}"
            )
        
    # ================================================================
    # TRANSACTION TYPE HANDLERS
    # ================================================================
    
    def _apply_credit(self, account_id: int, amount: float, transaction_id: int, source: str) -> Dict[str, Any]:
        """Apply inflow to account balance"""
        account = self._validate_account_active(account_id)
        old_balance = float(account["balance"])
        new_balance = old_balance + amount
        
        # Update account balance
        self.account_model.update_account(account_id, source=source, balance=new_balance)
        
        # Log the change
        self._log_balance_change(
            account_id=account_id,
            transaction_id=transaction_id,
            old_balance=old_balance,
            new_balance=new_balance,
            change_amount=amount,
            action="CREDIT",
            source=source
        )
        return {
            "account_id": account_id,
            "old_balance": old_balance,
            "new_balance": new_balance,
            "change": amount,
            "changed_by_transaction": transaction_id
        }
    
    def _apply_debit(self, account_id: int, amount: float, transaction_id: int, source: str,
                      allow_overdraft: bool = False) -> Dict[str, Any]:
        """Apply outflow to account balance"""
        # Check sufficient funds
        self._check_sufficient_funds(account_id, amount, allow_overdraft)
      
        account = self._validate_account_active(account_id)
        old_balance = float(account["balance"])
        new_balance = old_balance - amount
        
        # Update account balance
        self.account_model.update_account(account_id, source=source, balance=new_balance)
        
        # Log the change
        self._log_balance_change(
            account_id=account_id,
            transaction_id=transaction_id,
            old_balance=old_balance,
            new_balance=new_balance,
            change_amount=-amount,
            action="DEBIT",
            source=source
        )
        
        return {
            "account_id": account_id,
            "old_balance": old_balance,
            "new_balance": new_balance,
            "change": -amount,
            "changed_by_transaction": transaction_id
        }
    
    def _apply_transfer(self, source_account_id: int, dest_account_id: int, 
                       amount: float, transaction_id: int, source: str,
                       allow_overdraft: bool = False) -> Dict[str, Any]:
        """Apply transfer transaction between two accounts"""
        # Validate not same account
        if source_account_id == dest_account_id:
            raise BalanceValidationError("Cannot transfer to the same account")
        
        
        # Check sufficient funds in source
        self._check_sufficient_funds(source_account_id, amount, allow_overdraft)
        
        # Get both accounts
        source_account = self._validate_account_active(source_account_id)
        dest_account = self._validate_account_active(dest_account_id)
        
        # Calculate new balances
        source_old = float(source_account.get("balance"))
        source_new = source_old - amount
        
        dest_old = float(dest_account.get("balance"))
        dest_new = dest_old + amount
        
        # Update both accounts
        self.account_model.update_account(source_account_id, source=source, balance=source_new)
        self.account_model.update_account(dest_account_id, source=source, balance=dest_new)
        
        # Log both changes
        self._log_balance_change(
            account_id=source_account_id,
            transaction_id=transaction_id,
            old_balance=source_old,
            new_balance=source_new,
            change_amount=-amount,
            action="TRANSFER_OUT",
            source = source
        )
        
        self._log_balance_change(
            account_id=dest_account_id,
            transaction_id=transaction_id,
            old_balance=dest_old,
            new_balance=dest_new,
            change_amount=amount,
            action="TRANSFER_IN",
            source=source
        )
        
        return {
            "source": {
                "account_id": source_account_id,
                "old_balance": source_old,
                "new_balance": source_new,
                "change": -amount
            },
            "destination": {
                "account_id": dest_account_id,
                "old_balance": dest_old,
                "new_balance": dest_new,
                "change": amount
            }
        }
    
    def _reverse_transaction(self, transaction_id: int, source:str, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Reverse a transaction's balance effects"""
        trans_type = transaction_data.get("transaction_type")
        amount = float(transaction_data["amount"])
        account_id = transaction_data["account_id"]
        credited_trans_types = {"income", "debt_borrowed"}
        debited_trans_types = {"debt_repaid", "expense"}
        transfer_types = {"transfer", "investment_deposit", "investment_withdraw"}
        if trans_type in credited_trans_types:
            # Reverse credit = subtract from balance
            return self._apply_debit(account_id, amount, transaction_id, source=source, allow_overdraft=True)
        
        elif trans_type in debited_trans_types:
            # Reverse debit = add to balance
            return self._apply_credit(account_id, amount, transaction_id, source=source)
        
        elif trans_type in transfer_types:
            # Reverse transfer = swap source and destination
            source_id = transaction_data["source_account_id"]
            dest_id = transaction_data["destination_account_id"]
            return self._apply_transfer(dest_id, source_id, amount, transaction_id, source=source, allow_overdraft=True)
        
        else:
            raise BalanceValidationError(f"Unknown transaction type: {trans_type}")
    
    # ================================================================
    # PUBLIC API - TRANSACTION OPERATIONS
    # ================================================================
    
    def apply_transaction_change(self,
                                 transaction_id: int,
                                 transaction_type: str,
                                 amount: float,
                                 account_id: Optional[int] = None,
                                 source_account_id: Optional[int] = None,
                                 destination_account_id: Optional[int] = None,
                                 allow_overdraft: bool = False) -> Dict[str, Any]:
        """
        Apply a transaction's balance effects.
        
        This is the main entry point called by TransactionModel.
        
        Args:
            transaction_id: ID of the transaction
            transaction_type: 'income', 'expense', or 'transfer' or 'debt_borrowed' or 'debt_repaid' or 'investment_deposit' or 'investment_withdraw'
            amount: Transaction amount
            account_id: Account for income/expense
            source_account_id: Source account for transfer
            destination_account_id: Destination account for transfer
            allow_overdraft: Allow negative balance
        
        Returns:
            Dict with balance change details
        """
        if transaction_type in {"income", "debt_borrowed"}:
            if not account_id:
                raise BalanceValidationError("account_id required for income")
            return self._apply_credit(account_id, amount, transaction_id, source=transaction_type)
        
        elif transaction_type in {"expense", "debt_repaid"}:
            if not account_id:
                raise BalanceValidationError("account_id required for expense")
            return self._apply_debit(account_id, amount, transaction_id, source=transaction_type, allow_overdraft=allow_overdraft)
        
        elif transaction_type in  {"transfer", "investment_deposit", "investment_withdraw"}:
            if not source_account_id or not destination_account_id:
                raise BalanceValidationError("source_account_id and destination_account_id required for transfer")
            return self._apply_transfer(source_account_id, destination_account_id, amount, 
                                       transaction_id, source=transaction_type, allow_overdraft=allow_overdraft)
        
        else:
            raise BalanceValidationError(f"Unknown transaction type: {transaction_type}")
    
    def reverse_transaction_change(self, transaction_id: int, source: str, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reverse a transaction's balance effects.
        
        Used when deleting or updating transactions.
        
        Args:
            transaction_id: ID of the transaction
            transaction_data: Original transaction data
        
        Returns:
            Dict with reversal details
        """
        return self._reverse_transaction(transaction_id, source, transaction_data)
    
    # ================================================================
    # PUBLIC API - BALANCE QUERIES
    # ================================================================
    
    def get_account_balance(self, account_id: int) -> Dict[str, Any]:
        """Get current balance for a specific account"""
        account = self.account_model.get_account(account_id, global_view=False)
        
        return {
            "account_id": account_id,
            "account_name": account.get("name"),
            "account_type": account.get("account_type"),
            "current_balance": float(account.get("balance")),
            "opening_balance": float(account.get("opening_balance")),
            "is_active": account.get("is_active"),
            "owner": account.get("owned_by_username")
        }
    
    def get_all_balances(self,*, include_deleted: bool = False, global_view: bool = False) -> List[Dict[str, Any]]:
        """Get balances for all user's accounts"""
        accounts_result = self.account_model.list_account(
            include_deleted=include_deleted,
            global_view=global_view
        )
        
        balances = []
        for account in accounts_result.get("accounts", []):
            balances.append({
                "account_id": account["account_id"],
                "account_name": account["name"],
                "account_type": account["account_type"],
                "current_balance": float(account["balance"]),
                "opening_balance": float(account["opening_balance"]),
                "is_active": account["is_active"],
                "is_deleted": account["is_deleted"]
            })
        
        return balances
    
    def get_net_worth(self) -> Dict[str, Any]:
        """Calculate total net worth across all accounts"""
        balances = self.get_all_balances(include_deleted=False)
        
        total = sum(b["current_balance"] for b in balances if b["is_active"])
        
        # Break down by account type
        by_type = {}
        for balance in balances:
            if not balance["is_active"]:
                continue
            
            acc_type = balance["account_type"]
            if acc_type not in by_type:
                by_type[acc_type] = 0
            by_type[acc_type] += balance["current_balance"]
        
        return {
            "user_id": self.user_id,
            "total_net_worth": total,
            "active_accounts": len([b for b in balances if b["is_active"]]),
            "breakdown_by_type": by_type,
            "timestamp": datetime.now().isoformat()
        }

    # ================================================================
    # PUBLIC API - BALANCE REBUILDING
    # ================================================================
    
    def rebuild_account_balance(self, account_id: int) -> Dict[str, Any]:
        """
        Recalculate account balance from scratch by summing all transactions.
        
        Useful when:
        - Balance seems incorrect
        - After importing historical data
        - After bulk transaction operations
        """
        account = self._validate_account_active(account_id)
        old_balance = float(account.get("balance", 0))
        opening_balance = float(account.get("opening_balance", 0))
        
        # Query all transactions for this account
        # TODO:  based on your TransactionModel's query method
        sql = """
            SELECT transaction_id, transaction_type, amount, account_id,
                   source_account_id, destination_account_id
            FROM transactions
            WHERE (account_id = %s OR source_account_id = %s OR destination_account_id = %s)
              AND is_deleted = 0 AND user_id = %s
            ORDER BY transaction_date ASC, transaction_id ASC
        """
        
        transactions = self._execute(sql, (account_id, account_id, account_id, self.user_id), fetchall=True)
        
        # Start with opening balance
        calculated_balance = opening_balance
        
        # Apply each transaction
        for tx in transactions:
            trans_type = tx["transaction_type"]
            amount = float(tx["amount"])
            
            if trans_type in ("income", "debt_borrowed") and tx["account_id"] == account_id:
                calculated_balance += amount
            
            elif trans_type in ("expense", "debt_repaid") and tx["account_id"] == account_id:
                calculated_balance -= amount
        
            elif trans_type in ("transfer", "investment_deposit", "investment_withdraw"):
                if tx["source_account_id"] == account_id:
                    calculated_balance -= amount
                elif tx["destination_account_id"] == account_id:
                    calculated_balance += amount
        
        # Update account with calculated balance
        self.account_model.update_account(account_id, source="BALANCE_REBUILD", balance=calculated_balance)
        
        # Log the rebuild
        self._log_balance_change(
            account_id=account_id,
            transaction_id=None,
            old_balance=old_balance,
            new_balance=calculated_balance,
            change_amount=calculated_balance - old_balance,
            action="balance_rebuild",
            notes=f"Rebuilt from {len(transactions)} transactions"
        )
        
        return {
            "account_id": account_id,
            "old_balance": old_balance,
            "new_balance": calculated_balance,
            "difference": calculated_balance - old_balance,
            "transactions_processed": len(transactions)
        }
    
    def rebuild_all_balances(self) -> Dict[str, Any]:
        """Rebuild balances for all user's accounts"""
        all_accounts = self.account_model.list_account(
            include_deleted=False, global_view=False
        )

        results = []
        for account in all_accounts.get("accounts", []):
            if account["is_active"]:
                try:
                    result = self.rebuild_account_balance(account["account_id"])
                    results.append(result)
                except Exception as e:
                    results.append({
                        "account_id": account["account_id"],
                        "error": str(e)
                    })

        return {
            "user_id": self.user_id,
            "accounts_rebuilt": len(results),
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
    
    # ================================================================
    # CRON-STYLE RUNNER (Optional)
    # ================================================================
    
    def run_balance_health_check(self) -> Dict[str, Any]:
        """
        Run periodic health check on all balances.
        
        Can be called by cron/scheduler to:
        - Detect anomalies
        - Flag negative balances
        - Identify inactive accounts with transactions
        """
        results = {
            "user_id": self.user_id,
            "timestamp": datetime.now().isoformat(),
            "checks": []
        }
        
        balances = self.get_all_balances(include_deleted=False)
        
        for balance in balances:
            check = {
                "account_id": balance["account_id"],
                "account_name": balance["account_name"],
                "issues": []
            }
            
            # Check for negative balance
            if balance["current_balance"] < 0:
                check["issues"].append(f"Negative balance: {balance['current_balance']}")
            
            # Check for large deviation from opening
            opening = balance["opening_balance"]
            current = balance["current_balance"]
            if opening != 0:
                deviation = abs((current - opening) / opening) * 100
                if deviation > 500:  # More than 500% change
                    check["issues"].append(f"Large deviation: {deviation:.2f}%")
            
            if check["issues"]:
                results["checks"].append(check)
        
        results["total_issues"] = len(results["checks"])
        
        return results