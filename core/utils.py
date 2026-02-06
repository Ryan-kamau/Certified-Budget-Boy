"""
Common Helper Functions for Budget Tracker

This module provides reusable utility functions for:
- Date range validation and parsing
- Amount range filtering
- Query building with dynamic filters
- Input sanitization
- Common validation patterns
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple, Union
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
import re

#============================================================================
# Date Utilities
# ============================================================================

class DateRangeValidator:
    """Validates and normalizes date ranges for queries."""
    
    @staticmethod
    def parse_date(date_input: Union[str, date, datetime, None]) -> Optional[date]:
        """
        Parse various date formats into a date object.
        
        Supported formats:
        - YYYY-MM-DD (ISO format)
        - DD/MM/YYYY
        - MM-DD-YYYY
        - date object
        - datetime object
        
        Args:
            date_input: Date in various formats
            
        Returns:
            date object or None if invalid
            
        Examples:
            >>> DateRangeValidator.parse_date("2024-02-04")
            datetime.date(2024, 2, 4)
            
            >>> DateRangeValidator.parse_date("04/02/2024")
            datetime.date(2024, 2, 4)
        """
        if date_input is None:
            return None
            
        if isinstance(date_input, date):
            return date_input
            
        if isinstance(date_input, datetime):
            return date_input.date()
            
        if isinstance(date_input, str):
            date_input = date_input.strip()
            
            # Try ISO format YYYY-MM-DD
            try:
                return datetime.strptime(date_input, "%Y-%m-%d").date()
            except ValueError:
                pass
            
            # Try DD/MM/YYYY
            try:
                return datetime.strptime(date_input, "%d/%m/%Y").date()
            except ValueError:
                pass
            
            # Try MM-DD-YYYY
            try:
                return datetime.strptime(date_input, "%m/%d/%Y").date()
            except ValueError:
                pass
        
        return None
    
    @staticmethod
    def validate_range(
        start_date: Optional[Union[str, date]], 
        end_date: Optional[Union[str, date]]
    ) -> Tuple[Optional[date], Optional[date]]:
        """
        Validate and normalize a date range.
        
        Args:
            start_date: Start of range
            end_date: End of range
            
        Returns:
            Tuple of (start_date, end_date) as date objects
            
        Raises:
            ValueError: If end_date is before start_date
        """
        start = DateRangeValidator.parse_date(start_date)
        end = DateRangeValidator.parse_date(end_date)
        
        if start and end and end < start:
            raise ValueError(
                f"End date ({end}) cannot be before start date ({start})"
            )
        
        return start, end
    
    @staticmethod
    def get_preset_range(preset: str) -> Tuple[date, date]:
        """
        Get predefined date ranges.
        
        Args:
            preset: One of 'today', 'yesterday', 'this_week', 'last_week',
                   'this_month', 'last_month', 'this_year', 'last_year',
                   'last_7_days', 'last_30_days', 'last_90_days'
        
        Returns:
            Tuple of (start_date, end_date)
            
        Raises:
            ValueError: If preset is unknown
        """
        today = date.today()
        
        if preset == "today":
            return today, today
        
        elif preset == "yesterday":
            yesterday = today - timedelta(days=1)
            return yesterday, yesterday
        
        elif preset == "this_week":
            # Monday to today
            start = today - timedelta(days=today.weekday())
            return start, today
        
        elif preset == "last_week":
            # Previous Monday to Sunday
            last_monday = today - timedelta(days=today.weekday() + 7)
            last_sunday = last_monday + timedelta(days=6)
            return last_monday, last_sunday
        
        elif preset == "this_month":
            start = today.replace(day=1)
            return start, today
        
        elif preset == "last_month":
            # First day of last month
            first_this_month = today.replace(day=1)
            last_day_last_month = first_this_month - timedelta(days=1)
            first_last_month = last_day_last_month.replace(day=1)
            return first_last_month, last_day_last_month
        
        elif preset == "this_year":
            start = today.replace(month=1, day=1)
            return start, today
        
        elif preset == "last_year":
            last_year = today.year - 1
            start = date(last_year, 1, 1)
            end = date(last_year, 12, 31)
            return start, end
        
        elif preset == "last_7_days":
            start = today - timedelta(days=6)
            return start, today
        
        elif preset == "last_30_days":
            start = today - timedelta(days=29)
            return start, today
        
        elif preset == "last_90_days":
            start = today - timedelta(days=89)
            return start, today
        
        else:
            raise ValueError(
                f"Unknown preset: {preset}. Valid options: today, yesterday, "
                "this_week, last_week, this_month, last_month, this_year, "
                "last_year, last_7_days, last_30_days, last_90_days"
            )
        
class AmountRangeValidator:
    """Validates and normalizes amount ranges for queries."""
    
    @staticmethod
    def parse_amount(amount_input: Union[str, int, float, Decimal, None]) -> Optional[Decimal]:
        """
        Parse various amount formats into a Decimal object.
        
        Args:
            amount_input: Amount in various formats
            
        Returns:
            Decimal object or None if invalid
            
        Examples:
            >>> AmountRangeValidator.parse_amount("100.50")
            Decimal('100.50')
            
            >>> AmountRangeValidator.parse_amount(200)
            Decimal('200')
        """
        if amount_input is None:
            return None
            
        if isinstance(amount_input, Decimal):
            return amount_input
            
        if isinstance(amount_input, (int, float)):
            return Decimal(str(amount_input))
            
        if isinstance(amount_input, str):
            amount_input = amount_input.strip()
            try:
                return Decimal(amount_input)
            except InvalidOperation:
                return None
                
        return None

    @staticmethod
    def validate_range(
        min_amount: Optional[Union[str, float, Decimal]],
        max_amount: Optional[Union[str, float, Decimal]]
    ) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Validate and normalize an amount range.
        
        Args:
            min_amount: Minimum amount
            max_amount: Maximum amount
            
        Returns:
            Tuple of (min_amount, max_amount) as Decimals
            
        Raises:
            ValueError: If max_amount is less than min_amount or negative amounts
        """
        min_val = AmountRangeValidator.parse_amount(min_amount)
        max_val = AmountRangeValidator.parse_amount(max_amount)
        
        if min_val is not None and min_val < 0:
            raise ValueError("Minimum amount cannot be negative")
        
        if max_val is not None and max_val < 0:
            raise ValueError("Maximum amount cannot be negative")
        
        if min_val and max_val and max_val < min_val:
            raise ValueError(
                f"Maximum amount ({max_val}) cannot be less than "
                f"minimum amount ({min_val})"
            )
        
        return min_val, max_val

