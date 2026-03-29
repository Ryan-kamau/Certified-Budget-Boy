"""
Interactive Charts Tester

A menu-driven test interface for the FinanceCharts module.
Tests all chart functionality through a simple CLI menu.

TODO: Update the following before running:
1. Import paths if your structure is different (line 12-13)
"""

from datetime import datetime, date

# ============================================================================
# TODO: UPDATE THESE IMPORTS BASED ON YOUR PROJECT STRUCTURE
# ============================================================================
from fintrack.core.database import DatabaseConnection
from fintrack.models.user_model import UserModel
from fintrack.features.charts import FinanceCharts   # TODO: Update path if needed


# ============================================================================
# Helpers
# ============================================================================

def print_menu():
    """Display the main menu"""
    print("\n📊 FINANCE CHARTS TEST MENU")
    print("=" * 60)
    print("INDIVIDUAL CHARTS:")
    print("  1. Monthly transaction types  (line graph)")
    print("  2. Spending by category       (donut chart)")
    print("  3. Daily spending heatmap     (calendar)")
    print("  4. Net worth over time        (line chart)")
    print()
    print("COMBINED:")
    print("  5. Show all charts (sequentially)")
    print()
    print("  6. Exit")
    print("=" * 60)


def _ask_date(prompt: str) -> date | None:
    """Prompt for an optional date (YYYY-MM-DD). Returns None if blank."""
    while True:
        raw = input(prompt).strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("⚠️  Invalid date format. Use YYYY-MM-DD.")


def _ask_int(prompt: str, default: int) -> int:
    """Prompt for an optional integer with a default fallback."""
    raw = input(prompt).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"⚠️  Invalid number — using default ({default}).")
        return default


# ============================================================================
# Main
# ============================================================================

def main():
    """Main tester loop"""

    # ----------------------------
    # DB & Authentication
    # ----------------------------
    print("\n🔐 AUTHENTICATION")
    print("=" * 60)

    db   = DatabaseConnection()
    conn = db.get_connection()

    if not conn:
        print("❌ Could not establish database connection.")
        return

    username = input("Username: ").strip()
    password = input("Password: ").strip()

    um   = UserModel(conn)
    auth = um.authenticate(username, password)

    if not auth.get("success"):
        print(f"❌ {auth.get('message')}")
        return

    current_user = auth["user"]
    charts = FinanceCharts(conn, current_user)

    print(f"\n✅ Logged in as: {current_user.get('username')} (ID: {current_user.get('user_id')})")
    print(f"✅ Role: {current_user.get('role')}")
    print("✅ FinanceCharts ready.")
    print("\nℹ️  Charts open as pop-up windows. Close each window to continue.")

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
            # 1. MONTHLY TRANSACTION TYPES LINE GRAPH
            # ================================================================
            if choice == 1:
                print("\n📈 MONTHLY TRANSACTION TYPES — LINE GRAPH")
                print("-" * 60)
                print("Shows all transaction types (income, expense, debt, investments, net)")
                print("as individual lines across the 12 months of a year.")
                print()

                year_raw = input("Year (blank = current year): ").strip()
                year     = int(year_raw) if year_raw else None

                print("\n⏳ Rendering chart…")
                charts.monthly_transactions(year=year)
                print("✅ Chart closed.")

            # ================================================================
            # 2. SPENDING BY CATEGORY — DONUT CHART
            # ================================================================
            elif choice == 2:
                print("\n🍩 SPENDING BY CATEGORY — DONUT CHART")
                print("-" * 60)
                print("Shows expense breakdown by category as an annotated donut.")
                print()

                print("Transaction types: income | expense | transfer | debt_borrowed |")
                print("                   debt_repaid | investment_deposit | investment_withdraw")
                tx_type = input("Transaction type (blank = expense): ").strip() or "expense"

                top_n      = _ask_int("Top N categories to show (blank = 9): ", default=9)
                start_date = _ask_date("Start date YYYY-MM-DD (blank = start of month): ")
                end_date   = _ask_date("End date   YYYY-MM-DD (blank = today): ")

                print("\n⏳ Rendering chart…")
                charts.category_donut(
                    transaction_type=tx_type,
                    top_n=top_n,
                    start_date=start_date,
                    end_date=end_date,
                )
                print("✅ Chart closed.")

            # ================================================================
            # 3. DAILY SPENDING HEATMAP
            # ================================================================
            elif choice == 3:
                print("\n🗓  DAILY SPENDING HEATMAP — CALENDAR")
                print("-" * 60)
                print("GitHub-style calendar showing spending intensity per day.")
                print("Darker / more intense colour = higher spend.")
                print()

                start_date = _ask_date("Start date YYYY-MM-DD (blank = Jan 1 this year): ")
                end_date   = _ask_date("End date   YYYY-MM-DD (blank = today): ")

                print("\n⏳ Rendering chart…")
                charts.daily_heatmap(
                    start_date=start_date,
                    end_date=end_date,
                )
                print("✅ Chart closed.")

            # ================================================================
            # 4. NET WORTH OVER TIME
            # ================================================================
            elif choice == 4:
                print("\n💎 NET WORTH OVER TIME — LINE CHART")
                print("-" * 60)
                print("Reconstructs monthly net-worth by walking backwards from")
                print("your current balance using monthly cash-flow data.")
                print()

                year_raw = input("Year (blank = current year): ").strip()
                year     = int(year_raw) if year_raw else None

                print("\n⏳ Rendering chart…")
                charts.net_worth_over_time(year=year)
                print("✅ Chart closed.")

            # ================================================================
            # 5. SHOW ALL CHARTS
            # ================================================================
            elif choice == 5:
                print("\n🚀 SHOW ALL CHARTS")
                print("-" * 60)
                print("Opens all four charts one after another.")
                print("Close each pop-up window to advance to the next.")
                print()

                confirm = input("Proceed? (y/n): ").strip().lower()
                if confirm != "y":
                    print("⚠️  Cancelled.")
                    continue

                print("\n⏳ Chart 1 of 4 — Monthly Transaction Types…")
                charts.monthly_transactions()

                print("⏳ Chart 2 of 4 — Category Donut…")
                charts.category_donut()

                print("⏳ Chart 3 of 4 — Daily Heatmap…")
                charts.daily_heatmap()

                print("⏳ Chart 4 of 4 — Net Worth Over Time…")
                charts.net_worth_over_time()

                print("✅ All charts shown.")

            # ================================================================
            # 6. EXIT
            # ================================================================
            elif choice == 6:
                print("\n👋 Exiting charts tester.")
                break

            else:
                print("⚠️  Invalid option. Please choose 1–6.")

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
    print("✅ Charts tester finished.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("📊 FINANCE CHARTS TESTER")
    print("=" * 60)
    print("\nThis interactive tester allows you to:")
    print("  • Render individual charts on demand")
    print("  • Customise date ranges and parameters per chart")
    print("  • Test all transaction types in the donut chart")
    print("  • View all charts sequentially in one go")
    print()

    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()