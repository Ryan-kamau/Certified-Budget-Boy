# tests/test_insights.py
"""
Interactive Insights Engine Tester

A menu-driven test interface for the InsightsEngine module.
Tests all insight categories through a simple CLI menu.

TODO: Update the following before running:
1. Import paths if your structure is different (line 12-18)
"""

from pprint import pprint
from datetime import datetime, date, timedelta

# ============================================================================
# TODO: UPDATE THESE IMPORTS BASED ON YOUR PROJECT STRUCTURE
# ============================================================================
from core.database import DatabaseConnection
from models.user_model import UserModel
from features.insights import (
    InsightsEngine,
    InsightCategory,
    Severity,
    DEFAULT_THRESHOLDS,
    InsightsValidationError,
)


# ============================================================================
# Helpers
# ============================================================================

def print_menu():
    """Display the main menu."""
    print("\n🧠 INSIGHTS ENGINE TEST MENU")
    print("=" * 60)
    print("ALL INSIGHTS:")
    print("  1. Get all insights          (current vs prior month)")
    print("  2. Get insights summary      (dashboard badge view)")
    print()
    print("BY CATEGORY:")
    print("  3. Spending insights         (spike, daily avg, streak)")
    print("  4. Income insights           (drop, no income)")
    print("  5. Savings insights          (rate, net worth)")
    print("  6. Category insights         (per-category spike, budget cap, shift)")
    print("  7. Transaction insights      (large transaction alerts)")
    print("  8. Debt insights             (debt growing / reducing)")
    print("  9. Payment method insights   (payment method shift)")
    print()
    print("FILTERED:")
    print(" 10. Filter by severity        (info / warning / critical)")
    print(" 11. Filter by category")
    print()
    print("CUSTOM DATE RANGE:")
    print(" 12. Run all insights with custom date ranges")
    print()
    print("THRESHOLDS:")
    print(" 13. View current thresholds")
    print()
    print("  14. Exit")
    print("=" * 60)


def _ask_date(prompt: str, required: bool = False) -> date | None:
    """Prompt for an optional date (YYYY-MM-DD)."""
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


def _print_insights(insights: list) -> None:
    """Render insights to the terminal in a readable format."""
    if not insights:
        print("\n  ✅ No insights generated for this period.")
        return

    sev_icon = {"critical": "🚨", "warning": "⚠️ ", "info": "ℹ️ "}

    print(f"\n  {'─' * 56}")
    for i, ins in enumerate(insights, 1):
        icon = sev_icon.get(ins.severity if hasattr(ins, "severity") else ins.get("severity", ""), "•")
        sev  = ins.severity if hasattr(ins, "severity") else ins.get("severity", "?")
        cat  = ins.category if hasattr(ins, "category") else ins.get("category", "?")
        titl = ins.title    if hasattr(ins, "title")    else ins.get("title", "")
        msg  = ins.message  if hasattr(ins, "message")  else ins.get("message", "")

        print(f"\n  {i}. {icon} [{sev.upper():8}] [{cat}]")
        print(f"     {titl}")
        print(f"     {msg}")
    print(f"\n  {'─' * 56}")
    print(f"  Total: {len(insights)} insight(s) generated.")