# ============================================================================
# Query Building Utilities
# ============================================================================

class QueryBuilder:
    """Dynamic SQL query builder with parameter management."""
    
    def __init__(self, base_query: str):
        """
        Initialize query builder.
        
        Args:
            base_query: Base SQL query (usually a SELECT with WHERE 1=1)
        """
        self.query = base_query
        self.params: List[Any] = []
    
    def add_condition(self, condition: str, *params: Any) -> "QueryBuilder":
        """
        Add a WHERE condition with parameters.
        
        Args:
            condition: SQL condition (e.g., "amount >= %s")
            *params: Parameters for the condition
            
        Returns:
            Self for method chaining
        """
        self.query += f" AND {condition}"
        self.params.extend(params)
        return self
    
    def add_date_range(
        self,
        column: str,
        start_date: Optional[date],
        end_date: Optional[date]
    ) -> "QueryBuilder":
        """
        Add date range conditions.
        
        Args:
            column: Date column name
            start_date: Start of range (inclusive)
            end_date: End of range (inclusive)
            
        Returns:
            Self for method chaining
        """
        if start_date:
            self.add_condition(f"{column} >= %s", start_date)
        if end_date:
            self.add_condition(f"{column} <= %s", end_date)
        return self
    
    def add_amount_range(
        self,
        column: str,
        min_amount: Optional[Decimal],
        max_amount: Optional[Decimal]
    ) -> "QueryBuilder":
        """
        Add amount range conditions.
        
        Args:
            column: Amount column name
            min_amount: Minimum amount (inclusive)
            max_amount: Maximum amount (inclusive)
            
        Returns:
            Self for method chaining
        """
        if min_amount is not None:
            self.add_condition(f"{column} >= %s", min_amount)
        if max_amount is not None:
            self.add_condition(f"{column} <= %s", max_amount)
        return self
    
    def add_in_condition(
        self,
        column: str,
        values: Optional[List[Any]]
    ) -> "QueryBuilder":
        """
        Add IN condition for multiple values.
        
        Args:
            column: Column name
            values: List of values
            
        Returns:
            Self for method chaining
        """
        if values:
            placeholders = ", ".join(["%s"] * len(values))
            self.add_condition(f"{column} IN ({placeholders})", *values)
        return self
    
    def add_like_condition(
        self,
        column: str,
        search_term: Optional[str],
        match_type: str = "contains"
    ) -> "QueryBuilder":
        """
        Add LIKE condition for text search.
        
        Args:
            column: Column name
            search_term: Search term
            match_type: One of 'contains', 'starts_with', 'ends_with', 'exact'
            
        Returns:
            Self for method chaining
        """
        if search_term:
            if match_type == "contains":
                pattern = f"%{search_term}%"
            elif match_type == "starts_with":
                pattern = f"{search_term}%"
            elif match_type == "ends_with":
                pattern = f"%{search_term}"
            elif match_type == "exact":
                pattern = search_term
            else:
                raise ValueError(f"Unknown match_type: {match_type}")
            
            self.add_condition(f"{column} LIKE %s", pattern)
        return self
    
    def add_order_by(self, order_clause: str) -> "QueryBuilder":
        """
        Add ORDER BY clause.
        
        Args:
            order_clause: ORDER BY clause (e.g., "amount DESC, date ASC")
            
        Returns:
            Self for method chaining
        """
        self.query += f" ORDER BY {order_clause}"
        return self
    
    def add_limit_offset(
        self,
        limit: Optional[int],
        offset: Optional[int] = None
    ) -> "QueryBuilder":
        """
        Add LIMIT and OFFSET clauses.
        
        Args:
            limit: Maximum number of rows
            offset: Number of rows to skip
            
        Returns:
            Self for method chaining
        """
        if limit is not None:
            self.query += " LIMIT %s"
            self.params.append(limit)
        
        if offset is not None:
            self.query += " OFFSET %s"
            self.params.append(offset)
        
        return self
    
    def build(self) -> Tuple[str, List[Any]]:
        """
        Build final query and parameters.
        
        Returns:
            Tuple of (query_string, parameters)
        """
        return self.query, self.params


