"""
Interactive Export & Report Tester

A menu-driven test interface for the Export Service.
Tests all export and report generation functionality through a simple CLI menu.
"""

from pprint import pprint
from datetime import datetime, date, timedelta
import os

# ============================================================================
# TODO: UPDATE THESE IMPORTS BASED ON YOUR PROJECT STRUCTURE
# ============================================================================
from fintrack.core.database import DatabaseConnection
from fintrack.models.user_model import UserModel
from fintrack.features.export_reports import (
    ExportService,
    ExportConfig,
    ExportError
)
from fintrack.features.search import (
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


def print_menu():
    """Display the main menu"""
    print("\n📊 EXPORT & REPORT TEST MENU")
    print("=" * 70)
    print("CSV EXPORTS:")
    print("  1. Export all transactions to CSV")
    print("  2. Export filtered transactions to CSV")
    print("  3. Export transactions grouped by category")
    print("  4. Export transactions grouped by month")
    print("  5. Export accounts to CSV")
    print("  6. Export categories to CSV")
    print()
    print("EXCEL EXPORTS:")
    print("  7. Export transactions to Excel (with charts)")
    print("  8. Export accounts to Excel")
    print("  9. Generate monthly report Excel (comprehensive)")
    print()
    print("PDF EXPORTS:")
    print("  10. Export all transactions to PDF")
    print("  11. Export filtered transactions to PDF")
    print("  12. Export account summary to PDF")
    print()
    print("SPECIALIZED REPORTS:")
    print("  13. Generate monthly report (CSV/PDF/Excel)")
    print("  14. Generate weekly report (current week)")
    print("  15. Generate daily report (today)")
    print("  16. Generate category analysis report")
    print("  17. Generate custom date range report")
    print()
    print("UTILITIES:")
    print("  18. List generated exports")
    print("  19. View export metadata")
    print("  20. Clean old exports (>30 days)")
    print()
    print("  21. Exit")
    print("=" * 70)


def format_file_size(bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} TB"


def display_metadata(metadata):
    """Display export metadata in a nice format."""
    print("\n" + "=" * 70)
    print("✅ EXPORT SUCCESSFUL")
    print("=" * 70)
    print(f"📁 Filename:      {metadata.filename}")
    print(f"📂 Location:     {metadata.filepath}")
    print(f"📄 Format:       {metadata.format.upper()}")
    print(f"📊 Records:      {metadata.record_count}")
    print(f"📅 Date Range:   {metadata.date_range}")
    print(f"⏰ Generated:    {metadata.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💾 File Size:    {format_file_size(metadata.file_size_bytes)}")
    print("=" * 70)


def list_exports(export_service):
    """List all exports in the output directory."""
    export_dir = export_service.config.output_dir
    
    if not os.path.exists(export_dir):
        print(f"\n⚠️  Export directory not found: {export_dir}")
        return
    
    files = sorted(os.listdir(export_dir), reverse=True)
    
    if not files:
        print(f"\n📭 No exports found in {export_dir}")
        return
    
    print(f"\n📂 EXPORTS IN {export_dir}")
    print("=" * 70)
    
    csv_files = [f for f in files if f.endswith('.csv')]
    pdf_files = [f for f in files if f.endswith('.pdf')]
    excel_files = [f for f in files if f.endswith('.xlsx')]
    
    if csv_files:
        print("\n📄 CSV Files:")
        for i, filename in enumerate(csv_files[:20], 1):  # Show first 20
            filepath = os.path.join(export_dir, filename)
            size = os.path.getsize(filepath)
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            print(f"  {i:2d}. {filename}")
            print(f"      Size: {format_file_size(size)} | Modified: {mtime.strftime('%Y-%m-%d %H:%M')}")
        
        if len(csv_files) > 20:
            print(f"\n  ... and {len(csv_files) - 20} more CSV files")
    
    if pdf_files:
        print("\n📕 PDF Files:")
        for i, filename in enumerate(pdf_files[:20], 1):  # Show first 20
            filepath = os.path.join(export_dir, filename)
            size = os.path.getsize(filepath)
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            print(f"  {i:2d}. {filename}")
            print(f"      Size: {format_file_size(size)} | Modified: {mtime.strftime('%Y-%m-%d %H:%M')}")
        
        if len(pdf_files) > 20:
            print(f"\n  ... and {len(pdf_files) - 20} more PDF files")
    
    if excel_files:
        print("\n📗 Excel Files:")
        for i, filename in enumerate(excel_files[:20], 1):  # Show first 20
            filepath = os.path.join(export_dir, filename)
            size = os.path.getsize(filepath)
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            print(f"  {i:2d}. {filename}")
            print(f"      Size: {format_file_size(size)} | Modified: {mtime.strftime('%Y-%m-%d %H:%M')}")
        
        if len(excel_files) > 20:
            print(f"\n  ... and {len(excel_files) - 20} more Excel files")
    
    print("=" * 70)
    print(f"Total: {len(csv_files)} CSV, {len(excel_files)} Excel, {len(pdf_files)} PDF")


def clean_old_exports(export_service, days=30):
    """Clean exports older than specified days."""
    export_dir = export_service.config.output_dir
    
    if not os.path.exists(export_dir):
        print(f"\n⚠️  Export directory not found: {export_dir}")
        return
    
    cutoff_date = datetime.now() - timedelta(days=days)
    deleted_count = 0
    deleted_size = 0
    
    for filename in os.listdir(export_dir):
        filepath = os.path.join(export_dir, filename)
        
        if os.path.isfile(filepath):
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            if mtime < cutoff_date:
                file_size = os.path.getsize(filepath)
                os.remove(filepath)
                deleted_count += 1
                deleted_size += file_size
                print(f"🗑️  Deleted: {filename} ({format_file_size(file_size)})")
    
    if deleted_count > 0:
        print(f"\n✅ Cleaned {deleted_count} files, freed {format_file_size(deleted_size)}")
    else:
        print(f"\n✨ No files older than {days} days found")


def main():
    """Main tester loop"""
    
    # ----------------------------
    # DB & Authentication
    # ----------------------------
    print("\n🔐 AUTHENTICATION")
    print("=" * 70)
    
    db = DatabaseConnection()
    conn = db.get_connection()

    if not conn:
        print("❌ Could not establish database connection.")
        return

    username = input("Username: ").strip()
    password = input("Password: ").strip()

    um = UserModel(conn)
    auth = um.authenticate(username, password)

    if not auth.get("success"):
        print(f"❌ {auth.get('message')}")
        return

    current_user = auth["user"]
    
    # Configure export service
    config = ExportConfig(
        output_dir="reports/exports",
        include_summary=True
    )
    
    export_service = ExportService(conn, current_user, config)

    print(f"\n✅ Logged in as: {current_user.get('username')} (ID: {current_user.get('user_id')})")
    print(f"✅ Role: {current_user.get('role')}")
    print(f"✅ Export directory: {config.output_dir}")
    print("✅ ExportService ready.")

    # ----------------------------
    # Menu loop
    # ----------------------------
    while True:
        print_menu()

        try:
            choice = int(input("\n👉 Enter choice: "))
        except ValueError:
            print("⚠️  Invalid input. Please enter a number.")
            continue

        try:
            # ================================================================
            # CSV EXPORTS
            # ================================================================
            
            # ----------------------------
            # 1. EXPORT ALL TRANSACTIONS
            # ----------------------------
            if choice == 1:
                print("\n📄 EXPORT ALL TRANSACTIONS TO CSV")
                print("-" * 70)
                
                confirm = input("This may take a while for large datasets. Continue? (y/n): ")
                if confirm.lower() != 'y':
                    continue
                
                filters = TransactionSearchRequest(
                    sort=SortOptions(sort_by="transaction_date", sort_order="DESC")
                )
                
                print("\n⏳ Exporting...")
                metadata = export_service.export_transactions_csv(filters)
                display_metadata(metadata)

            # ----------------------------
            # 2. EXPORT FILTERED TRANSACTIONS
            # ----------------------------
            elif choice == 2:
                print("\n📄 EXPORT FILTERED TRANSACTIONS TO CSV")
                print("-" * 70)
                
                print("\nFilter options (leave blank to skip):")
                search_text = input("Search text: ").strip() or None
                
                print("\nDate preset (today/this_week/this_month/last_30_days):")
                date_preset = input("Preset: ").strip() or None
                
                print("\nTransaction types (comma-separated):")
                print("  Options: income, expense, transfer")
                trans_types = input("Types: ").strip()
                trans_types = [t.strip() for t in trans_types.split(',')] if trans_types else None
                
                filters = TransactionSearchRequest(
                    text=TextSearchFilter(search_text=search_text),
                    date=DateFilter(date_preset=date_preset) if date_preset else DateFilter(),
                    tx_type=TransactionTypeFilter(transaction_types=trans_types),
                    sort=SortOptions(sort_by="transaction_date", sort_order="DESC")
                )
                
                print("\n⏳ Exporting...")
                metadata = export_service.export_transactions_csv(filters)
                display_metadata(metadata)

            # ----------------------------
            # 3. EXPORT GROUPED BY CATEGORY
            # ----------------------------
            elif choice == 3:
                print("\n📄 EXPORT TRANSACTIONS GROUPED BY CATEGORY")
                print("-" * 70)
                
                date_preset = input("Date range (this_month/last_30_days/this_year): ").strip() or "this_month"
                
                filters = TransactionSearchRequest(
                    date=DateFilter(date_preset=date_preset),
                    sort=SortOptions(sort_by="transaction_date", sort_order="DESC")
                )
                
                print("\n⏳ Exporting...")
                metadata = export_service.export_transactions_csv(
                    filters,
                    group_by="category"
                )
                display_metadata(metadata)

            # ----------------------------
            # 4. EXPORT GROUPED BY MONTH
            # ----------------------------
            elif choice == 4:
                print("\n📄 EXPORT TRANSACTIONS GROUPED BY MONTH")
                print("-" * 70)
                
                year = input("Year (e.g., 2024): ").strip()
                if year:
                    filters = TransactionSearchRequest(
                        date=DateFilter(
                            start_date=f"{year}-01-01",
                            end_date=f"{year}-12-31"
                        )
                    )
                else:
                    filters = TransactionSearchRequest()
                
                print("\n⏳ Exporting...")
                metadata = export_service.export_transactions_csv(
                    filters,
                    group_by="month"
                )
                display_metadata(metadata)

            # ----------------------------
            # 5. EXPORT ACCOUNTS
            # ----------------------------
            elif choice == 5:
                print("\n📄 EXPORT ACCOUNTS TO CSV")
                print("-" * 70)
                
                active_only = input("Active accounts only? (y/n): ").strip().lower() == 'y'
                
                filters = AccountSearchRequest(
                    status=StatusFilter(active_only=active_only),
                    sort=SortOptions(sort_by="balance", sort_order="DESC")
                )
                
                print("\n⏳ Exporting...")
                metadata = export_service.export_accounts_csv(filters)
                display_metadata(metadata)

            # ----------------------------
            # 6. EXPORT CATEGORIES
            # ----------------------------
            elif choice == 6:
                print("\n📄 EXPORT CATEGORIES TO CSV")
                print("-" * 70)
                
                filters = CategorySearchRequest(
                    sort=SortOptions(sort_by="name", sort_order="ASC")
                )
                
                print("\n⏳ Exporting...")
                metadata = export_service.export_categories_csv(filters)
                display_metadata(metadata)

            # ================================================================
            # EXCEL EXPORTS
            # ================================================================
            
            # ----------------------------
            # 7. EXPORT TRANSACTIONS TO EXCEL
            # ----------------------------
            elif choice == 7:
                print("\n📗 EXPORT TRANSACTIONS TO EXCEL (WITH CHARTS)")
                print("-" * 70)
                
                date_preset = input("Date range (this_month/last_30_days/this_year): ").strip() or "this_month"
                include_charts = input("Include charts? (y/n): ").strip().lower() == 'y'
                
                filters = TransactionSearchRequest(
                    date=DateFilter(date_preset=date_preset),
                    sort=SortOptions(sort_by="transaction_date", sort_order="DESC")
                )
                
                print("\n⏳ Generating Excel file with multiple sheets...")
                metadata = export_service.export_transactions_excel(
                    filters,
                    include_summary=True,
                    include_charts=include_charts
                )
                display_metadata(metadata)
                print("\n📋 Sheets included: Transactions, Summary, By Category")
                if include_charts:
                    print("📊 Charts: Category pie chart, category bar chart")

            # ----------------------------
            # 8. EXPORT ACCOUNTS TO EXCEL
            # ----------------------------
            elif choice == 8:
                print("\n📗 EXPORT ACCOUNTS TO EXCEL")
                print("-" * 70)
                
                active_only = input("Active accounts only? (y/n): ").strip().lower() == 'y'
                
                filters = AccountSearchRequest(
                    status=StatusFilter(active_only=active_only),
                    sort=SortOptions(sort_by="balance", sort_order="DESC")
                )
                
                print("\n⏳ Generating Excel file...")
                metadata = export_service.export_accounts_excel(filters)
                display_metadata(metadata)

            # ----------------------------
            # 9. MONTHLY REPORT EXCEL
            # ----------------------------
            elif choice == 9:
                print("\n📗 GENERATE COMPREHENSIVE MONTHLY EXCEL REPORT")
                print("-" * 70)
                
                now = datetime.now()
                year = int(input(f"Year (default: {now.year}): ").strip() or now.year)
                month = int(input(f"Month (default: {now.month}): ").strip() or now.month)
                
                print("\n⏳ Generating comprehensive monthly report...")
                print("   This includes: Overview, Transactions, By Category, Daily Breakdown")
                metadata = export_service.export_monthly_report_excel(year, month)
                display_metadata(metadata)
                print("\n📋 Sheets included:")
                print("   • Overview (with charts)")
                print("   • Transactions (detailed list)")
                print("   • By Category (with totals)")
                print("   • Daily Breakdown (day-by-day)")

            # ================================================================
            # PDF EXPORTS
            # ================================================================
            
            # ----------------------------
            # 10. EXPORT ALL TRANSACTIONS PDF
            # ----------------------------
            elif choice == 10:
                print("\n📕 EXPORT ALL TRANSACTIONS TO PDF")
                print("-" * 70)
                
                limit = input("Limit to how many transactions? (default: 1000): ").strip()
                limit = int(limit) if limit else 1000
                
                filters = TransactionSearchRequest(
                    sort=SortOptions(sort_by="transaction_date", sort_order="DESC"),
                    pagination=Pagination(page_size=limit)
                )
                
                print("\n⏳ Generating PDF...")
                metadata = export_service.export_transactions_pdf(
                    filters,
                    title="Complete Transaction Report"
                )
                display_metadata(metadata)

            # ----------------------------
            # 11. EXPORT FILTERED TRANSACTIONS PDF
            # ----------------------------
            elif choice == 11:
                print("\n📕 EXPORT FILTERED TRANSACTIONS TO PDF")
                print("-" * 70)
                
                date_preset = input("Date preset (this_month/last_30_days): ").strip() or "this_month"
                
                print("\nTransaction type (income/expense/transfer):")
                trans_type = input("Type: ").strip() or None
                trans_types = [trans_type] if trans_type else None
                
                filters = TransactionSearchRequest(
                    date=DateFilter(date_preset=date_preset),
                    tx_type=TransactionTypeFilter(transaction_types=trans_types),
                    sort=SortOptions(sort_by="transaction_date", sort_order="DESC")
                )
                
                print("\n⏳ Generating PDF...")
                metadata = export_service.export_transactions_pdf(
                    filters,
                    title=f"Transaction Report - {date_preset.replace('_', ' ').title()}"
                )
                display_metadata(metadata)

            # ----------------------------
            # 12. EXPORT ACCOUNT SUMMARY PDF
            # ----------------------------
            elif choice == 12:
                print("\n📕 EXPORT ACCOUNT SUMMARY TO PDF")
                print("-" * 70)
                
                filters = AccountSearchRequest(
                    status=StatusFilter(active_only=True),
                    sort=SortOptions(sort_by="balance", sort_order="DESC")
                )
                
                print("\n⏳ Generating PDF...")
                metadata = export_service.export_account_summary_pdf(filters)
                display_metadata(metadata)

            # ================================================================
            # SPECIALIZED REPORTS
            # ================================================================
            
            # ----------------------------
            # 13. MONTHLY REPORT
            # ----------------------------
            elif choice == 13:
                print("\n📊 GENERATE MONTHLY REPORT")
                print("-" * 70)
                
                now = datetime.now()
                year = int(input(f"Year (default: {now.year}): ").strip() or now.year)
                month = int(input(f"Month (default: {now.month}): ").strip() or now.month)
                
                print("\nFormat options:")
                print("  csv   - CSV only")
                print("  pdf   - PDF only")
                print("  excel - Excel only (with charts and multiple sheets)")
                print("  all   - Generate all formats")
                format_choice = input("Format (csv/pdf/excel/all, default: all): ").strip() or "all"
                
                print("\n⏳ Generating monthly report...")
                
                if format_choice == "excel":
                    metadata = export_service.export_monthly_report_excel(year, month)
                    display_metadata(metadata)
                elif format_choice == "all":
                    # CSV and PDF
                    result = export_service.export_monthly_report(year, month, "both")
                    if isinstance(result, list):
                        for metadata in result:
                            display_metadata(metadata)
                    else:
                        display_metadata(result)
                    # Excel
                    metadata = export_service.export_monthly_report_excel(year, month)
                    display_metadata(metadata)
                else:
                    result = export_service.export_monthly_report(year, month, format_choice)
                    if isinstance(result, list):
                        for metadata in result:
                            display_metadata(metadata)
                    else:
                        display_metadata(result)

            # ----------------------------
            # 14. WEEKLY REPORT
            # ----------------------------
            elif choice == 14:
                print("\n📊 GENERATE WEEKLY REPORT")
                print("-" * 70)
                
                now = datetime.now()
                year = int(input(f"Year (default: {now.year}): ").strip() or now.year)
                week = int(input(f"ISO Week number (default: {now.isocalendar()[1]}): ").strip() or now.isocalendar()[1])
                
                format_choice = input("Format (csv/pdf/both, default: both): ").strip() or "both"
                
                print("\n⏳ Generating weekly report...")
                result = export_service.export_weekly_report(year, week, format_choice)
                
                if isinstance(result, list):
                    for metadata in result:
                        display_metadata(metadata)
                else:
                    display_metadata(result)

            # ----------------------------
            # 15. DAILY REPORT
            # ----------------------------
            elif choice == 15:
                print("\n📊 GENERATE DAILY REPORT")
                print("-" * 70)
                
                date_str = input("Date (YYYY-MM-DD, default: today): ").strip()
                target_date = date_str if date_str else date.today()
                
                format_choice = input("Format (csv/pdf/both, default: both): ").strip() or "both"
                
                print("\n⏳ Generating daily report...")
                result = export_service.export_daily_report(target_date, format_choice)
                
                if isinstance(result, list):
                    for metadata in result:
                        display_metadata(metadata)
                else:
                    display_metadata(result)

            # ----------------------------
            # 16. CATEGORY ANALYSIS
            # ----------------------------
            elif choice == 16:
                print("\n📊 GENERATE CATEGORY ANALYSIS REPORT")
                print("-" * 70)
                
                category_name = input("Category name: ").strip()
                if not category_name:
                    print("⚠️  Category name is required")
                    continue
                
                date_preset = input("Date range (this_month/last_30_days/this_year): ").strip() or "last_30_days"
                format_choice = input("Format (csv/pdf/both, default: both): ").strip() or "both"
                
                print("\n⏳ Generating category analysis...")
                result = export_service.export_category_analysis(
                    category_name,
                    date_preset,
                    format_choice
                )
                
                if isinstance(result, list):
                    for metadata in result:
                        display_metadata(metadata)
                else:
                    display_metadata(result)

            # ----------------------------
            # 17. CUSTOM DATE RANGE REPORT
            # ----------------------------
            elif choice == 17:
                print("\n📊 GENERATE CUSTOM DATE RANGE REPORT")
                print("-" * 70)
                
                start_date = input("Start date (YYYY-MM-DD): ").strip()
                end_date = input("End date (YYYY-MM-DD): ").strip()
                
                if not start_date or not end_date:
                    print("⚠️  Both dates are required")
                    continue
                
                format_choice = input("Format (csv/pdf/both, default: both): ").strip() or "both"
                group_by = input("Group by (category/account/date, or leave blank): ").strip() or None
                
                filters = TransactionSearchRequest(
                    date=DateFilter(start_date=start_date, end_date=end_date),
                    sort=SortOptions(sort_by="transaction_date", sort_order="ASC")
                )
                
                print("\n⏳ Generating custom report...")
                
                if format_choice in ['csv', 'both']:
                    csv_meta = export_service.export_transactions_csv(filters, group_by=group_by)
                    display_metadata(csv_meta)
                
                if format_choice in ['pdf', 'both']:
                    pdf_meta = export_service.export_transactions_pdf(
                        filters,
                        title=f"Report: {start_date} to {end_date}",
                        group_by=group_by
                    )
                    display_metadata(pdf_meta)

            # ================================================================
            # UTILITIES
            # ================================================================
            
            # ----------------------------
            # 18. LIST EXPORTS
            # ----------------------------
            elif choice == 18:
                list_exports(export_service)

            # ----------------------------
            # 19. VIEW METADATA
            # ----------------------------
            elif choice == 19:
                print("\n📋 VIEW EXPORT METADATA")
                print("-" * 70)
                
                filename = input("Enter filename: ").strip()
                filepath = os.path.join(export_service.config.output_dir, filename)
                
                if os.path.exists(filepath):
                    size = os.path.getsize(filepath)
                    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                    
                    print(f"\n📁 File: {filename}")
                    print(f"📂 Path: {filepath}")
                    print(f"💾 Size: {format_file_size(size)}")
                    print(f"⏰ Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    print(f"\n❌ File not found: {filename}")

            # ----------------------------
            # 20. CLEAN OLD EXPORTS
            # ----------------------------
            elif choice == 20:
                print("\n🗑️  CLEAN OLD EXPORTS")
                print("-" * 70)
                
                days = input("Delete files older than how many days? (default: 30): ").strip()
                days = int(days) if days else 30
                
                confirm = input(f"⚠️  Delete exports older than {days} days? (y/n): ")
                if confirm.lower() == 'y':
                    clean_old_exports(export_service, days)

            # ----------------------------
            # EXIT
            # ----------------------------
            elif choice == 21:
                print("\n👋 Exiting export tester.")
                break

            else:
                print("⚠️  Invalid option. Please choose 1-21.")

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user.")
            break
            
        except ExportError as e:
            print(f"\n❌ Export Error: {e}")
            
        except Exception as exc:
            print(f"\n❌ Error: {exc}")
            import traceback
            traceback.print_exc()

    # ----------------------------
    # Cleanup
    # ----------------------------
    conn.close()
    print("\n🔒 Database connection closed.")
    print("✅ Export tester finished.")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("📊 EXPORT & REPORT TESTER")
    print("=" * 70)
    print("\nThis interactive tester allows you to:")
    print("  • Export transactions, accounts, and categories to CSV")
    print("  • Generate formatted PDF reports with summaries")
    print("  • Create specialized reports (monthly, weekly, daily)")
    print("  • Generate category analysis reports")
    print("  • Manage and clean old exports")
    print()
    
    try:
        main()
    except KeyboardInterrupt:          
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()