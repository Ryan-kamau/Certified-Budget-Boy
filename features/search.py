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

@dataclass
class TransactionSearchRequest:
    text: TextSearchFilter = TextSearchFilter()
    amount: AmountFilter = AmountFilter()
    date: DateFilter = DateFilter()
    category: CategoryFilter = CategoryFilter()
    account: AccountFilter = AccountFilter()
    tx_type: TransactionTypeFilter = TransactionTypeFilter()
    status: StatusFilter = StatusFilter()
    sort: SortOptions = SortOptions()
    pagination: Pagination = Pagination()
    parent: ParentFilter = ParentFilter()


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
        filters: TransactionSearchRequest
    ) -> Dict[str, Any]:
        """
        Advanced transaction search with multiple filter criteria.
        
        
        Args:
            filters: TransactionSearchRequest object containing all filter criteria
            Includes:
                - text: TextSearchFilter for full-text search
                - amount: AmountFilter for amount-based filtering
                - date: DateFilter for date-based filtering
                - category: CategoryFilter for category-based filtering
                - account: AccountFilter for account-based filtering
                - tx_type: TransactionTypeFilter for type and payment method filtering
                - status: StatusFilter for deleted and global view options
                - sort: SortOptions for sorting results
                - pagination: Pagination settings
                - parent: ParentFilter for hierarchical relationships
        Returns:
            Dict with:
                - results: List of matching transactions
                - pagination: Pagination metadata
                - filters_applied: Summary of active filters
                - summary: Aggregate statistics
                
        Raises:
            SearchError: If an error occurs during search execution
            SearchValidationError: If search parameters are invalid
        """
        try:
            # ========================================
            # 1. VALIDATE & NORMALIZE INPUTS
            # ========================================
            
            # Validate date range
            if filters.date and filters.date.date_preset:
                start_date, end_date = DateRangeValidator.get_preset_range(filters.date.date_preset)
            else:
                start_date, end_date = DateRangeValidator.validate_range(start_date, end_date)
            
            # Validate amount range
            if filters.amount and filters.amount.exact_amount is not None:
                exact_amt = AmountRangeValidator.parse_amount(filters.amount.exact_amount)
                min_amt, max_amt = exact_amt, exact_amt
            else:
                min_amt, max_amt = AmountRangeValidator.validate_range(filters.amount.min_amount, filters.amount.max_amount)

            # Validate transaction types
            if filters.tx_type and filters.tx_type.transaction_types:
                filters.tx_type.transaction_types = [
                    ValidationPatterns.validate_transaction_type(tt) 
                    for tt in filters.tx_type.transaction_types
                ]
            
            # Validate payment methods
            if filters.tx_type and filters.tx_type.payment_methods:
                filters.tx_type.payment_methods = [
                    ValidationPatterns.validate_payment_method(pm)
                    for pm in filters.tx_type.payment_methods
                ]
            
            # Validate sort order
            sort_order = ValidationPatterns.validate_sort_order(filters.sort.sort_order if filters.sort else None)
            
            # Sanitize search text
            search_text = InputSanitizer.sanitize_string(filters.text.search_text if filters.text else "", max_length=500)
            
            if not filters.text.search_fields:
                filters.text.search_fields = ['title', 'description']

            # ========================================
            # 2. BUILD BASE QUERY
            # ========================================
            
            base_query = """
                SELECT 
                    t.*,
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
                WHERE 1=1
            """
            
            builder = QueryBuilder(base_query)
            
            # ========================================
            # 3. ADD FILTERS
            # ========================================
            
            # Tenant filter
            tenant_filter = self._get_tenant_filter("t", filters.status.global_view)
            if tenant_filter:
                builder.add_condition(tenant_filter, self.user_id)
            
            # Text search
            if search_text:
                search_conditions = []
                for field in filters.text.search_fields:
                    search_conditions.append(f"t.{field} LIKE %s")
                
                search_clause = f"({' OR '.join(search_conditions)})"
                search_params = [f"%{search_text}%"] * len(filters.text.search_fields)
                
                builder.add_condition(search_clause, *search_params)
            
            # Amount filters
            builder.add_amount_range("t.amount", min_amt, max_amt)
            
            # Date filters
            builder.add_date_range("t.transaction_date", start_date, end_date)
            
            # Category filters
            if filters.category.category_ids:
                category_ids = filters.category.category_ids
                if filters.category.include_subcategories:
                    # Get all descendant category IDs
                    all_category_ids = self._get_category_hierarchy(category_ids)
                    builder.add_in_condition("t.category_id", all_category_ids)
                else:
                    builder.add_in_condition("t.category_id", category_ids)
            
            if filters.category.category_names:
                # Convert names to IDs
                cat_ids = self._get_category_ids_by_names(filters.category.category_names)
                if cat_ids:
                    builder.add_in_condition("t.category_id", cat_ids)
            
            # Account filters
            if filters.account.account_ids:
                account_ids = filters.account.account_ids
                # Match on any account field
                placeholders = ", ".join(["%s"] * len(account_ids))
                account_clause = f"(t.account_id IN ({placeholders}) OR t.source_account_id IN ({placeholders}) OR t.destination_account_id IN ({placeholders}))"                
                params = account_ids * 3
                builder.add_condition(account_clause, *params)
            
            if filters.account.account_types:
                account_ids = filters.account.account_ids or [] 
                # Join with accounts table for type filtering
                placeholders = ", ".join(["%s"] * len(filters.account.account_types))
                type_clause = f"""
                    (a.account_type IN ({placeholders}) OR sa.account_type IN ({placeholders}) OR da.account_type IN ({placeholders}))
                """
                params = filters.account.account_types * 3
                builder.add_condition(type_clause, *params)
            
            # Transaction type filters
            builder.add_in_condition("t.transaction_type", filters.tx_type.transaction_types)
            
            # Payment method filters
            builder.add_in_condition("t.payment_method", filters.payment_method.payment_methods)
            
            # Parent filters
            if filters.parent.has_parent is True:
                builder.add_condition("t.parent_transaction_id IS NOT NULL")
            elif filters.parent.has_parent is False:
                builder.add_condition("t.parent_transaction_id IS NULL")
            
            if filters.parent.parent_id is not None:
                builder.add_condition("t.parent_transaction_id = %s", filters.parent.parent_id)
            
            # ========================================
            # 4. GET TOTAL COUNT
            # ========================================
            
            count_query = f"SELECT COUNT(*) as total FROM ({builder.query}) AS count_subquery"
            count_result = self._execute(count_query, tuple(builder.params), fetchone=True)
            total_count = count_result['total'] if count_result else 0
            
            # ========================================
            # 5. ADD SORTING AND PAGINATION
            # ========================================
            
            # Sorting
            allowed_sort_fields = [
                'transaction_date', 'amount', 'title', 'created_at', 
                'updated_at', 'transaction_type', 'category_name'
            ]
            
            if sort_by not in allowed_sort_fields:
                sort_by = 'transaction_date'
            
            builder.add_order_by(f"{sort_by} {sort_order}")
            
            # Pagination
            pagination = PaginationHelper.calculate_pagination(total_count, page, page_size)
            builder.add_limit_offset(pagination['page_size'], pagination['offset'])
            
            # ========================================
            # 6. EXECUTE QUERY
            # ========================================
            
            query, params = builder.build()
            results = self._execute(query, tuple(params), fetchall=True)
            
            # ========================================
            # 7. CALCULATE SUMMARY STATISTICS
            # ========================================
            
            summary = self._calculate_transaction_summary(results)
            
            # ========================================
            # 8. BUILD RESPONSE
            # ========================================
            
            filters_applied = {
                'search_text': search_text,
                'date_range': FormatHelper.format_date_range(start_date, end_date),
                'amount_range': f"{min_amt or 'Any'} - {max_amt or 'Any'}",
                'categories': category_names or category_ids,
                'accounts': account_ids,
                'transaction_types': transaction_types,
                'payment_methods': payment_methods,
                'include_deleted': include_deleted
            }
            
            return {
                'success': True,
                'results': results,
                'count': len(results),
                'pagination': pagination,
                'filters_applied': filters_applied,
                'summary': summary
            }
            
        except (ValueError, TransactionError) as e:
            raise SearchValidationError(f"Search validation failed: {str(e)}")
        except Exception as e:
            raise SearchError(f"Search failed: {str(e)}")
    # Text search
            if search_text:
                search_conditions = []
                for field in search_fields:
                    search_conditions.append(f"t.{field} LIKE %s")
                
                search_clause = f"({' OR '.join(search_conditions)})"
                search_params = [f"%{search_text}%"] * len(search_fields)
                
                builder.add_condition(search_clause, *search_params)
            
            # Amount filters
            builder.add_amount_range("t.amount", min_amt, max_amt)
            
            # Date filters
            builder.add_date_range("t.transaction_date", start_date, end_date)
            
            # Category filters
            if category_ids:
                if include_subcategories:
                    # Get all descendant category IDs
                    all_category_ids = self._get_category_hierarchy(category_ids)
                    builder.add_in_condition("t.category_id", all_category_ids)
                else:
                    builder.add_in_condition("t.category_id", category_ids)
            
            if category_names:
                # Convert names to IDs
                cat_ids = self._get_category_ids_by_names(category_names)
                if cat_ids:
                    builder.add_in_condition("t.category_id", cat_ids)
            
            # Account filters
            if account_ids:
                # Match on any account field
                account_clause = "(t.account_id IN (%s) OR t.source_account_id IN (%s) OR t.destination_account_id IN (%s))"
                placeholders = ", ".join(["%s"] * len(account_ids))
                account_clause = account_clause.replace("%s", placeholders, 1)
                account_clause = account_clause.replace("%s", placeholders, 1)
                account_clause = account_clause.replace("%s", placeholders, 1)
                
                params = account_ids * 3
                builder.add_condition(account_clause, *params)
            
            if account_types:
                # Join with accounts table for type filtering
                type_clause = """
                    (a.account_type IN (%s) OR sa.account_type IN (%s) OR da.account_type IN (%s))
                """
                placeholders = ", ".join(["%s"] * len(account_types))
                type_clause = type_clause.replace("%s", placeholders, 1)
                type_clause = type_clause.replace("%s", placeholders, 1)
                type_clause = type_clause.replace("%s", placeholders, 1)
                
                params = account_types * 3
                builder.add_condition(type_clause, *params)
            
            # Transaction type filters
            builder.add_in_condition("t.transaction_type", transaction_types)
            
            # Payment method filters
            builder.add_in_condition("t.payment_method", payment_methods)
            
            # Parent filters
            if has_parent is True:
                builder.add_condition("t.parent_transaction_id IS NOT NULL")
            elif has_parent is False:
                builder.add_condition("t.parent_transaction_id IS NULL")
            
            if parent_id is not None:
                builder.add_condition("t.parent_transaction_id = %s", parent_id)
            
            # ========================================
            # 4. GET TOTAL COUNT
            # ========================================
            
            count_query = f"SELECT COUNT(*) as total FROM ({builder.query}) AS count_subquery"
            count_result = self._execute(count_query, tuple(builder.params), fetchone=True)
            total_count = count_result['total'] if count_result else 0
            
            # ========================================
            # 5. ADD SORTING AND PAGINATION
            # ========================================
            
            # Sorting
            allowed_sort_fields = [
                'transaction_date', 'amount', 'title', 'created_at', 
                'updated_at', 'transaction_type', 'category_name'
            ]
            
            if sort_by not in allowed_sort_fields:
                sort_by = 'transaction_date'
            
            builder.add_order_by(f"{sort_by} {sort_order}")
            
            # Pagination
            pagination = PaginationHelper.calculate_pagination(total_count, page, page_size)
            builder.add_limit_offset(pagination['page_size'], pagination['offset'])
            
            # ========================================
            # 6. EXECUTE QUERY
            # ========================================
            
            query, params = builder.build()
            results = self._execute(query, tuple(params), fetchall=True)
            
            # ========================================
            # 7. CALCULATE SUMMARY STATISTICS
            # ========================================
            
            summary = self._calculate_transaction_summary(results)
            
            # ========================================
            # 8. BUILD RESPONSE
            # ========================================
            
            filters_applied = {
                'search_text': search_text,
                'date_range': FormatHelper.format_date_range(start_date, end_date),
                'amount_range': f"{min_amt or 'Any'} - {max_amt or 'Any'}",
                'categories': category_names or category_ids,
                'accounts': account_ids,
                'transaction_types': transaction_types,
                'payment_methods': payment_methods,
                'include_deleted': include_deleted
            }
            
            return {
                'success': True,
                'results': results,
                'count': len(results),
                'pagination': pagination,
                'filters_applied': filters_applied,
                'summary': summary
            }
            
        except (ValueError, TransactionError) as e:
            raise SearchValidationError(f"Search validation failed: {str(e)}")
        except Exception as e:
            raise SearchError(f"Search failed: {str(e)}")
    
            