# ============================================================================
# Input Sanitization
# ============================================================================

class InputSanitizer:
    """Sanitize and validate user inputs."""
    
    @staticmethod
    def sanitize_string(
        value: Optional[str],
        max_length: Optional[int] = None,
        allow_empty: bool = True
    ) -> Optional[str]:
        """
        Sanitize string input.
        
        Args:
            value: Input string
            max_length: Maximum allowed length
            allow_empty: Whether to allow empty strings
            
        Returns:
            Sanitized string or None
        """
        if value is None:
            return None
        
        # Strip whitespace
        cleaned = value.strip()
        
        # Handle empty string
        if not cleaned:
            return None if not allow_empty else ""
        
        # Truncate if needed
        if max_length and len(cleaned) > max_length:
            cleaned = cleaned[:max_length]
        
        return cleaned
    
    @staticmethod
    def validate_enum(
        value: Optional[str],
        allowed_values: List[str],
        case_sensitive: bool = False
    ) -> Optional[str]:
        """
        Validate that value is in allowed list.
        
        Args:
            value: Input value
            allowed_values: List of allowed values
            case_sensitive: Whether comparison is case-sensitive
            
        Returns:
            Validated value or None
            
        Raises:
            ValueError: If value is not in allowed_values
        """
        if value is None:
            return None
        
        cleaned = value.strip()
        
        if not case_sensitive:
            cleaned = cleaned.lower()
            allowed_values = [v.lower() for v in allowed_values]
        
        if cleaned not in allowed_values:
            raise ValueError(
                f"Invalid value '{value}'. Must be one of: {', '.join(allowed_values)}"
            )
        
        return cleaned
    
    @staticmethod
    def parse_comma_separated(value: Optional[str]) -> List[str]:
        """
        Parse comma-separated values into list.
        
        Args:
            value: Comma-separated string
            
        Returns:
            List of trimmed values
            
        Examples:
            >>> InputSanitizer.parse_comma_separated("tag1, tag2, tag3")
            ['tag1', 'tag2', 'tag3']
        """
        if not value:
            return []
        
        return [item.strip() for item in value.split(",") if item.strip()]


