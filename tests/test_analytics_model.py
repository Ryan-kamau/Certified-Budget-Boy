"""
Interactive Analytics Model Tester

A menu-driven test interface for the AnalyticsModel module.
Tests all analytics functionality through a simple CLI menu.

TODO: Update the following before running:
1. Import paths if your structure is different (line 9-12)
"""

from pprint import pprint
from datetime import date, datetime

# ============================================================================
# TODO: UPDATE THESE IMPORTS BASED ON YOUR PROJECT STRUCTURE
# ============================================================================
from core.database import DatabaseConnection
from models.user_model import UserModel
from models.analytics_model import AnalyticsModel  # TODO: Update path if needed


def print_menu():
    """Display the main menu"""
    print("\n📈 ANALYTICS MODEL TEST MENU")
    print("=" * 60)
    print("REPORTS:")
    print("  1. Financial summary (income vs expenses)")
    print("  2. Top categories by spend / income")
    print("  3. Trends over time (daily/weekly/monthly/yearly)")
    print("  4. Payment method breakdown")
    print()
    print("COMPARISONS:")
    print("  5. Monthly comparison (full year view)")
    print("  6. Daily spending (date range)")
    print()
    print("  7. Exit")
    print("=" * 60)


def _ask_date(prompt: str, required: bool = False):
    """
    Prompt for an optional date (YYYY-MM-DD).
    Returns a date object or None if blank and not required.
    """
    while True:
        raw = input(prompt).strip()
        if not raw:
            if required:
                print("⚠️  This field is required.")
                continue
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("⚠️  Invalid date format. Use YYYY-MM-DD.")


