"""
Interactive Search & Filter Tester

A menu-driven test interface for the Search Service.
Tests all search and filter functionality through a simple CLI menu.

TODO: Update the following before running:
1. Import paths if your structure is different
"""

from pprint import pprint
from datetime import datetime, date, timedelta

# ============================================================================
# TODO: UPDATE THESE IMPORTS BASED ON YOUR PROJECT STRUCTURE
# ============================================================================
from core.database import DatabaseConnection
from models.user_model import UserModel
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
    Pagination,
    ParentFilter
)


def print_menu():
    """Display the main menu"""
    print("\n🔍 SEARCH & FILTER TEST MENU")
    print("=" * 60)
    print("TRANSACTION SEARCH:")
    print("  1. Search transactions by text")
    print("  2. Search transactions by amount range")
    print("  3. Search transactions by date range")
    print("  4. Search transactions by category")
    print("  5. Search transactions by account")
    print("  6. Advanced transaction search (multi-criteria)")
    print("  7. Search with date presets")
    print()
    print("CATEGORY SEARCH:")
    print("  8. Search categories")
    print("  9. Search categories with hierarchy")
    print()
    print("ACCOUNT SEARCH:")
    print("  10. Search accounts")
    print("  11. Search accounts by balance range")
    print("  12. Find negative balance accounts")
    print()
    print("RECURRING SEARCH:")
    print("  13. Search recurring transactions")
    print("  14. Find overdue recurring transactions")
    print()
    print("  15. Exit")
    print("=" * 60)