# ============================================================================
# Validation Patterns
# ============================================================================

class ValidationPatterns:
    """Common validation patterns."""
    
    # Transaction types
    TRANSACTION_TYPES = [
        'income', 'expense', 'transfer', 
        'debt_borrowed', 'debt_repaid',
        'investment_deposit', 'investment_withdraw'
    ]
    
    # Payment methods
    PAYMENT_METHODS = [
        'cash', 'bank', 'mobile_money', 'credit_card', 'other'
    ]
    
    # Account types
    ACCOUNT_TYPES = [
        'cash', 'bank', 'mobile_money', 'credit', 'savings', 'investments', 'other'
    ]
    
    # Recurring frequencies
    RECURRING_FREQUENCIES = ['daily', 'weekly', 'monthly', 'yearly']
    
    # Sort orders
    SORT_ORDERS = ['ASC', 'DESC']
    
    # Date presets
    DATE_PRESETS = [
        'today', 'yesterday', 'this_week', 'last_week',
        'this_month', 'last_month', 'this_year', 'last_year',
        'last_7_days', 'last_30_days', 'last_90_days'
    ]
    
    @staticmethod
    def validate_transaction_type(value: str) -> str:
        """Validate transaction type."""
        return InputSanitizer.validate_enum(
            value, 
            ValidationPatterns.TRANSACTION_TYPES,
            case_sensitive=False
        )
    
    @staticmethod
    def validate_payment_method(value: str) -> str:
        """Validate payment method."""
        return InputSanitizer.validate_enum(
            value,
            ValidationPatterns.PAYMENT_METHODS,
            case_sensitive=False
        )
    
    @staticmethod
    def validate_sort_order(value: str) -> str:
        """Validate sort order."""
        return InputSanitizer.validate_enum(
            value,
            ValidationPatterns.SORT_ORDERS,
            case_sensitive=False
        )


# ============================================================================
# Pagination Helper
# ============================================================================

class PaginationHelper:
    """Helper for pagination calculations."""
    
    @staticmethod
    def calculate_pagination(
        total_count: int,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """
        Calculate pagination metadata.
        
        Args:
            total_count: Total number of items
            page: Current page number (1-indexed)
            page_size: Items per page
            
        Returns:
            Dict with pagination metadata
            
        Examples:
            >>> PaginationHelper.calculate_pagination(100, 2, 25)
            {
                'total_count': 100,
                'page': 2,
                'page_size': 25,
                'total_pages': 4,
                'offset': 25,
                'has_next': True,
                'has_prev': True
            }
        """
        if page < 1:
            page = 1
        
        if page_size < 1:
            page_size = 50
        
        total_pages = (total_count + page_size - 1) // page_size
        offset = (page - 1) * page_size
        
        return {
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'offset': offset,
            'has_next': page < total_pages,
            'has_prev': page > 1
        }


# ============================================================================
# Format Helpers
# ============================================================================

class FormatHelper:
    """Format data for display."""
    
    @staticmethod
    def format_currency(amount: Union[float, Decimal], currency: str = "KES") -> str:
        """
        Format amount as currency.
        
        Args:
            amount: Amount to format
            currency: Currency code
            
        Returns:
            Formatted currency string
            
        Examples:
            >>> FormatHelper.format_currency(1234.56)
            'KES 1,234.56'
        """
        return f"{currency} {amount:,.2f}"
    
    @staticmethod
    def format_date_range(start: Optional[date], end: Optional[date]) -> str:
        """
        Format date range for display.
        
        Args:
            start: Start date
            end: End date
            
        Returns:
            Formatted date range string
        """
        if start and end:
            return f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
        elif start:
            return f"From {start.strftime('%Y-%m-%d')}"
        elif end:
            return f"Until {end.strftime('%Y-%m-%d')}"
        else:
            return "All dates"
