#CSV, PDF, Excel reports
"""
Export and Report Generation Service for Budget Tracker

This module provides comprehensive export and reporting capabilities:
- CSV exports using pandas
- PDF reports using reportlab
- Transaction exports by category/month/week/day
- Account summaries and balance reports
- Category spending analysis
- Custom date range reports
- Automatic file naming and organization

Exports are saved to: /reports/exports/
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple, Union
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
import os
import pandas as pd
from dataclasses import dataclass, asdict

# PDF imports
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.platypus import Image as RLImage
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# Excel imports
try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
    from openpyxl.chart import PieChart, BarChart, Reference
    from openpyxl.utils.dataframe import dataframe_to_rows
    from openpyxl.worksheet.table import Table as ExcelTable, TableStyleInfo
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

import mysql.connector

# Import search service for data retrieval
from features.search import (
    SearchService,
    TransactionSearchRequest,
    CategorySearchRequest,
    AccountSearchRequest,
    RecurringSearchRequest,
    TextSearchFilter,
    AmountFilter,
    DateFilter,
    CategoryFilter,
    AccountFilter,
    TransactionTypeFilter,
    StatusFilter,
    SortOptions,
    Pagination
)

# Import utilities
from core.utils import (
    DateRangeValidator,
    FormatHelper,
    ValidationPatterns
)


# ================================================================
# Export Configuration
# ================================================================

@dataclass
class ExportConfig:
    """Configuration for export operations."""
    output_dir: str = "reports/exports"
    csv_encoding: str = "utf-8"
    csv_index: bool = False
    pdf_pagesize: str = "letter"  # 'letter' or 'A4'
    excel_include_charts: bool = True
    excel_include_formulas: bool = True
    excel_sheet_name: str = "Data"
    include_summary: bool = True
    include_charts: bool = False  # Future: add chart generation
    filename_prefix: str = ""
    

@dataclass
class ExportMetadata:
    """Metadata for generated exports."""
    filename: str
    filepath: str
    format: str  # 'csv' or 'pdf'
    generated_at: datetime
    record_count: int
    date_range: str
    filters_applied: Dict[str, Any]
    file_size_bytes: int


# ================================================================
# Custom Exceptions
# ================================================================

class ExportError(Exception):
    """Base exception for export operations"""
    pass


class ExportValidationError(ExportError):
    """Raised when export parameters are invalid"""
    pass

# ================================================================
# Main Export Service
# ================================================================

class ExportService:
    """
    Centralized export and report generation service.
    
    Provides methods for exporting transactions, accounts, and categories
    in CSV and PDF formats with various grouping and filtering options.
    """
    
    def __init__(
        self, 
        conn: mysql.connector.MySQLConnection, 
        current_user: Dict[str, Any],
        config: Optional[ExportConfig] = None
    ):
        self.conn = conn
        self.user = current_user
        self.user_id = current_user.get("user_id")
        self.username = current_user.get("username")
        self.role = current_user.get("role")
        
        # Initialize search service for data retrieval
        self.search_service = SearchService(conn, current_user)
        #configuration
        self.config = config or ExportConfig()

        # Ensure output directory exists
        self._ensure_output_dir()
    
    def _ensure_output_dir(self):
        """Create output directory if it doesn't exist."""
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)

    # ================================================================
    # CSV EXPORTS
    # ================================================================
    
    def export_transactions_csv(
        self,
        filters: TransactionSearchRequest,
        filename: Optional[str] = None,
        group_by: Optional[str] = None  # 'category', 'account', 'date', 'month', 'week'
    ) -> ExportMetadata:
        """
        Export transactions to CSV with optional grouping.
        
        Args:
            filters: TransactionSearchRequest with search criteria
            filename: Custom filename (optional, auto-generated if None)
            group_by: Grouping option for the export
            
        Returns:
            ExportMetadata with file information
            
        Examples:
            # Export all transactions
            metadata = service.export_transactions_csv(
                TransactionSearchRequest()
            )
            
            # Export this month's expenses grouped by category
            metadata = service.export_transactions_csv(
                TransactionSearchRequest(
                    date=DateFilter(date_preset="this_month"),
                    tx_type=TransactionTypeFilter(transaction_types=["expense"])
                ),
                group_by="category"
            )
        """