def main():
    """Main tester loop"""
    
    # ----------------------------
    # DB & Authentication
    # ----------------------------
    print("\n🔐 AUTHENTICATION")
    print("=" * 60)
    
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
    search_service = SearchService(conn, current_user)

    print(f"\n✅ Logged in as: {current_user.get('username')} (ID: {current_user.get('user_id')})")
    print(f"✅ Role: {current_user.get('role')}")
    print("✅ SearchService ready.")

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
            # TRANSACTION SEARCH
            # ================================================================
            
            # ----------------------------
            # 1. SEARCH BY TEXT
            # ----------------------------
            if choice == 1:
                print("\n📝 SEARCH TRANSACTIONS BY TEXT")
                print("-" * 60)
                
                search_text = input("Enter search text: ").strip()
                
                filters = TransactionSearchRequest(
                    text=TextSearchFilter(search_text=search_text),
                    pagination=Pagination(page_size=20)
                )
                
                result = search_service.search_transactions(filters)
                
                print(f"\n✅ Found {result['count']} transactions (Page {result['pagination']['page']} of {result['pagination']['total_pages']})")
                print("-" * 60)
                
                for tx in result['results'][:10]:  # Show first 10
                    print(f"\n💰 {tx['title']}")
                    print(f"   Amount: {tx['amount']}")
                    print(f"   Date: {tx['transaction_date']}")
                    print(f"   Type: {tx['transaction_type']}")
                    if tx.get('description'):
                        print(f"   Description: {tx['description'][:50]}...")
                
                if result['count'] > 10:
                    print(f"\n... and {result['count'] - 10} more results")
                
                print(f"\n📊 Summary:")
                print(f"   Total Income: {result['summary']['total_income']:.2f}")
                print(f"   Total Expense: {result['summary']['total_expense']:.2f}")
                print(f"   Net: {result['summary']['net_amount']:.2f}")

            # ----------------------------
            # 2. SEARCH BY AMOUNT RANGE
            # ----------------------------
            elif choice == 2:
                print("\n💵 SEARCH TRANSACTIONS BY AMOUNT RANGE")
                print("-" * 60)
                
                min_amount = input("Minimum amount (or leave blank): ").strip()
                max_amount = input("Maximum amount (or leave blank): ").strip()
                
                filters = TransactionSearchRequest(
                    amount=AmountFilter(
                        min_amount=min_amount if min_amount else None,
                        max_amount=max_amount if max_amount else None
                    ),
                    pagination=Pagination(page_size=20)
                )
                
                result = search_service.search_transactions(filters)
                
                print(f"\n✅ Found {result['count']} transactions in range {min_amount or 'Any'} - {max_amount or 'Any'}")
                print("-" * 60)
                
                for tx in result['results'][:10]:
                    print(f"\n💰 {tx['title']}: {tx['amount']:.2f}")
                    print(f"   Date: {tx['transaction_date']}")
                    print(f"   Type: {tx['transaction_type']}")

            # ----------------------------
            # 3. SEARCH BY DATE RANGE
            # ----------------------------
            elif choice == 3:
                print("\n📅 SEARCH TRANSACTIONS BY DATE RANGE")
                print("-" * 60)
                
                start_date = input("Start date (YYYY-MM-DD or leave blank): ").strip()
                end_date = input("End date (YYYY-MM-DD or leave blank): ").strip()
                
                filters = TransactionSearchRequest(
                    date=DateFilter(
                        start_date=start_date if start_date else None,
                        end_date=end_date if end_date else None
                    ),
                    sort=SortOptions(sort_by="transaction_date", sort_order="DESC"),
                    pagination=Pagination(page_size=20)
                )
                
                result = search_service.search_transactions(filters)
                
                print(f"\n✅ Found {result['count']} transactions")
                print(f"Date Range: {result['filters_applied']['date_range']}")
                print("-" * 60)
                
                for tx in result['results'][:10]:
                    print(f"\n📆 {tx['transaction_date']}: {tx['title']}")
                    print(f"   Amount: {tx['amount']:.2f}")
                    print(f"   Type: {tx['transaction_type']}")

            # ----------------------------
            # 4. SEARCH BY CATEGORY
            # ----------------------------
            elif choice == 4:
                print("\n📂 SEARCH TRANSACTIONS BY CATEGORY")
                print("-" * 60)
                
                category_names = input("Category names (comma-separated): ").strip()
                include_subcategories = input("Include subcategories? (y/n): ").strip().lower() == 'y'
                
                if category_names:
                    cat_list = [c.strip() for c in category_names.split(',')]
                    
                    filters = TransactionSearchRequest(
                        category=CategoryFilter(
                            category_names=cat_list,
                            include_subcategories=include_subcategories
                        ),
                        pagination=Pagination(page_size=20)
                    )
                    
                    result = search_service.search_transactions(filters)
                    
                    print(f"\n✅ Found {result['count']} transactions")
                    print("-" * 60)
                    
                    for tx in result['results'][:10]:
                        print(f"\n📁 {tx['category_name'] or 'Uncategorized'}: {tx['title']}")
                        print(f"   Amount: {tx['amount']:.2f}")
                        print(f"   Date: {tx['transaction_date']}")

            # ----------------------------
            # 5. SEARCH BY ACCOUNT
            # ----------------------------
            elif choice == 5:
                print("\n🏦 SEARCH TRANSACTIONS BY ACCOUNT")
                print("-" * 60)
                
                account_ids = input("Account IDs (comma-separated): ").strip()
                
                if account_ids:
                    acc_list = [int(a.strip()) for a in account_ids.split(',')]
                    
                    filters = TransactionSearchRequest(
                        account=AccountFilter(account_ids=acc_list),
                        pagination=Pagination(page_size=20)
                    )
                    
                    result = search_service.search_transactions(filters)
                    
                    print(f"\n✅ Found {result['count']} transactions")
                    print("-" * 60)
                    
                    for tx in result['results'][:10]:
                        account_name = tx.get('account_name') or tx.get('source_account_name') or 'Unknown'
                        print(f"\n💳 {account_name}: {tx['title']}")
                        print(f"   Amount: {tx['amount']:.2f}")
                        print(f"   Type: {tx['transaction_type']}")

            # ----------------------------
            # 6. ADVANCED MULTI-CRITERIA SEARCH
            # ----------------------------
            elif choice == 6:
                print("\n🔬 ADVANCED TRANSACTION SEARCH")
                print("-" * 60)
                print("Enter criteria (leave blank to skip):")
                print()
                
                # Collect all criteria
                search_text = input("Text search: ").strip() or None
                min_amount = input("Min amount: ").strip() or None
                max_amount = input("Max amount: ").strip() or None
                start_date = input("Start date (YYYY-MM-DD): ").strip() or None
                end_date = input("End date (YYYY-MM-DD): ").strip() or None
                
                print("\nTransaction types (comma-separated):")
                print("  Options: income, expense, transfer, debt_borrowed, debt_repaid")
                trans_types = input("Types: ").strip()
                trans_types = [t.strip() for t in trans_types.split(',')] if trans_types else None
                
                print("\nPayment methods (comma-separated):")
                print("  Options: cash, bank, mobile_money, credit_card, other")
                payment_methods = input("Methods: ").strip()
                payment_methods = [p.strip() for p in payment_methods.split(',')] if payment_methods else None
                
                sort_by = input("\nSort by (transaction_date/amount/title): ").strip() or "transaction_date"
                sort_order = input("Sort order (ASC/DESC): ").strip().upper() or "DESC"
                
                filters = TransactionSearchRequest(
                    text=TextSearchFilter(search_text=search_text),
                    amount=AmountFilter(
                        min_amount=min_amount,
                        max_amount=max_amount
                    ),
                    date=DateFilter(
                        start_date=start_date,
                        end_date=end_date
                    ),
                    tx_type=TransactionTypeFilter(
                        transaction_types=trans_types,
                        payment_methods=payment_methods
                    ),
                    sort=SortOptions(sort_by=sort_by, sort_order=sort_order),
                    pagination=Pagination(page_size=20)
                )
                
                result = search_service.search_transactions(filters)
                
                print(f"\n✅ Found {result['count']} transactions matching criteria")
                print("\n📋 Filters Applied:")
                for key, value in result['filters_applied'].items():
                    if value:
                        print(f"   {key}: {value}")
                
                print("\n📊 Summary:")
                for key, value in result['summary'].items():
                    print(f"   {key}: {value}")
                
                print("\n💰 Results:")
                print("-" * 60)
                for tx in result['results'][:10]:
                    print(f"\n{tx['transaction_date']} | {tx['title']}")
                    print(f"   Amount: {tx['amount']:.2f} | Type: {tx['transaction_type']}")
                    print(f"   Payment: {tx['payment_method']}")

            # ----------------------------
            # 7. SEARCH WITH DATE PRESETS
            # ----------------------------
            elif choice == 7:
                print("\n📆 SEARCH WITH DATE PRESETS")
                print("-" * 60)
                print("Available presets:")
                print("  1. today")
                print("  2. yesterday")
                print("  3. this_week")
                print("  4. last_week")
                print("  5. this_month")
                print("  6. last_month")
                print("  7. this_year")
                print("  8. last_year")
                print("  9. last_7_days")
                print("  10. last_30_days")
                print("  11. last_90_days")
                
                preset = input("\nEnter preset name: ").strip()
                
                try:
                    filters = TransactionSearchRequest(
                        date=DateFilter(date_preset=preset),
                        pagination=Pagination(page_size=20)
                    )
                    
                    result = search_service.search_transactions(filters)
                    
                    print(f"\n✅ Found {result['count']} transactions for '{preset}'")
                    print(f"Date Range: {result['filters_applied']['date_range']}")
                    print("-" * 60)
                    
                    print(f"\n📊 Summary:")
                    print(f"   Total Income: {result['summary']['total_income']:.2f}")
                    print(f"   Total Expense: {result['summary']['total_expense']:.2f}")
                    print(f"   Net: {result['summary']['net_amount']:.2f}")
                    
                    if result['results']:
                        print(f"\n💰 Sample Transactions:")
                        for tx in result['results'][:5]:
                            print(f"\n{tx['transaction_date']}: {tx['title']}")
                            print(f"   {tx['amount']:.2f} ({tx['transaction_type']})")
                
                except ValueError as e:
                    print(f"\n❌ Error: {e}")

            # ================================================================
            # CATEGORY SEARCH
            # ================================================================
            
            # ----------------------------
            # 8. SEARCH CATEGORIES
            # ----------------------------
            elif choice == 8:
                print("\n📂 SEARCH CATEGORIES")
                print("-" * 60)
                
                search_text = input("Search text: ").strip() or None
                sort_by = input("Sort by (name/created_at): ").strip() or "name"
                
                filters = CategorySearchRequest(
                    text=TextSearchFilter(search_text=search_text),
                    sort=SortOptions(sort_by=sort_by)
                )
                
                result = search_service.search_categories(filters)
                
                print(f"\n✅ Found {result['count']} categories")
                print("-" * 60)
                
                for cat in result['results']:
                    parent = f" (Parent: {cat.get('parent_id')})" if cat.get('parent_id') else ""
                    print(f"\n📁 {cat['name']}{parent}")
                    if cat.get('description'):
                        print(f"   {cat['description']}")
                    print(f"   Owner: {cat.get('owned_by_username')}")

            # ----------------------------
            # 9. SEARCH CATEGORIES WITH HIERARCHY
            # ----------------------------
            elif choice == 9:
                print("\n🌳 SEARCH CATEGORIES WITH HIERARCHY")
                print("-" * 60)
                
                parent_id = input("Parent category ID (or leave blank for top-level): ").strip()
                parent_id = int(parent_id) if parent_id else None
                
                include_children = input("Include child categories? (y/n): ").strip().lower() == 'y'
                
                filters = CategorySearchRequest(
                    parent=ParentFilter(parent_id=parent_id),
                    status=StatusFilter(include_children=include_children)
                )
                
                result = search_service.search_categories(filters)
                
                print(f"\n✅ Found {result['count']} categories")
                print("-" * 60)
                
                for cat in result['results']:
                    indent = "  " * (cat.get('level', 0) if 'level' in cat else 0)
                    print(f"{indent}📁 {cat['name']}")

            # ================================================================
            # ACCOUNT SEARCH
            # ================================================================
            
            # ----------------------------
            # 10. SEARCH ACCOUNTS
            # ----------------------------
            elif choice == 10:
                print("\n🏦 SEARCH ACCOUNTS")
                print("-" * 60)
                
                search_text = input("Search text: ").strip() or None
                account_types = input("Account types (comma-separated, or leave blank): ").strip()
                account_types = [t.strip() for t in account_types.split(',')] if account_types else None
                
                filters = AccountSearchRequest(
                    text=TextSearchFilter(search_text=search_text),
                    account=AccountFilter(account_types=account_types)
                )
                
                result = search_service.search_accounts(filters)
                
                print(f"\n✅ Found {result['count']} accounts")
                print("-" * 60)
                print(f"📊 Total Balance: {result['summary']['total_balance']:.2f}")
                print(f"📊 Active Accounts: {result['summary']['active_accounts']}")
                print(f"📊 Negative Accounts: {result['summary']['negative_accounts']}")
                
                print("\n💳 Accounts:")
                for acc in result['results']:
                    status = "🟢" if acc['is_active'] else "🔴"
                    print(f"\n{status} {acc['name']}")
                    print(f"   Type: {acc['account_type']}")
                    print(f"   Balance: {acc['balance']:.2f}")

            # ----------------------------
            # 11. SEARCH BY BALANCE RANGE
            # ----------------------------
            elif choice == 11:
                print("\n💰 SEARCH ACCOUNTS BY BALANCE RANGE")
                print("-" * 60)
                
                min_balance = input("Minimum balance: ").strip() or None
                max_balance = input("Maximum balance: ").strip() or None
                
                filters = AccountSearchRequest(
                    amount=AmountFilter(
                        min_amount=min_balance,
                        max_amount=max_balance
                    ),
                    sort=SortOptions(sort_by="balance", sort_order="DESC")
                )
                
                result = search_service.search_accounts(filters)
                
                print(f"\n✅ Found {result['count']} accounts in range")
                print("-" * 60)
                
                for acc in result['results']:
                    print(f"\n💳 {acc['name']}: {acc['balance']:.2f}")
                    print(f"   Type: {acc['account_type']}")

            # ----------------------------
            # 12. FIND NEGATIVE BALANCE ACCOUNTS
            # ----------------------------
            elif choice == 12:
                print("\n🔴 ACCOUNTS WITH NEGATIVE BALANCE")
                print("-" * 60)
                
                filters = AccountSearchRequest(
                    amount=AmountFilter(negative_balance_only=True),
                    sort=SortOptions(sort_by="balance", sort_order="ASC")
                )
                
                result = search_service.search_accounts(filters)
                
                if result['count'] > 0:
                    print(f"\n⚠️  Found {result['count']} accounts with negative balance!")
                    print("-" * 60)
                    
                    for acc in result['results']:
                        print(f"\n🔴 {acc['name']}")
                        print(f"   Balance: {acc['balance']:.2f}")
                        print(f"   Type: {acc['account_type']}")
                else:
                    print("\n✅ No accounts with negative balance found!")

            # ================================================================
            # RECURRING SEARCH
            # ================================================================
            
            # ----------------------------
            # 13. SEARCH RECURRING TRANSACTIONS
            # ----------------------------
            elif choice == 13:
                print("\n🔁 SEARCH RECURRING TRANSACTIONS")
                print("-" * 60)
                
                search_text = input("Search text: ").strip() or None
                frequencies = input("Frequencies (daily/weekly/monthly/yearly, comma-separated): ").strip()
                frequencies = [f.strip() for f in frequencies.split(',')] if frequencies else None
                
                active_only = input("Active only? (y/n): ").strip().lower() == 'y'
                
                filters = RecurringSearchRequest(
                    text=TextSearchFilter(search_text=search_text),
                    frequencies=frequencies,
                    status=StatusFilter(active_only=active_only)
                )
                
                result = search_service.search_recurring(filters)
                
                print(f"\n✅ Found {result['count']} recurring transactions")
                print("-" * 60)
                print(f"📊 Total Active: {result['summary']['total_active']}")
                print(f"📊 Total Paused: {result['summary']['total_paused']}")
                print(f"📊 Total Overdue: {result['summary']['total_overdue']}")
                
                print("\n🔁 Recurring Transactions:")
                for rec in result['results']:
                    status = "✅" if rec['is_active'] else "⏸️"
                    print(f"\n{status} {rec['name']}")
                    print(f"   Amount: {rec['amount']:.2f}")
                    print(f"   Frequency: {rec['frequency']}")
                    print(f"   Next Due: {rec['next_due']}")

            # ----------------------------
            # 14. FIND OVERDUE RECURRING
            # ----------------------------
            elif choice == 14:
                print("\n⚠️  OVERDUE RECURRING TRANSACTIONS")
                print("-" * 60)
                
                filters = RecurringSearchRequest(
                    status=StatusFilter(overdue_only=True),
                    sort=SortOptions(sort_by="next_due", sort_order="ASC")
                )
                
                result = search_service.search_recurring(filters)
                
                if result['count'] > 0:
                    print(f"\n⚠️  Found {result['count']} overdue recurring transactions!")
                    print("-" * 60)
                    
                    for rec in result['results']:
                        days_overdue = (datetime.now().date() - rec['next_due']).days
                        print(f"\n⚠️  {rec['name']}")
                        print(f"   Due: {rec['next_due']} ({days_overdue} days ago)")
                        print(f"   Amount: {rec['amount']:.2f}")
                        print(f"   Frequency: {rec['frequency']}")
                else:
                    print("\n✅ No overdue recurring transactions!")

            # ----------------------------
            # EXIT
            # ----------------------------
            elif choice == 15:
                print("\n👋 Exiting search tester.")
                break

            else:
                print("⚠️  Invalid option. Please choose 1-15.")

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user.")
            break
            
        except Exception as exc:
            print(f"\n❌ Error: {exc}")
            import traceback
            traceback.print_exc()

    # ----------------------------
    # Cleanup
    # ----------------------------
    conn.close()
    print("\n🔒 Database connection closed.")
    print("✅ Search tester finished.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🔍 SEARCH & FILTER TESTER")
    print("=" * 60)
    print("\nThis interactive tester allows you to:")
    print("  • Search transactions by text, amount, date, category, account")
    print("  • Use advanced multi-criteria search")
    print("  • Search with date presets (this_month, last_7_days, etc.)")
    print("  • Search categories with hierarchy support")
    print("  • Search accounts by balance and type")
    print("  • Find overdue recurring transactions")
    print()
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()