def _ask_global_view(role: str) -> bool:
    """
    Ask admin users whether they want global view.
    Regular users always get False.
    """
    if role != "admin":
        return False
    raw = input("Global view? (y/n, default n): ").strip().lower()
    return raw == "y"


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
    analytics = AnalyticsModel(conn, current_user)

    print(f"\n✅ Logged in as: {current_user.get('username')} (ID: {current_user.get('user_id')})")
    print(f"✅ Role: {current_user.get('role')}")
    print("✅ AnalyticsModel ready.")

    role = current_user.get("role")

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
            # 1. FINANCIAL SUMMARY
            # ================================================================
            if choice == 1:
                print("\n📊 FINANCIAL SUMMARY")
                print("-" * 60)

                start_date  = _ask_date("Start date (YYYY-MM-DD, blank for all time): ")
                end_date    = _ask_date("End date   (YYYY-MM-DD, blank for all time): ")
                global_view = _ask_global_view(role)

                result = analytics.summary(
                    start_date=start_date,
                    end_date=end_date,
                    global_view=global_view,
                )

                print("\n✅ Financial Summary:")
                print("-" * 60)
                period = result["period"]
                print(f"  Period          : {period['start'] or 'all time'} → {period['end'] or 'all time'}")
                print(f"  Transactions    : {result['transaction_count']}")
                print()
                print(f"  💰 Total Income      : {result['total_income']:,.2f}")
                print(f"  💸 Total Expenses    : {result['total_expenses']:,.2f}")
                print(f"  📥 Debt Borrowed     : {result['total_debt_in']:,.2f}")
                print(f"  📤 Debt Repaid       : {result['total_debt_out']:,.2f}")
                print(f"  📈 Invested          : {result['total_invested']:,.2f}")
                print(f"  📉 Withdrawn         : {result['total_withdrawn']:,.2f}")
                print()
                print(f"  🔢 Net Cash Flow     : {result['net_cash_flow']:,.2f}")
                print(f"  💼 Savings Rate      : {result['savings_rate']}%")

            # ================================================================
            # 2. TOP CATEGORIES
            # ================================================================
            elif choice == 2:
                print("\n🏆 TOP CATEGORIES")
                print("-" * 60)

                print("\nAvailable transaction types:")
                print("  income | expense | transfer | debt_borrowed |")
                print("  debt_repaid | investment_deposit | investment_withdraw")

                tx_type     = input("\nTransaction type (default expense): ").strip() or "expense"
                limit_raw   = input("How many categories? (default 10): ").strip()
                limit       = int(limit_raw) if limit_raw else 50
                start_date  = _ask_date("Start date (YYYY-MM-DD, blank for all time): ")
                end_date    = _ask_date("End date   (YYYY-MM-DD, blank for all time): ")
                global_view = _ask_global_view(role)

                result = analytics.top_categories(
                    transaction_type=tx_type,
                    limit=limit,
                    start_date=start_date,
                    end_date=end_date,
                    global_view=global_view,
                )

                print(f"\n✅ Top {len(result)} categories for '{tx_type}':")
                print("-" * 60)

                if not result:
                    print("  No data found.")
                else:
                    for i, cat in enumerate(result, 1):
                        print(f"  {i:>2}. {cat['category_name']:<30} "
                              f"Total: {cat['total']:>12,.2f}  "
                              f"({cat['percentage']}%)  "
                              f"Txns: {cat['count']}")

            # ================================================================
            # 3. TRENDS OVER TIME
            # ================================================================
            elif choice == 3:
                print("\n📉 TRENDS OVER TIME")
                print("-" * 60)

                print("\nAvailable periods:  daily | weekly | monthly | yearly")
                period      = input("Period (default monthly): ").strip() or "monthly"
                start_date  = _ask_date("Start date (YYYY-MM-DD, blank for all time): ")
                end_date    = _ask_date("End date   (YYYY-MM-DD, blank for all time): ")
                global_view = _ask_global_view(role)

                result = analytics.trends(
                    period=period,
                    start_date=start_date,
                    end_date=end_date,
                    global_view=global_view,
                )

                print(f"\n✅ Trends ({period}) — {len(result)} period(s):")
                print("-" * 60)
                print(f"  {'Period':<15} {'Income':>12} {'Expenses':>12} "
                      f"{'Debt In':>10} {'Debt Out':>10} "
                      f"{'Invested':>10} {'Withdrawn':>11} {'Net':>12}")
                print("  " + "-" * 95)

                if not result:
                    print("  No data found.")
                else:
                    for row in result:
                        print(
                            f"  {row['period']:<15} "
                            f"{row['total_income']:>12,.2f} "
                            f"{row['total_expenses']:>12,.2f} "
                            f"{row['total_debt_in']:>10,.2f} "
                            f"{row['total_debt_out']:>10,.2f} "
                            f"{row['total_investment_deposit']:>10,.2f} "
                            f"{row['total_investment_withdrawal']:>11,.2f} "
                            f"{row['net']:>12,.2f}"
                        )

            # ================================================================
            # 4. PAYMENT METHOD BREAKDOWN
            # ================================================================
            elif choice == 4:
                print("\n💳 PAYMENT METHOD BREAKDOWN")
                print("-" * 60)

                print("\nAvailable transaction types:")
                print("  income | expense | transfer | debt_borrowed |")
                print("  debt_repaid | investment_deposit | investment_withdraw")

                tx_type     = input("\nTransaction type (default expense): ").strip() or "expense"
                start_date  = _ask_date("Start date (YYYY-MM-DD, blank for all time): ")
                end_date    = _ask_date("End date   (YYYY-MM-DD, blank for all time): ")
                global_view = _ask_global_view(role)

                result = analytics.payment_method_breakdown(
                    transaction_type=tx_type,
                    start_date=start_date,
                    end_date=end_date,
                    global_view=global_view,
                )

                print(f"\n✅ Payment method breakdown for '{tx_type}':")
                print("-" * 60)

                if not result:
                    print("  No data found.")
                else:
                    for row in result:
                        bar = "█" * int(row["percentage"] / 2)
                        print(f"  {row['payment_method']:<15} "
                              f"Total: {row['total']:>12,.2f}  "
                              f"({row['percentage']:>5.1f}%)  "
                              f"Txns: {row['count']:>4}  {bar}")

            # ================================================================
            # 5. MONTHLY COMPARISON
            # ================================================================
            elif choice == 5:
                print("\n📅 MONTHLY COMPARISON (YEAR VIEW)")
                print("-" * 60)

                year_raw    = input(f"Year (default {date.today().year}): ").strip()
                year        = int(year_raw) if year_raw else date.today().year
                global_view = _ask_global_view(role)

                result = analytics.monthly_comparison(year=year, global_view=global_view)

                print(f"\n✅ Monthly breakdown for {year}:")
                print("-" * 60)
                print(f"  {'Month':<6} {'Income':>12} {'Expenses':>12} "
                      f"{'Debt In':>10} {'Debt Out':>10} "
                      f"{'Invested':>10} {'Withdrawn':>11} {'Net':>12}")
                print("  " + "-" * 87)

                for row in result:
                    net_indicator = "▲" if row["net"] >= 0 else "▼"
                    print(
                        f"  {row['month_label']:<6} "
                        f"{row['total_income']:>12,.2f} "
                        f"{row['total_expenses']:>12,.2f} "
                        f"{row['total_debt_in']:>10,.2f} "
                        f"{row['total_debt_out']:>10,.2f} "
                        f"{row['total_investment_deposit']:>10,.2f} "
                        f"{row['total_investment_withdrawal']:>11,.2f} "
                        f"{net_indicator} {row['net']:>10,.2f}"
                    )

                # Year totals
                total_income   = sum(r["total_income"]   for r in result)
                total_expenses = sum(r["total_expenses"] for r in result)
                total_net      = sum(r["net"]            for r in result)
                print("  " + "-" * 87)
                print(f"  {'TOTAL':<6} {total_income:>12,.2f} {total_expenses:>12,.2f} "
                      f"{'':>10} {'':>10} {'':>10} {'':>11}   {total_net:>10,.2f}")

            # ================================================================
            # 6. DAILY SPENDING
            # ================================================================
            elif choice == 6:
                print("\n📆 DAILY SPENDING")
                print("-" * 60)

                start_date  = _ask_date("Start date (YYYY-MM-DD): ", required=True)
                end_date    = _ask_date("End date   (YYYY-MM-DD): ", required=True)
                global_view = _ask_global_view(role)

                result = analytics.daily_spending(
                    start_date=start_date,
                    end_date=end_date,
                    global_view=global_view,
                )

                print(f"\n✅ Daily spending ({start_date} → {end_date}) — {len(result)} day(s) with data:")
                print("-" * 60)

                if not result:
                    print("  No spending recorded in this range.")
                else:
                    max_total = max(r["total"] for r in result) or 1
                    for row in result:
                        bar_len = int((row["total"] / max_total) * 30)
                        bar = "█" * bar_len
                        print(f"  {row['date']}  {row['total']:>12,.2f}  "
                              f"({row['count']:>2} txn{'s' if row['count'] != 1 else ' '})  {bar}")

                    total_spent = sum(r["total"] for r in result)
                    avg_daily   = total_spent / len(result)
                    print("-" * 60)
                    print(f"  Total spent  : {total_spent:,.2f}")
                    print(f"  Daily average: {avg_daily:,.2f}")

            # ================================================================
            # EXIT
            # ================================================================
            elif choice == 7:
                print("\n👋 Exiting analytics tester.")
                break

            else:
                print("⚠️  Invalid option. Please choose 1-7.")

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
    print("✅ Analytics tester finished.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("📈 ANALYTICS MODEL TESTER")
    print("=" * 60)
    print("\nThis interactive tester allows you to:")
    print("  • View financial summaries (income vs expenses)")
    print("  • Rank top spending/income categories")
    print("  • Analyse trends over daily/weekly/monthly/yearly periods")
    print("  • Break down spending by payment method")
    print("  • Compare month-by-month for a full year")
    print("  • Inspect day-by-day spending over a date range")
    print()

    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()