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
    negative_balance_only: bool = False

@dataclass
class DateFilter:
    start_date: Optional[Union[str, date]] = None
    end_date: Optional[Union[str, date]] = None
    next_due_start: Optional[Union[str, date]] = None
    next_due_end: Optional[Union[str, date]] = None
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
    include_children: bool = False
    global_view: bool = False
    active_only: bool = True
    paused_only: bool = False
    overdue_only: bool = False

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

@dataclass
class CategorySearchRequest:
    text: TextSearchFilter = TextSearchFilter()
    category: CategoryFilter = CategoryFilter()
    parent: ParentFilter = ParentFilter()
    status: StatusFilter = StatusFilter()
    sort: SortOptions = SortOptions(sort_by= "name", sort_order= "ASC")
    depth_level: Optional[int] = None
    
@dataclass
class AccountSearchRequest:
    text: TextSearchFilter = TextSearchFilter()
    account: AccountFilter = AccountFilter()
    amount: AmountFilter = AmountFilter()
    status: StatusFilter = StatusFilter()
    sort: SortOptions = SortOptions(sort_by= "balance", sort_order= "DESC")

@dataclass
class RecurringSearchRequest:
    text: TextSearchFilter = TextSearchFilter()
    status: StatusFilter = StatusFilter()
    date: DateFilter = DateFilter()
    tx_type: TransactionTypeFilter = TransactionTypeFilter()
    status: StatusFilter = StatusFilter()
    sort: SortOptions = SortOptions(sort_by= "next_due", sort_order= "ASC")
    frequencies: Optional[List[str]] = None
    


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
                start_date, end_date = DateRangeValidator.validate_range(filters.date.start_date, filters.daate.end_date)
            
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
            allowed_sort_fields = {
                'transaction_date', 'amount', 'title', 'created_at', 
                'updated_at', 'transaction_type', 'category_name'
            }
            
            if filters.sort.sort_by not in allowed_sort_fields:
                filters.sort.sort_by = 'transaction_date'
            
            builder.add_order_by(f"{filters.sort.sort_by} {sort_order}")
            
            # Pagination
            pagination = PaginationHelper.calculate_pagination(total_count, filters.pagination.page, filters.pagination.page_size)
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
                'categories': filters.category.category_names or filters.category.category_ids,
                'accounts': filters.account.account_ids,
                'transaction_types': filters.tx_type.transaction_types,
                'payment_methods': filters.tx_type.payment_methods,
                'include_deleted': filters.status.include_deleted
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
    
    # ================================================================
    # CATEGORY SEARCH
    # ================================================================
    
    def search_categories(
        self,
        filters: CategorySearchRequest = CategorySearchRequest()
    ) -> Dict[str, Any]:
        """
        Search categories with hierarchy awareness.
        
        Args:
            filters.text.search_text: Text to search in category name/description
            filters.parent.parent_id: Filter by parent category
            filters.status.include_children: Include child categories
            filters.depth_level: Maximum hierarchy depth to include
            filters.status.include_deleted: Include soft-deleted categories
            filters.status.global_view: View global categories (admin only)
            filters.sort.sort_by: Column to sort by
            filters.sort.sort_order: 'ASC' or 'DESC'
            
        Returns:
            Dict with matching categories (flat or tree structure)
        """
        try:
            # Build query
            base_query = """
                SELECT c.*, 
                       u1.username AS owned_by_username, 
                       u2.username AS updated_by_username
                FROM categories c
                LEFT JOIN users u1 ON c.owner_id = u1.user_id
                LEFT JOIN users u2 ON c.updated_by = u2.user_id
                WHERE 1=1
            """
            
            builder = QueryBuilder(base_query)
            
            # Tenant filter
            tenant_filter = self._get_tenant_filter("c", filters.status.global_view)
            if tenant_filter:
                builder.add_condition(tenant_filter, self.user_id)
            
            # Deleted filter
            if not filters.status.include_deleted:
                builder.add_condition("c.is_deleted = 0")
            
            # Text search
            if filters.text and filters.text.search_text:
                search_text = InputSanitizer.sanitize_string(filters.text.search_text)
                builder.add_condition(
                    "(c.name LIKE %s OR c.description LIKE %s)",
                    f"%{search_text}%", f"%{search_text}%"
                )
            
            # Parent filter
            if filters.parent and filters.parent.parent_id is not None:
                if filters.status.include_children:
                    # Get all descendants
                    descendant_ids = self._get_descendant_categories(filters.parent.parent_id)
                    descendant_ids.append(filters.parent.parent_id)
                    builder.add_in_condition("c.category_id", descendant_ids)
                else:
                    builder.add_condition("c.parent_id = %s", filters.parent.parent_id)
            
            # Sorting
            sort_order = ValidationPatterns.validate_sort_order(filters.sort.sort_order)
            builder.add_order_by(f"c.{filters.sort.sort_by} {sort_order}")
            
            # Execute
            query, params = builder.build()
            results = self._execute(query, tuple(params), fetchall=True)
            
            return {
                'success': True,
                'results': results,
                'count': len(results)
            }
            
        except Exception as e:
            raise SearchError(f"Category search failed: {str(e)}")
    
    # ================================================================
    # ACCOUNT SEARCH
    # ================================================================
    
    def search_accounts(
        self,
        filters: AccountSearchRequest
    ) -> Dict[str, Any]:
        """
        Search accounts with balance and type filtering.
        
        Args:
            filters.text.search_text: Text to search in account name/description
            filters.amount.min_amount: Minimum balance
            filters.amount.max_amount: Maximum balance
            filters.amount.negative_balance_only: Only show accounts with negative balance
            filters.amount.account_types: List of account types to filter by
            filteers.status.active_only: Only show active accounts
            filters.status.include_deleted: Include soft-deleted accounts
            filters.status.global_view: View global accounts (admin only)
            filters.sort.sort_by: Column to sort by
            filters.sort.sort_order: 'ASC' or 'DESC'
            
        Returns:
            Dict with matching accounts
        """
        try:
            # Build query
            base_query = """
                SELECT a.*, u1.username AS owned_by_username
                FROM accounts a
                LEFT JOIN users u1 ON a.owner_id = u1.user_id
                WHERE 1=1
            """
            
            builder = QueryBuilder(base_query)
            
            # Tenant filter
            tenant_filter = self._get_tenant_filter("a", filters.status.global_view)
            if tenant_filter:
                builder.add_condition(tenant_filter, self.user_id)
            
            # Active filter
            if filters.status and filters.status.active_only:
                builder.add_condition("a.is_active = 1")
            
            # Deleted filter
            if not filters.status.include_deleted:
                builder.add_condition("a.is_deleted = 0")
            
            # Text search
            if filters.text and filters.text.search_text:
                search_text = InputSanitizer.sanitize_string(filters.text.search_text)
                builder.add_condition(
                    "(a.name LIKE %s OR a.description LIKE %s)",
                    f"%{search_text}%", f"%{search_text}%"
                )
            
            # Balance filters
            if filters.amount and filters.amount.negative_balance_only:
                builder.add_condition("a.balance < 0")
            else:
                min_bal, max_bal = AmountRangeValidator.validate_range(filters.amount.min_amount, filters.amount.max_amount)
                builder.add_amount_range("a.balance", min_bal, max_bal)
            
            # Type filters
            if filters.account and filters.account.account_types:
                builder.add_in_condition("a.account_type", filters.account.account_types)
            
            # Sorting
            sort_order = ValidationPatterns.validate_sort_order(filters.sort.sort_order)
            builder.add_order_by(f"a.{filters.sort.sort_by} {sort_order}")
            
            # Execute
            query, params = builder.build()
            results = self._execute(query, tuple(params), fetchall=True)
            
            # Calculate summary
            total_balance = sum(float(r['balance']) for r in results if r['is_active'])
            
            return {
                'success': True,
                'results': results,
                'count': len(results),
                'summary': {
                    'total_balance': total_balance,
                    'active_accounts': sum(1 for r in results if r['is_active']),
                    'negative_accounts': sum(1 for r in results if float(r['balance']) < 0)
                }
            }
            
        except Exception as e:
            raise SearchError(f"Account search failed: {str(e)}")
    
    # ================================================================
    # RECURRING TRANSACTION SEARCH
    # ================================================================
    
    def search_recurring(
        self,
        filters: RecurringSearchRequest
    ) -> Dict[str, Any]:
        """
        Search recurring transactions.
        
        Args:
            filters.text.search_text: Text to search in name/notes
            filters.frequencies: List of frequencies to filter by
            flters.status.active_only: Only show active recurring transactions
            filters.status.paused_only: Only show paused recurring transactions
            filters.status.overdue_only: Only show overdue recurring transactions
            filters.date.next_due_start: Earliest next_due date
            filters.date.next_due_end: Latest next_due date
            filters.tx_type.transaction_types: List of transaction types
            filters.status.include_deleted: Include soft-deleted records
            filters.status.global_view: View global recurring transactions
            filters.sort.sort_by: Column to sort by
            filters.sort.sort_order: 'ASC' or 'DESC'
            
        Returns:
            Dict with matching recurring transactions
        """
        try:
            # Build query
            base_query = """
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
            """
            
            builder = QueryBuilder(base_query)
            
            # Tenant filter
            tenant_filter = self._get_tenant_filter("r", filters.status.global_view)
            if tenant_filter:
                builder.add_condition(tenant_filter, self.user_id)
            
            # Deleted filter
            if not filters.status.include_deleted:
                builder.add_condition("r.is_deleted = 0")
            
            # Text search
            if filters.text.search_text:
                search_text = InputSanitizer.sanitize_string(filters.text.search_text)
                builder.add_condition(
                    "(r.name LIKE %s OR r.notes LIKE %s)",
                    f"%{search_text}%", f"%{search_text}%"
                )
            
            # Status filters
            if filters.status and filters.status.active_only:
                builder.add_condition("r.is_active = 1")
            
            if filters.status and filters.status.paused_only:
                builder.add_condition("r.pause_until IS NOT NULL")
                builder.add_condition("r.pause_until > NOW()")
            
            if filters.status and filters.status.overdue_only:
                builder.add_condition("r.next_due < NOW()")
                builder.add_condition("r.is_active = 1")
            
            # Next due date range
            if filters.date and filters.date.next_due_start and filters.date.next_due_end:
                next_due_start, next_due_end = DateRangeValidator.validate_range(
                    filters.date.next_due_start, filters.date.next_due_end
                )
                builder.add_date_range("r.next_due", next_due_start, next_due_end)
            
            # Frequency filters
            if filters.frequencies is not None:
                builder.add_in_condition("r.frequency", filters.frequencies)
            
            # Transaction type filters
            if filters.tx_type and filters.tx_type.transaction_types is not None:
                builder.add_in_condition("r.transaction_type", filters.tx_type.transaction_types)
            
            # Sorting
            if filters.sort and filters.sort.sort_by is not None:
                sort_order = ValidationPatterns.validate_sort_order(filters.sort.sort_order)
                builder.add_order_by(f"r.{filters.sort.sort_by} {sort_order}")
            
            # Execute
            query, params = builder.build()
            results = self._execute(query, tuple(params), fetchall=True)
            
            # Calculate summary
            now = datetime.now()
            summary = {
                'total_active': sum(1 for r in results if r['is_active']),
                'total_paused': sum(1 for r in results if r['pause_until'] and r['pause_until'] > now),
                'total_overdue': sum(1 for r in results if r['next_due'] and r['next_due'] < now and r['is_active'])
            }
            
            return {
                'success': True,
                'results': results,
                'count': len(results),
                'summary': summary
            }
            
        except Exception as e:
            raise SearchError(f"Recurring search failed: {str(e)}")

    # ================================================================
    # HELPER METHODS
    # ================================================================
    
    def _execute(self, sql: str, params: Tuple[Any, ...], *, fetchone: bool = False, fetchall: bool = False):
        """Execute SQL query with error handling."""
        # validate flags
        if fetchone and fetchall:
            raise SearchError("Invalid flags: fetchone and fetchall cannot both be True")
        try:
            with self.conn.cursor(dictionary=True) as cursor:
                cursor.execute(sql, params)
                
                if fetchone:
                    return cursor.fetchone()
                if fetchall:
                    return cursor.fetchall()
                
                self.conn.commit()
                return cursor.lastrowid
                
        except mysql.connector.Error as e:
            try:
                self.conn.rollback()
            except:
                pass
            raise SearchError(f"Database error: {str(e)}")
    
    def _get_tenant_filter(self, alias: str, global_view: bool) -> Optional[str]:
        """Generate tenant filter clause."""
        if self.role == "admin":
            if global_view:
                return f"{alias}.is_global = 1"
            else:
                return f"{alias}.owner_id = %s" if alias != "t" else f"{alias}.user_id = %s"
        else:
            if not global_view:
                return f"{alias}.owner_id = %s" if alias != "t" else f"{alias}.user_id = %s"
        return None
    
    def _get_category_hierarchy(self, category_ids: List[int]) -> List[int]:
        """Get all descendant categories recursively."""
        if not category_ids:
            return []
        
        all_ids = set(category_ids)
        
        for cat_id in category_ids:
            descendants = self._get_descendant_categories(cat_id)
            all_ids.update(descendants)
        
        return list(all_ids)
    
    def _get_descendant_categories(self, parent_id: int) -> List[int]:
        """Get all descendant category IDs."""
        query = """
            WITH RECURSIVE descendants AS (
                SELECT category_id FROM categories WHERE category_id = %s
                UNION ALL
                SELECT c.category_id 
                FROM categories c
                INNER JOIN descendants d ON c.parent_id = d.category_id
                WHERE c.is_deleted = 0
            )
            SELECT category_id FROM descendants WHERE category_id != %s
        """
        
        results = self._execute(query, (parent_id, parent_id), fetchall=True)
        return [r['category_id'] for r in results]
    
    def _get_category_ids_by_names(self, names: List[str]) -> List[int]:
        """Convert category names to IDs."""
        if not names:
            return []
        
        placeholders = ", ".join(["%s"] * len(names))
        query = f"""
            SELECT category_id 
            FROM categories 
            WHERE name IN ({placeholders})
              AND owner_id = %s
              AND is_deleted = 0
        """
        
        params = names + [self.user_id]
        results = self._execute(query, tuple(params), fetchall=True)
        return [r['category_id'] for r in results]
    
    def _calculate_transaction_summary(self, transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate summary statistics for transaction results."""
        if not transactions:
            return {
                'total_income': 0,
                'total_expense': 0,
                'total_transfers': 0,
                'net_amount': 0,
                'transaction_count': 0
            }
        
        income = sum(float(t['amount']) for t in transactions if t['transaction_type'] in ['income', 'debt_borrowed'])
        expense = sum(float(t['amount']) for t in transactions if t['transaction_type'] in ['expense', 'debt_repaid'])
        transfers = sum(float(t['amount']) for t in transactions if t['transaction_type'] in ['transfer', 'investment_deposit', 'investment_withdraw'])
        
        return {
            'total_income': income,
            'total_expense': expense,
            'total_transfers': transfers,
            'net_amount': income - expense,
            'transaction_count': len(transactions)
        }



    