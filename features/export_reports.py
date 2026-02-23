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
        try:
            # Fetch data using search service (get all results, no pagination limit)
            filters.pagination = Pagination(page_size=100000)  # Large limit to get all
            result = self.search_service.search_transactions(filters)
            
            if not result['results']:
                raise ExportError("No transactions found matching the criteria")
            
            # Convert to DataFrame
            df = pd.DataFrame(result['results'])
            
            # Select and order columns
            columns = [
                'transaction_id', 'transaction_date', 'title', 'amount',
                'transaction_type', 'payment_method', 'category_name',
                'account_name', 'source_account_name', 'destination_account_name',
                'description', 'owned_by_username', 'created_at'
            ]
            
            # Keep only columns that exist
            columns = [col for col in columns if col in df.columns]
            df = df[columns]
            
            # Apply grouping if requested
            if group_by:
                df = self._apply_grouping(df, group_by)

            # Apply grouping if requested
            if group_by:
                df = self._apply_grouping(df, group_by)
            
            # Generate filename
            if not filename:
                filename = self._generate_filename(
                    prefix="transactions",
                    filters=filters,
                    extension="csv",
                    group_by=group_by
                )
            
            filepath = os.path.join(self.config.output_dir, filename)
            # Export to CSV
            df.to_csv(
                filepath,
                index=self.config.csv_index,
                encoding=self.config.csv_encoding
            )
            # Create metadata
            metadata = self._create_metadata(
                filename=filename,
                filepath=filepath,
                format="csv",
                record_count=len(result['results']),
                filters=result['filters_applied']
            )
            
            return metadata
            
        except Exception as e:
            raise ExportError(f"CSV export failed: {str(e)}")
        
    def export_accounts_csv(
        self,
        filters: AccountSearchRequest,
        filename: Optional[str] = None
    ) -> ExportMetadata:
        """
        Export accounts to CSV.
        
        Args:
            filters: AccountSearchRequest with search criteria
            filename: Custom filename (optional)
            
        Returns:
            ExportMetadata with file information
        """
        try:
            # Fetch data
            result = self.search_service.search_accounts(filters)
            
            if not result['results']:
                raise ExportError("No accounts found matching the criteria")
            
            # Convert to DataFrame
            df = pd.DataFrame(result['results'])
            
            # Select columns
            columns = [
                'account_id', 'name', 'account_type', 'balance',
                'currency', 'is_active', 'description',
                'owned_by_username', 'created_at', 'updated_at'
            ]
            columns = [col for col in columns if col in df.columns]
            df = df[columns]
            
            # Generate filename
            if not filename:
                filename = self._generate_filename(
                    prefix="accounts",
                    filters=None,
                    extension="csv"
                )
            
            filepath = os.path.join(self.config.output_dir, filename)
            
            # Export to CSV
            df.to_csv(
                filepath,
                index=self.config.csv_index,
                encoding=self.config.csv_encoding
            )
            
            # Create metadata
            metadata = self._create_metadata(
                filename=filename,
                filepath=filepath,
                format="csv",
                record_count=len(result['results']),
                filters={"account_filters": "applied"}
            )
            
            return metadata
            
        except Exception as e:
            raise ExportError(f"Account CSV export failed: {str(e)}")
    
    def export_categories_csv(
        self,
        filters: CategorySearchRequest,
        filename: Optional[str] = None
    ) -> ExportMetadata:
        """
        Export categories to CSV.
        
        Args:
            filters: CategorySearchRequest with search criteria
            filename: Custom filename (optional)
            
        Returns:
            ExportMetadata with file information
        """
        try:
            # Fetch data
            result = self.search_service.search_categories(filters)
            
            if not result['results']:
                raise ExportError("No categories found matching the criteria")
            
            # Convert to DataFrame
            df = pd.DataFrame(result['results'])
            
            # Select columns
            columns = [
                'category_id', 'name', 'parent_id', 'description',
                'is_global', 'owned_by_username', 'created_at'
            ]
            columns = [col for col in columns if col in df.columns]
            df = df[columns]
            
            # Generate filename
            if not filename:
                filename = self._generate_filename(
                    prefix="categories",
                    filters=None,
                    extension="csv"
                )
            
            filepath = os.path.join(self.config.output_dir, filename)
            
            # Export to CSV
            df.to_csv(
                filepath,
                index=self.config.csv_index,
                encoding=self.config.csv_encoding
            )
            
            # Create metadata
            metadata = self._create_metadata(
                filename=filename,
                filepath=filepath,
                format="csv",
                record_count=len(result['results']),
                filters={"category_filters": "applied"}
            )
            
            return metadata
            
        except Exception as e:
            raise ExportError(f"Category CSV export failed: {str(e)}")
    
    # ================================================================
    # PDF EXPORTS
    # ================================================================
    
    def export_transactions_pdf(
        self,
        filters: TransactionSearchRequest,
        filename: Optional[str] = None,
        title: str = "Transaction Report",
        group_by: Optional[str] = None
    ) -> ExportMetadata:
        """
        Export transactions to PDF with formatting and summary.
        
        Args:
            filters: TransactionSearchRequest with search criteria
            filename: Custom filename (optional)
            title: Report title
            group_by: Grouping option for the report
            
        Returns:
            ExportMetadata with file information
            
        Raises:
            ExportError: If PDF generation is not available
        """
        if not PDF_AVAILABLE:
            raise ExportError(
                "PDF export not available. Install reportlab: pip install reportlab"
            )
        try:
            # Fetch data
            filters.pagination = Pagination(page_size=100000)
            result = self.search_service.search_transactions(filters)
            
            if not result['results']:
                raise ExportError("No transactions found matching the criteria")
            
            # Generate filename
            if not filename:
                filename = self._generate_filename(
                    prefix="transactions",
                    filters=filters,
                    extension="pdf",
                    group_by=group_by
                )
            
            filepath = os.path.join(self.config.output_dir, filename)
            
            # Create PDF
            pagesize = A4 if self.config.pdf_pagesize == "A4" else letter
            doc = SimpleDocTemplate(
                filepath,
                pagesize=pagesize,
                rightMargin=0.5*inch,
                leftMargin=0.5*inch,
                topMargin=0.75*inch,
                bottomMargin=0.5*inch
            )
            
            # Build content
            story = []
            styles = getSampleStyleSheet()
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#1a1a1a'),
                spaceAfter=30,
                alignment=TA_CENTER
            )
            story.append(Paragraph(title, title_style))
            
            # Metadata section
            story.extend(self._create_pdf_metadata_section(result, styles))
            story.append(Spacer(1, 0.3*inch))
            
            # Summary section
            if self.config.include_summary:
                story.extend(self._create_pdf_summary_section(result, styles))
                story.append(Spacer(1, 0.3*inch))
            
            # Transactions table
            if group_by:
                story.extend(self._create_pdf_grouped_table(
                    result['results'], group_by, styles
                ))
            else:
                story.extend(self._create_pdf_transaction_table(
                    result['results'], styles
                ))
            
            # Build PDF
            doc.build(story)
            
            # Create metadata
            metadata = self._create_metadata(
                filename=filename,
                filepath=filepath,
                format="pdf",
                record_count=len(result['results']),
                filters=result['filters_applied']
            )
            
            return metadata
            
        except Exception as e:
            raise ExportError(f"PDF export failed: {str(e)}")

    def export_account_summary_pdf(
        self,
        filters: AccountSearchRequest,
        filename: Optional[str] = None,
        title: str = "Account Summary Report"
    ) -> ExportMetadata:
        """
        Export account summary to PDF.
        
        Args:
            filters: AccountSearchRequest with search criteria
            filename: Custom filename (optional)
            title: Report title
            
        Returns:
            ExportMetadata with file information
        """
        if not PDF_AVAILABLE:
            raise ExportError(
                "PDF export not available. Install reportlab: pip install reportlab"
            )
        
        try:
            # Fetch data
            result = self.search_service.search_accounts(filters)
            
            if not result['results']:
                raise ExportError("No accounts found matching the criteria")
            
            # Generate filename
            if not filename:
                filename = self._generate_filename(
                    prefix="account_summary",
                    filters=None,
                    extension="pdf"
                )
            
            filepath = os.path.join(self.config.output_dir, filename)
            
            # Create PDF
            pagesize = A4 if self.config.pdf_pagesize == "A4" else letter
            doc = SimpleDocTemplate(filepath, pagesize=pagesize)
            
            story = []
            styles = getSampleStyleSheet()
            
            # Title
            story.append(Paragraph(title, styles['Title']))
            story.append(Spacer(1, 0.3*inch))
            
            # Summary statistics
            summary_data = [
                ['Metric', 'Value'],
                ['Total Accounts', str(result['count'])],
                ['Active Accounts', str(result['summary']['active_accounts'])],
                ['Total Balance', f"{result['summary']['total_balance']:.2f}"],
                ['Negative Accounts', str(result['summary']['negative_accounts'])]
            ]
            
            summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 0.5*inch))
            
            # Account details table
            story.append(Paragraph("Account Details", styles['Heading2']))
            story.append(Spacer(1, 0.2*inch))
            
            account_data = [['Account Name', 'Type', 'Balance', 'Status']]
            for acc in result['results']:
                status = "Active" if acc['is_active'] else "Inactive"
                account_data.append([
                    str(acc['name'])[:30],
                    str(acc['account_type']),
                    f"{float(acc['balance']):.2f}",
                    status
                ])
            
            account_table = Table(account_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch, 1*inch])
            account_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (2, 1), (2, -1), 'RIGHT'),  # Right-align balance
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(account_table)
            
            # Build PDF
            doc.build(story)
            
            # Create metadata
            metadata = self._create_metadata(
                filename=filename,
                filepath=filepath,
                format="pdf",
                record_count=len(result['results']),
                filters={"account_summary": "applied"}
            )
            
            return metadata
            
        except Exception as e:
            raise ExportError(f"Account PDF export failed: {str(e)}")

        # ================================================================
    # EXCEL EXPORTS
    # ================================================================
    
    def export_transactions_excel(
        self,
        filters: TransactionSearchRequest,
        filename: Optional[str] = None,
        include_summary: bool = True,
        include_charts: bool = True
    ) -> ExportMetadata:
        """
        Export transactions to Excel with multiple sheets, formatting, and charts.
        
        Args:
            filters: TransactionSearchRequest with search criteria
            filename: Custom filename (optional)
            include_summary: Include summary sheet
            include_charts: Include charts in summary
            
        Returns:
            ExportMetadata with file information
            
        Features:
            - Multiple sheets (Transactions, Summary, By Category)
            - Professional formatting (headers, colors, borders)
            - Formulas (SUM, AVERAGE)
            - Charts (category spending, trends)
            - Auto-column width
            
        Raises:
            ExportError: If Excel generation is not available
        """
        if not EXCEL_AVAILABLE:
            raise ExportError(
                "Excel export not available. Install openpyxl: pip install openpyxl"
            )
        try:
            # Fetch data
            filters.pagination = Pagination(page_size=100000)
            result = self.search_service.search_transactions(filters)
            
            if not result['results']:
                raise ExportError("No transactions found matching the criteria")
            
            # Generate filename
            if not filename:
                filename = self._generate_filename(
                    prefix="transactions",
                    filters=filters,
                    extension="xlsx"
                )
            
            filepath = os.path.join(self.config.output_dir, filename)
            # Create workbook and sheets
            wb = Workbook()
        
            # Remove default sheet
            if 'Sheet' in wb.sheetnames:
                wb.remove(wb['Sheet'])
            
            # Create sheets
            self._create_transactions_sheet(wb, result['results'])
            
            if include_summary:
                self._create_summary_sheet(wb, result['summary'], result['filters_applied'])
                self._create_category_breakdown_sheet(wb, result['results'])
                
                if include_charts and self.config.excel_include_charts:
                    self._add_excel_charts(wb)
            
            # Save workbook
            wb.save(filepath)
            
            # Create metadata
            metadata = self._create_metadata(
                filename=filename,
                filepath=filepath,
                format="excel",
                record_count=len(result['results']),
                filters=result['filters_applied']
            )
            
            return metadata
            
        except Exception as e:
            raise ExportError(f"Excel export failed: {str(e)}")
    
    def export_accounts_excel(
        self,
        filters: AccountSearchRequest,
        filename: Optional[str] = None
    ) -> ExportMetadata:
        """
        Export accounts to Excel with formatting and summary.
        
        Args:
            filters: AccountSearchRequest with search criteria
            filename: Custom filename (optional)
            
        Returns:
            ExportMetadata with file information
        """
        if not EXCEL_AVAILABLE:
            raise ExportError(
                "Excel export not available. Install openpyxl: pip install openpyxl"
            )
        
        try:
            # Fetch data
            result = self.search_service.search_accounts(filters)
            
            if not result['results']:
                raise ExportError("No accounts found matching the criteria")
            
            # Generate filename
            if not filename:
                filename = self._generate_filename(
                    prefix="accounts",
                    filters=None,
                    extension="xlsx"
                )
            
            filepath = os.path.join(self.config.output_dir, filename)
            
            # Create workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "Accounts"
            
            # Convert to DataFrame
            df = pd.DataFrame(result['results'])
            
            # Select columns
            columns = [
                'account_id', 'name', 'account_type', 'balance',
                'currency', 'is_active', 'description', 'created_at'
            ]
            columns = [col for col in columns if col in df.columns]
            df = df[columns]
            
            # Write data with formatting
            self._write_dataframe_to_sheet(ws, df, "Account List")
            
            # Add summary section
            self._add_account_summary_section(ws, result['summary'], len(df) + 3)
            
            # Save workbook
            wb.save(filepath)
            
            # Create metadata
            metadata = self._create_metadata(
                filename=filename,
                filepath=filepath,
                format="excel",
                record_count=len(result['results']),
                filters={"account_filters": "applied"}
            )
            
            return metadata
            
        except Exception as e:
            raise ExportError(f"Account Excel export failed: {str(e)}")
    
    def export_monthly_report_excel(
        self,
        year: int,
        month: int,
        filename: Optional[str] = None
    ) -> ExportMetadata:
        """
        Generate comprehensive monthly report in Excel format.
        
        Args:
            year: Year (e.g., 2024)
            month: Month (1-12)
            filename: Custom filename (optional)
            
        Returns:
            ExportMetadata with file information
            
        Features:
            - Summary sheet with key metrics
            - Daily breakdown with trends
            - Category analysis with charts
            - Account balances
            - Professional formatting
        """
        if not EXCEL_AVAILABLE:
            raise ExportError(
                "Excel export not available. Install openpyxl: pip install openpyxl"
            )
        
        try:
            # Calculate date range
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year, 12, 31)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)
            # Fetch transactions
            tx_filters = TransactionSearchRequest(
                date=DateFilter(start_date=start_date, end_date=end_date),
                sort=SortOptions(sort_by="transaction_date", sort_order="ASC")
            )
            tx_result = self.search_service.search_transactions(tx_filters)
            
            # Fetch accounts
            acc_filters = AccountSearchRequest(
                status=StatusFilter(active_only=True)
            )
            acc_result = self.search_service.search_accounts(acc_filters)
            
            # Generate filename
            if not filename:
                filename = f"monthly_report_{year}_{month:02d}.xlsx"
            
            filepath = os.path.join(self.config.output_dir, filename)
            
            # Create workbook
            wb = Workbook()
            
            # Remove default sheet
            if 'Sheet' in wb.sheetnames:
                wb.remove(wb['Sheet'])
            
            # Create overview sheet
            self._create_monthly_overview_sheet(
                wb, tx_result, acc_result, year, month
            )
            
            # Create transaction details
            if tx_result['results']:
                self._create_transactions_sheet(wb, tx_result['results'])
                self._create_category_breakdown_sheet(wb, tx_result['results'])
                self._create_daily_breakdown_sheet(wb, tx_result['results'])
            
            # Add charts
            if self.config.excel_include_charts:
                self._add_monthly_report_charts(wb, tx_result['results'])
            
            # Save workbook
            wb.save(filepath)
            
            # Create metadata
            metadata = self._create_metadata(
                filename=filename,
                filepath=filepath,
                format="excel",
                record_count=len(tx_result['results']) if tx_result['results'] else 0,
                filters={"month": f"{year}-{month:02d}"}
            )
            
            return metadata
            
        except Exception as e:
            raise ExportError(f"Monthly Excel report failed: {str(e)}")
    
    # ================================================================
    # SPECIALIZED REPORTS
    # ================================================================
    
    def export_monthly_report(
        self,
        year: int,
        month: int,
        format: str = "both"  # 'csv', 'pdf', or 'both'
    ) -> Union[ExportMetadata, List[ExportMetadata]]:
        """
        Generate monthly transaction report.
        
        Args:
            year: Year (e.g., 2024)
            month: Month (1-12)
            format: Export format ('csv', 'pdf', or 'both')
            
        Returns:
            ExportMetadata or list of ExportMetadata objects
        """
        try:
            # Calculate date range
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year, 12, 31)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)
            
            # Create filters
            filters = TransactionSearchRequest(
                date=DateFilter(start_date=start_date, end_date=end_date),
                sort=SortOptions(sort_by="transaction_date", sort_order="ASC")
            )
            
            results = []
            
            if format in ['csv', 'both']:
                csv_meta = self.export_transactions_csv(
                    filters,
                    filename=f"monthly_report_{year}_{month:02d}.csv",
                    group_by="category"
                )
                results.append(csv_meta)
            
            if format in ['pdf', 'both']:
                pdf_meta = self.export_transactions_pdf(
                    filters,
                    filename=f"monthly_report_{year}_{month:02d}.pdf",
                    title=f"Monthly Report - {start_date.strftime('%B %Y')}",
                    group_by="category"
                )
                results.append(pdf_meta)
            
            return results if len(results) > 1 else results[0]
            
        except Exception as e:
            raise ExportError(f"Monthly report generation failed: {str(e)}")
    
    def export_weekly_report(
        self,
        year: int,
        week: int,
        format: str = "both"
    ) -> Union[ExportMetadata, List[ExportMetadata]]:
        """
        Generate weekly transaction report.
        
        Args:
            year: Year (e.g., 2024)
            week: ISO week number (1-53)
            format: Export format ('csv', 'pdf', or 'both')
            
        Returns:
            ExportMetadata or list of ExportMetadata objects
        """
        try:
            # Calculate date range from ISO week
            jan_4 = date(year, 1, 4)
            week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
            start_date = week_1_monday + timedelta(weeks=week - 1)
            end_date = start_date + timedelta(days=6)
            
            # Create filters
            filters = TransactionSearchRequest(
                date=DateFilter(start_date=start_date, end_date=end_date),
                sort=SortOptions(sort_by="transaction_date", sort_order="ASC")
            )
            
            results = []
            
            if format in ['csv', 'both']:
                csv_meta = self.export_transactions_csv(
                    filters,
                    filename=f"weekly_report_{year}_W{week:02d}.csv",
                    group_by="date"
                )
                results.append(csv_meta)
            
            if format in ['pdf', 'both']:
                pdf_meta = self.export_transactions_pdf(
                    filters,
                    filename=f"weekly_report_{year}_W{week:02d}.pdf",
                    title=f"Weekly Report - Week {week}, {year}",
                    group_by="date"
                )
                results.append(pdf_meta)
            
            return results if len(results) > 1 else results[0]
            
        except Exception as e:
            raise ExportError(f"Weekly report generation failed: {str(e)}")
    
    def export_daily_report(
        self,
        target_date: Union[str, date],
        format: str = "both"
    ) -> Union[ExportMetadata, List[ExportMetadata]]:
        """
        Generate daily transaction report.
        
        Args:
            target_date: Date to report on
            format: Export format ('csv', 'pdf', or 'both')
            
        Returns:
            ExportMetadata or list of ExportMetadata objects
        """
        try:
            # Parse date
            if isinstance(target_date, str):
                target_date = DateRangeValidator.parse_date(target_date)
            
            # Create filters
            filters = TransactionSearchRequest(
                date=DateFilter(start_date=target_date, end_date=target_date),
                sort=SortOptions(sort_by="created_at", sort_order="ASC")
            )
            
            results = []
            date_str = target_date.strftime("%Y-%m-%d")
            
            if format in ['csv', 'both']:
                csv_meta = self.export_transactions_csv(
                    filters,
                    filename=f"daily_report_{date_str}.csv"
                )
                results.append(csv_meta)
            
            if format in ['pdf', 'both']:
                pdf_meta = self.export_transactions_pdf(
                    filters,
                    filename=f"daily_report_{date_str}.pdf",
                    title=f"Daily Report - {target_date.strftime('%B %d, %Y')}"
                )
                results.append(pdf_meta)
            
            return results if len(results) > 1 else results[0]
            
        except Exception as e:
            raise ExportError(f"Daily report generation failed: {str(e)}")
    
    def export_category_analysis(
        self,
        category_name: str,
        date_preset: str = "last_30_days",
        format: str = "both"
    ) -> Union[ExportMetadata, List[ExportMetadata]]:
        """
        Generate category spending analysis report.
        
        Args:
            category_name: Category to analyze
            date_preset: Date range preset
            format: Export format ('csv', 'pdf', or 'both')
            
        Returns:
            ExportMetadata or list of ExportMetadata objects
        """
        try:
            # Create filters
            filters = TransactionSearchRequest(
                category=CategoryFilter(
                    category_names=[category_name],
                    include_subcategories=True
                ),
                date=DateFilter(date_preset=date_preset),
                sort=SortOptions(sort_by="transaction_date", sort_order="DESC")
            )
            
            results = []
            safe_category = category_name.replace(" ", "_").lower()
            
            if format in ['csv', 'both']:
                csv_meta = self.export_transactions_csv(
                    filters,
                    filename=f"category_{safe_category}_{date_preset}.csv"
                )
                results.append(csv_meta)
            
            if format in ['pdf', 'both']:
                pdf_meta = self.export_transactions_pdf(
                    filters,
                    filename=f"category_{safe_category}_{date_preset}.pdf",
                    title=f"Category Analysis: {category_name}"
                )
                results.append(pdf_meta)
            
            return results if len(results) > 1 else results[0]
            
        except Exception as e:
            raise ExportError(f"Category analysis generation failed: {str(e)}")
    
    # ================================================================
    # HELPER METHODS
    # ================================================================
    
    def _apply_grouping(self, df: pd.DataFrame, group_by: str) -> pd.DataFrame:
        """
        Apply grouping to DataFrame.
        
        Args:
            df: Input DataFrame
            group_by: Grouping key ('category', 'account', 'date', 'month', 'week')
            
        Returns:
            Grouped DataFrame
        """
        if group_by == 'category':
            grouped = df.groupby('category_name').agg({
                'amount': ['sum', 'count', 'mean'],
                'transaction_id': 'count'
            }).round(2)
            grouped.columns = ['Total Amount', 'Transaction Count', 'Average Amount', 'ID Count']
            return grouped.reset_index()
        
        elif group_by == 'account':
            grouped = df.groupby('account_name').agg({
                'amount': ['sum', 'count'],
                'transaction_id': 'count'
            }).round(2)
            grouped.columns = ['Total Amount', 'Transaction Count', 'ID Count']
            return grouped.reset_index()
        
        elif group_by == 'date':
            df['transaction_date'] = pd.to_datetime(df['transaction_date'])
            grouped = df.groupby(df['transaction_date'].dt.date).agg({
                'amount': ['sum', 'count']
            }).round(2)
            grouped.columns = ['Total Amount', 'Transaction Count']
            return grouped.reset_index()
        
        elif group_by == 'month':
            df['transaction_date'] = pd.to_datetime(df['transaction_date'])
            df['month'] = df['transaction_date'].dt.to_period('M')
            grouped = df.groupby('month').agg({
                'amount': ['sum', 'count']
            }).round(2)
            grouped.columns = ['Total Amount', 'Transaction Count']
            return grouped.reset_index()
        
        elif group_by == 'week':
            df['transaction_date'] = pd.to_datetime(df['transaction_date'])
            df['week'] = df['transaction_date'].dt.to_period('W')
            grouped = df.groupby('week').agg({
                'amount': ['sum', 'count']
            }).round(2)
            grouped.columns = ['Total Amount', 'Transaction Count']
            return grouped.reset_index()
        
        return df
    
    