"""
Interactive Dashboard Tester

A menu-driven test interface for the Dashboard module.
Tests all Rich display sections and Matplotlib chart integration.

TODO: Update the following before running:
1. Import paths if your structure is different (line 12-13)
"""

from datetime import datetime

# ============================================================================
# TODO: UPDATE THESE IMPORTS BASED ON YOUR PROJECT STRUCTURE
# ============================================================================
from core.database import DatabaseConnection
from models.user_model import UserModel
from features.dashboard import Dashboard

# ============================================================================
# Helpers
# ============================================================================

def print_menu():
    """Display the main menu"""
    print("\n💰 DASHBOARD TEST MENU")
    print("=" * 60)
    print("RICH SECTIONS:")
    print("  1. Full dashboard         (all Rich panels)")
    print("  2. Summary only           (net-worth + cash-flow)")
    print("  3. Monthly trends only    (trend table)")
    print("  4. Top categories only    (spending table)")
    print()
    print("MATPLOTLIB CHARTS  (pop-up windows):")
    print("  5. Monthly transaction types  (line graph)")
    print("  6. Spending by category       (donut chart)")
    print("  7. Daily spending heatmap     (calendar)")
    print("  8. Net worth over time        (line chart)")
    print("  9. All charts sequentially")
    print(" 10. Interactive charts menu")
    print()
    print("  11. Exit")
    print("=" * 60)


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
    dash = Dashboard(conn, current_user)

    print(f"\n✅ Logged in as: {current_user.get('username')} (ID: {current_user.get('user_id')})")
    print(f"✅ Role: {current_user.get('role')}")
    print("✅ Dashboard ready.")

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
            # RICH SECTIONS
            # ================================================================

            # ----------------------------
            # 1. FULL DASHBOARD
            # ----------------------------
            if choice == 1:
                print("\n📊 FULL DASHBOARD")
                print("-" * 60)

                top_raw     = input("Top N categories (blank = 8): ").strip()
                recent_raw  = input("Recent transactions limit (blank = 10): ").strip()
                upcoming_raw = input("Upcoming days look-ahead (blank = 7): ").strip()

                top_categories = int(top_raw)    if top_raw    else 8
                recent_limit   = int(recent_raw)  if recent_raw  else 10
                upcoming_days  = int(upcoming_raw) if upcoming_raw else 7

                print()
                dash.render(
                    top_categories=top_categories,
                    recent_limit=recent_limit,
                    upcoming_days=upcoming_days,
                )

            # ----------------------------
            # 2. SUMMARY ONLY
            # ----------------------------
            elif choice == 2:
                print("\n💎 SUMMARY — Net Worth + Cash Flow")
                print("-" * 60)
                print()
                dash.render_summary()

            # ----------------------------
            # 3. MONTHLY TRENDS ONLY
            # ----------------------------
            elif choice == 3:
                print("\n📅 MONTHLY TRENDS")
                print("-" * 60)
                print()
                dash.render_trends()

            # ----------------------------
            # 4. TOP CATEGORIES ONLY
            # ----------------------------
            elif choice == 4:
                print("\n🗂  TOP CATEGORIES — Spending Table")
                print("-" * 60)
                print()
                dash.render_categories()

            # ================================================================
            # MATPLOTLIB CHARTS
            # ================================================================

            # ----------------------------
            # 5. MONTHLY LINE GRAPH
            # ----------------------------
            elif choice == 5:
                print("\n📈 MONTHLY TRANSACTION TYPES — LINE GRAPH")
                print("-" * 60)
                print("ℹ️  Chart opens as a pop-up window.")
                print()
                dash.show_chart("monthly")
                print("✅ Chart closed.")

            # ----------------------------
            # 6. CATEGORY DONUT
            # ----------------------------
            elif choice == 6:
                print("\n🍩 SPENDING BY CATEGORY — DONUT CHART")
                print("-" * 60)
                print("ℹ️  Chart opens as a pop-up window.")
                print()
                dash.show_chart("donut")
                print("✅ Chart closed.")

            # ----------------------------
            # 7. DAILY HEATMAP
            # ----------------------------
            elif choice == 7:
                print("\n🗓  DAILY SPENDING HEATMAP")
                print("-" * 60)
                print("ℹ️  Chart opens as a pop-up window.")
                print()
                dash.show_chart("heatmap")
                print("✅ Chart closed.")

            # ----------------------------
            # 8. NET WORTH OVER TIME
            # ----------------------------
            elif choice == 8:
                print("\n💎 NET WORTH OVER TIME")
                print("-" * 60)
                print("ℹ️  Chart opens as a pop-up window.")
                print()
                dash.show_chart("networth")
                print("✅ Chart closed.")

            # ----------------------------
            # 9. ALL CHARTS
            # ----------------------------
            elif choice == 9:
                print("\n🚀 ALL CHARTS — Sequentially")
                print("-" * 60)
                print("ℹ️  Four pop-up windows. Close each to advance to the next.")
                print()
                confirm = input("Proceed? (y/n): ").strip().lower()
                if confirm != "y":
                    print("⚠️  Cancelled.")
                    continue
                dash.show_all_charts()
                print("✅ All charts shown.")

            # ----------------------------
            # 10. INTERACTIVE CHARTS MENU
            # ----------------------------
            elif choice == 10:
                print("\n📊 INTERACTIVE CHARTS MENU")
                print("-" * 60)
                print("ℹ️  Rich-powered menu — pick charts interactively.")
                print()
                dash.charts_menu()

            # ----------------------------
            # 11. EXIT
            # ----------------------------
            elif choice == 11:
                print("\n👋 Exiting dashboard tester.")
                break

            else:
                print("⚠️  Invalid option. Please choose 1–11.")

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
    print("✅ Dashboard tester finished.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("💰 DASHBOARD TESTER")
    print("=" * 60)
    print("\nThis interactive tester allows you to:")
    print("  • Render the full Rich dashboard or individual sections")
    print("  • Open any of the four Matplotlib charts")
    print("  • Use the interactive charts picker menu")
    print()

    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()