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