def main():
    """Main tester loop."""

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

    from models.user_model import UserModel
    um   = UserModel(conn)
    auth = um.authenticate(username, password)

    if not auth.get("success"):
        print(f"❌ {auth.get('message')}")
        return

    current_user = auth["user"]
    engine = InsightsEngine(conn, current_user)

    print(f"\n✅ Logged in as: {current_user.get('username')} (ID: {current_user.get('user_id')})")
    print(f"✅ Role: {current_user.get('role')}")
    print("✅ InsightsEngine ready.")

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
            # 1. ALL INSIGHTS
            # ================================================================
            if choice == 1:
                print("\n🧠 ALL INSIGHTS — Current vs Prior Month")
                print("-" * 60)
                insights = engine.get_all_insights()
                _print_insights(insights)

            # ================================================================
            # 2. SUMMARY
            # ================================================================
            elif choice == 2:
                print("\n📊 INSIGHTS SUMMARY")
                print("-" * 60)
                summary = engine.get_summary()
                print(f"\n  Period (current) : {summary['period']['current']}")
                print(f"  Period (prior)   : {summary['period']['prior']}")
                print(f"\n  Total insights   : {summary['total']}")
                print(f"  🚨 Critical       : {summary['critical']}")
                print(f"  ⚠️  Warning        : {summary['warning']}")
                print(f"  ℹ️  Info           : {summary['info']}")
                print("\n  By Category:")
                for cat, count in summary["by_category"].items():
                    if count > 0:
                        print(f"    {cat:<16}: {count}")
                if summary["top_insight"]:
                    print(f"\n  🔝 Top insight: {summary['top_insight']['title']}")
                    print(f"     {summary['top_insight']['message']}")

            # ================================================================
            # 3. SPENDING INSIGHTS
            # ================================================================
            elif choice == 3:
                print("\n💸 SPENDING INSIGHTS")
                print("-" * 60)
                insights = engine.get_spending_insights()
                _print_insights(insights)

            # ================================================================
            # 4. INCOME INSIGHTS
            # ================================================================
            elif choice == 4:
                print("\n💵 INCOME INSIGHTS")
                print("-" * 60)
                insights = engine.get_income_insights()
                _print_insights(insights)

            # ================================================================
            # 5. SAVINGS INSIGHTS
            # ================================================================
            elif choice == 5:
                print("\n💰 SAVINGS INSIGHTS")
                print("-" * 60)
                insights = engine.get_savings_insights()
                _print_insights(insights)

            # ================================================================
            # 6. CATEGORY INSIGHTS
            # ================================================================
            elif choice == 6:
                print("\n🗂  CATEGORY INSIGHTS")
                print("-" * 60)
                insights = engine.get_category_insights()
                _print_insights(insights)

            # ================================================================
            # 7. TRANSACTION INSIGHTS
            # ================================================================
            elif choice == 7:
                print("\n💳 TRANSACTION INSIGHTS")
                print("-" * 60)
                insights = engine.get_transaction_insights()
                _print_insights(insights)

            # ================================================================
            # 8. DEBT INSIGHTS
            # ================================================================
            elif choice == 8:
                print("\n📋 DEBT INSIGHTS")
                print("-" * 60)
                insights = engine.get_debt_insights()
                _print_insights(insights)

            # ================================================================
            # 9. PAYMENT INSIGHTS
            # ================================================================
            elif choice == 9:
                print("\n💳 PAYMENT METHOD INSIGHTS")
                print("-" * 60)
                insights = engine.get_payment_insights()
                _print_insights(insights)

            # ================================================================
            # 10. FILTER BY SEVERITY
            # ================================================================
            elif choice == 10:
                print("\n🔍 FILTER BY SEVERITY")
                print("-" * 60)
                print("  Options: info, warning, critical")
                sev = input("  Severity: ").strip().lower()
                if sev not in {"info", "warning", "critical"}:
                    print("⚠️  Invalid severity.")
                    continue
                insights = engine.get_all_insights(severity_filter=sev)
                print(f"\n  Insights with severity '{sev}':")
                _print_insights(insights)

            # ================================================================
            # 11. FILTER BY CATEGORY
            # ================================================================
            elif choice == 11:
                print("\n🔍 FILTER BY CATEGORY")
                print("-" * 60)
                cats = sorted(InsightCategory.ALL)
                print(f"  Options: {', '.join(cats)}")
                cat = input("  Category: ").strip().lower()
                try:
                    insights = engine.get_insights_by_category(cat)
                    print(f"\n  Insights for category '{cat}':")
                    _print_insights(insights)
                except InsightsValidationError as exc:
                    print(f"❌ {exc}")

            # ================================================================
            # 12. CUSTOM DATE RANGE
            # ================================================================
            elif choice == 12:
                print("\n📅 CUSTOM DATE RANGE")
                print("-" * 60)
                print("  Current period (the period to analyse):")
                cs = _ask_date("    Start (YYYY-MM-DD): ", required=True)
                ce = _ask_date("    End   (YYYY-MM-DD): ", required=True)
                print("  Prior / baseline period:")
                ps = _ask_date("    Start (YYYY-MM-DD): ", required=True)
                pe = _ask_date("    End   (YYYY-MM-DD): ", required=True)
                insights = engine.get_all_insights(
                    curr_start=cs, curr_end=ce,
                    prev_start=ps, prev_end=pe,
                )
                _print_insights(insights)

            # ================================================================
            # 13. VIEW THRESHOLDS
            # ================================================================
            elif choice == 13:
                print("\n⚙️  CURRENT THRESHOLDS")
                print("-" * 60)
                for key, val in DEFAULT_THRESHOLDS.items():
                    print(f"  {key:<45}: {val}")

            # ================================================================
            # 14. EXIT
            # ================================================================
            elif choice == 14:
                print("\n👋 Exiting insights tester.")
                break

            else:
                print("⚠️  Invalid option. Please choose 1-14.")

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
    print("✅ Insights tester finished.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🧠 INSIGHTS ENGINE TESTER")
    print("=" * 60)
    print("\nThis interactive tester allows you to:")
    print("  • Run all smart financial insight generators")
    print("  • Filter insights by severity (info/warning/critical)")
    print("  • Filter insights by category (spending/income/etc.)")
    print("  • Test with custom date ranges")
    print("  • View the full insights summary for dashboard badges")
    print()

    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")