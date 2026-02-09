"""
Search and Filter Service for Budget Tracker

This module provides comprehensive search and filtering capabilities for:
- Transactions (by amount, date, category, account, tags, payment method, etc.)
- Categories (by name, parent, hierarchy)
- Accounts (by type, balance range, status)
- Recurring transactions (by frequency, status, next due date)

Features:
- Multi-criteria search
- Complex filtering with AND/OR logic
- Full-text search
- Tag-based filtering
- Date range presets
- Amount range filtering
- Sorting and pagination
- Export-ready results
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple, Union
from datetime import datetime, date
from decimal import Decimal
from dataclasses import dataclass
import mysql.connector

# Import your existing models
from models.transactions_model import TransactionModel, TransactionError
from models.category_model import CategoryModel, CategoryError
from models.account_model import AccountModel, AccountError
from features.recurring import RecurringModel, RecurringError

# Import utilities
from core.utils import (
    DateRangeValidator,
    AmountRangeValidator,
    QueryBuilder,
    InputSanitizer,
    ValidationPatterns,
    PaginationHelper,
    FormatHelper
)

@dataclass
class TextSearchFilter:
    search_text: Optional[str] = None
    search_fields: Optional[List[str]] = None

@dataclass
class AmountFilter:
    min_amount: Optional[Union[str, float, Decimal]] = None
    max_amount: Optional[Union[str, float, Decimal]] = None
    exact_amount: Optional[Union[str, float, Decimal]] = None

@dataclass
class DateFilter:
    start_date: Optional[Union[str, date]] = None
    end_date: Optional[Union[str, date]] = None
    date_preset: Optional[str] = None

@dataclass
class CategoryFilter:
    category_ids: Optional[List[int]] = None
    category_names: Optional[List[str]] = None
    include_subcategories: bool = False

@dataclass
class AccountFilter:
    account_ids: Optional[List[int]] = None
    account_types: Optional[List[str]] = None

@dataclass
class TransactionTypeFilter:
    transaction_types: Optional[List[str]] = None
    payment_methods: Optional[List[str]] = None

@dataclass
class StatusFilter:
    include_deleted: bool = False
    global_view: bool = False

@dataclass
class SortOptions:
    sort_by: str = "transaction_date"
    sort_order: str = "DESC"

@dataclass
class Pagination:
    page: int = 1
    page_size: int = 50
    
@dataclass
class ParentFilter:
    has_parent: Optional[bool] = None
    parent_id: Optional[int] = None

# ================================================================
# Custom Exceptions
# ================================================================
class SearchError(Exception):
    """Base exception for search operations"""
    pass


class SearchValidationError(SearchError):
    """Raised when search parameters are invalid"""
    pass


# ================================================================
# Main Search Service
# ================================================================
class SearchService:
    """
    Centralized search and filter service.
    
    This service provides a unified interface for searching across
    all budget tracker entities with advanced filtering capabilities.
    """
    
    def __init__(self, conn: mysql.connector.MySQLConnection, current_user: Dict[str, Any]):
        self.conn = conn
        self.user = current_user
        self.user_id = current_user.get("user_id")
        self.role = current_user.get("role")
        
        # Initialize models
        self.transaction_model = TransactionModel(conn, current_user)
        self.category_model = CategoryModel(conn, current_user)
        self.account_model = AccountModel(conn, current_user)
        self.recurring_model = RecurringModel(conn, current_user)
    
    # ================================================================
    # TRANSACTION SEARCH
    # ================================================================
    
    def search_transactions(
        self,
        # Text search
        search_text: Optional[str] = None,
        search_fields: Optional[List[str]] = None,  # ['title', 'description']
        
        # Amount filters
        min_amount: Optional[Union[str, float, Decimal]] = None,
        max_amount: Optional[Union[str, float, Decimal]] = None,
        exact_amount: Optional[Union[str, float, Decimal]] = None,
        
        # Date filters
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        date_preset: Optional[str] = None,  # 'this_month', 'last_30_days', etc.
        
        # Category filters
        category_ids: Optional[List[int]] = None,
        category_names: Optional[List[str]] = None,
        include_subcategories: bool = False,
        
        # Account filters
        account_ids: Optional[List[int]] = None,
        account_types: Optional[List[str]] = None,
        
        # Transaction type filters
        transaction_types: Optional[List[str]] = None,
        payment_methods: Optional[List[str]] = None,
        
        # Tag filters (if you implement tags)
        tags: Optional[List[str]] = None,
        
        # Status filters
        include_deleted: bool = False,
        global_view: bool = False,
        
        # Sorting
        sort_by: str = "transaction_date",
        sort_order: str = "DESC",
        
        # Pagination
        page: int = 1,
        page_size: int = 50,
        
        # Additional filters
        has_parent: Optional[bool] = None,  # True = only children, False = only parents, None = all
        parent_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Advanced transaction search with multiple filter criteria.
        
        Args:
            search_text: Text to search in title/description
            search_fields: Fields to search in (default: ['title', 'description'])
            min_amount: Minimum transaction amount
            max_amount: Maximum transaction amount
            exact_amount: Exact transaction amount
            start_date: Start of date range
            end_date: End of date range
            date_preset: Predefined date range (overrides start/end if provided)
            category_ids: List of category IDs to filter by
            category_names: List of category names to filter by
            include_subcategories: Include transactions in subcategories
            account_ids: List of account IDs
            account_types: List of account types
            transaction_types: List of transaction types
            payment_methods: List of payment methods
            tags: List of tags to filter by
            include_deleted: Include soft-deleted transactions
            global_view: View global transactions (admin only)
            sort_by: Column to sort by
            sort_order: 'ASC' or 'DESC'
            page: Page number (1-indexed)
            page_size: Items per page
            has_parent: Filter by parent status
            parent_id: Specific parent transaction ID
            
        Returns:
            Dict with:
                - results: List of matching transactions
                - pagination: Pagination metadata
                - filters_applied: Summary of active filters
                - summary: Aggregate statistics
                
        Raises:
            SearchValidationError: If search parameters are invalid
        """