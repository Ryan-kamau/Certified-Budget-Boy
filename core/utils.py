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
        

            
