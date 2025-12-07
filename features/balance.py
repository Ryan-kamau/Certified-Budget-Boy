# features/balance.py
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, date
from decimal import Decimal
import mysql.connector
import json

# Import your existing models
from models.account_model import AccountModel, AccountNotFoundError, AccountValidationError
from models.transactions_model import TransactionModel 


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
    - TransactionModel (for transaction queries)
    - Database connection
    """
    
    def __init__(self, conn: mysql.connector.MySQLConnection, current_user: Dict[str, Any]):
        self.conn = conn
        self.user = current_user
        self.user_id = current_user.get("user_id")
        self.role = current_user.get("role")
        
        # Dependencies
        self.account_model = AccountModel(conn, current_user)
        self.transaction_model = TransactionModel(conn, current_user)

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
                    self.conn.commit()
                    return result
                if fetchall:
                    result = cursor.fetchall()
                    self.conn.commit()
                    return result
                
                self.conn.commit()
                return cursor.lastrowid if not sql.strip().upper().startswith("UPDATE") else cursor.rowcount
                
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
                           change_amount: float,
                           action: str,
                           notes: Optional[str] = None):
        """
        Log balance changes for audit trail.
        Uses AccountModel's audit logging system.
        """
        self.account_model._audit_logs(
            account_id=account_id,
            action=action,
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
        current_balance = float(account.get("balance"))
        
        if not allow_overdraft and current_balance < amount:
            raise InsufficientFundsError(
                f"Insufficient funds in account {account_id}...You are Broke :( "
                f"Required: {amount}, Available: {current_balance}"
            )
        
    # ================================================================
    # TRANSACTION TYPE HANDLERS
    # ================================================================
    
    def _apply_income(self, account_id: int, amount: float, transaction_id: int) -> Dict[str, Any]:
        """Apply income transaction to account balance"""
        account = self._validate_account_active(account_id)
        old_balance = float(account.get("balance"))
        new_balance = old_balance + amount
        
        # Update account balance
        self.account_model.update_account(account_id, balance=new_balance)
        
        # Log the change
        self._log_balance_change(
            account_id=account_id,
            transaction_id=transaction_id,
            old_balance=old_balance,
            new_balance=new_balance,
            change_amount=amount,
            action="deposit"
        )
        
        return {
            "account_id": account_id,
            "old_balance": old_balance,
            "new_balance": new_balance,
            "change": amount,
            "changed_by_transaction": transaction_id
        }
    
    def _apply_expense(self, account_id: int, amount: float, transaction_id: int, 
                      allow_overdraft: bool = False) -> Dict[str, Any]:
        """Apply expense transaction to account balance"""
        # Check sufficient funds
        self._check_sufficient_funds(account_id, amount, allow_overdraft)
        
        account = self._validate_account_active(account_id)
        old_balance = float(account.get("balance"))
        new_balance = old_balance - amount
        
        # Update account balance
        self.account_model.update_account(account_id, balance=new_balance)
        
        # Log the change
        self._log_balance_change(
            account_id=account_id,
            transaction_id=transaction_id,
            old_balance=old_balance,
            new_balance=new_balance,
            change_amount=-amount,
            action="withdraw"
        )
        
        return {
            "account_id": account_id,
            "old_balance": old_balance,
            "new_balance": new_balance,
            "change": -amount,
            "changed_by_transaction": transaction_id
        }
    
    def _apply_transfer(self, source_account_id: int, dest_account_id: int, 
                       amount: float, transaction_id: int,
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
        self.account_model.update_account(source_account_id, balance=source_new)
        self.account_model.update_account(dest_account_id, balance=dest_new)
        
        # Log both changes
        self._log_balance_change(
            account_id=source_account_id,
            transaction_id=transaction_id,
            old_balance=source_old,
            new_balance=source_new,
            change_amount=-amount,
            action="transfer"
        )
        
        self._log_balance_change(
            account_id=dest_account_id,
            transaction_id=transaction_id,
            old_balance=dest_old,
            new_balance=dest_new,
            change_amount=amount,
            action="transfer"
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
    
    def _reverse_transaction(self, transaction_id: int, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Reverse a transaction's balance effects"""
        trans_type = transaction_data.get("transaction_type")
        amount = float(transaction_data.get("amount"))
        account_id = transaction_data.get("account_id")
        
        if trans_type == "income":
            # Reverse income = subtract from balance
            return self._apply_expense(account_id, amount, transaction_id, allow_overdraft=True)
        
        elif trans_type == "expense":
            # Reverse expense = add to balance
            return self._apply_income(account_id, amount, transaction_id)
        
        elif trans_type == "transfer":
            # Reverse transfer = swap source and destination
            source_id = transaction_data.get("source_account_id")
            dest_id = transaction_data.get("destination_account_id")
            return self._apply_transfer(dest_id, source_id, amount, transaction_id, allow_overdraft=True)
        
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
            transaction_type: 'income', 'expense', or 'transfer'
            amount: Transaction amount
            account_id: Account for income/expense
            source_account_id: Source account for transfer
            destination_account_id: Destination account for transfer
            allow_overdraft: Allow negative balance
        
        Returns:
            Dict with balance change details
        """
        if transaction_type == "income":
            if not account_id:
                raise BalanceValidationError("account_id required for income")
            return self._apply_income(account_id, amount, transaction_id)
        
        elif transaction_type == "expense":
            if not account_id:
                raise BalanceValidationError("account_id required for expense")
            return self._apply_expense(account_id, amount, transaction_id, allow_overdraft)
        
        elif transaction_type == "transfer":
            if not source_account_id or not destination_account_id:
                raise BalanceValidationError("source_account_id and destination_account_id required for transfer")
            return self._apply_transfer(source_account_id, destination_account_id, amount, 
                                       transaction_id, allow_overdraft)
        
        else:
            raise BalanceValidationError(f"Unknown transaction type: {transaction_type}")
    