# tests/test_goals.py
"""
Interactive Goals Service Tester

A menu-driven test interface for the GoalService module.
Tests all goals functionality through a simple CLI menu.

TODO: Update the following before running:
1. Import paths if your structure is different (line 9-12)
"""

from pprint import pprint
from datetime import datetime, date

# ============================================================================
# TODO: UPDATE THESE IMPORTS BASED ON YOUR PROJECT STRUCTURE
# ============================================================================
from fintrack.core.database import DatabaseConnection
from fintrack.models.user_model import UserModel
from fintrack.features.goals import (
    GoalService,
    GoalNotFoundError,
    GoalValidationError,
    GoalDatabaseError,
)


# ============================================================================
# MENU
# ============================================================================

def print_menu():
    """Display the main menu."""
    print("\n🎯 GOALS SERVICE TEST MENU")
    print("=" * 60)
    print("CRUD OPERATIONS:")
    print("  1.  Create goal")
    print("  2.  Get goal by ID  (with live progress)")
    print("  3.  Update goal")
    print("  4.  Soft delete goal")
    print("  5.  Hard delete goal")
    print("  6.  Restore goal")
    print("  7.  List goals")
    print()
    print("PROGRESS & TRACKING:")
    print("  8.  Get progress for a goal")
    print("  9.  Get ALL active goals progress")
    print("  10. Check budget cap  (by category or account)")
    print()
    print("STATUS MANAGEMENT:")
    print("  11. Auto-update all statuses")
    print("  12. Mark goal as completed")
    print("  13. Pause goal")
    print("  14. Resume goal")
    print()
    print("DASHBOARD & AUDIT:")
    print("  15. Get goals summary  (dashboard)")
    print("  16. View audit logs")
    print()
    print("  17. Exit")
    print("=" * 60)


# ============================================================================
# Small Input Helpers
# ============================================================================

def _ask_date(prompt: str, required: bool = False):
    """Prompt for an optional date (YYYY-MM-DD). Returns date or None."""
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
            print("⚠️  Invalid format — use YYYY-MM-DD.")


def _ask_int(prompt: str, required: bool = False):
    """Prompt for an optional integer. Returns int or None."""
    while True:
        raw = input(prompt).strip()
        if not raw:
            if required:
                print("⚠️  This field is required.")
                continue
            return None
        try:
            return int(raw)
        except ValueError:
            print("⚠️  Please enter a whole number.")


def _ask_float(prompt: str, required: bool = False):
    """Prompt for an optional float. Returns float or None."""
    while True:
        raw = input(prompt).strip()
        if not raw:
            if required:
                print("⚠️  This field is required.")
                continue
            return None
        try:
            return float(raw)
        except ValueError:
            print("⚠️  Please enter a valid number.")


def _ask_global_view(role: str) -> bool:
    """Ask admin users whether they want global view."""
    if role != "admin":
        return False
    raw = input("Global view? (y/n, default n): ").strip().lower()
    return raw == "y"


def _print_goal(goal: dict):
    """Pretty-print a single goal dict, highlighting progress fields."""
    print("\n" + "-" * 60)
    core_fields = [
        "goal_id", "name", "goal_type", "status",
        "target_amount", "start_date", "end_date",
        "category_id", "account_id", "description",
        "is_global", "is_deleted", "owner_username",
    ]
    progress_fields = [
        "current_amount", "remaining", "progress_pct",
        "time_elapsed_pct", "days_left", "on_track", "inferred_status",
    ]

    print("📋 GOAL DETAILS:")
    for f in core_fields:
        if f in goal:
            print(f"   {f:<22}: {goal[f]}")

    if "progress_pct" in goal:
        print("\n📊 LIVE PROGRESS:")
        for f in progress_fields:
            if f in goal:
                val = goal[f]
                if f == "on_track":
                    val = "✅ Yes" if val else "⚠️  No"
                if f == "progress_pct":
                    val = f"{val}%"
                if f == "time_elapsed_pct":
                    val = f"{val}%"
                print(f"   {f:<22}: {val}")
    print("-" * 60)


# ============================================================================
# Main
# ============================================================================

def main():
    """Main tester loop."""

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
    svc = GoalService(conn, current_user)
    role = current_user.get("role", "user")

    print(f"\n✅ Logged in as: {current_user.get('username')} (ID: {current_user.get('user_id')})")
    print(f"✅ Role: {role}")
    print("✅ GoalService ready.")

    # ----------------------------
    # Menu Loop
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
            # CRUD OPERATIONS
            # ================================================================

            # ----------------------------
            # 1. Create Goal
            # ----------------------------
            if choice == 1:
                print("\n🎯 CREATE GOAL")
                print("-" * 60)
                print("Goal types: saving | spending | budget_cap")
                print()

                name        = input("Name (required): ").strip()
                goal_type   = input("Goal type (saving/spending/budget_cap): ").strip()
                target      = _ask_float("Target amount (required): ", required=True)
                start_date  = _ask_date("Start date YYYY-MM-DD (required): ", required=True)
                end_date    = _ask_date("End date   YYYY-MM-DD (required): ", required=True)
                description = input("Description (optional, press Enter to skip): ").strip() or None

                category_id = None
                account_id  = None

                if goal_type == "saving":
                    account_id = _ask_int("Account ID (required for saving): ", required=True)
                elif goal_type in ("spending", "budget_cap"):
                    print("Link by category OR account (at least one required).")
                    category_id = _ask_int("Category ID (leave blank to skip): ")
                    if not category_id:
                        account_id = _ask_int("Account ID (leave blank to skip): ")

                status     = input("Initial status (default 'active'): ").strip() or "active"
                is_global  = input("Is global? (y/n, default n): ").strip().lower() == "y"

                data = dict(
                    name=name,
                    goal_type=goal_type,
                    target_amount=target,
                    start_date=start_date,
                    end_date=end_date,
                    description=description,
                    category_id=category_id,
                    account_id=account_id,
                    status=status,
                    is_global=1 if is_global else 0,
                )
                # Strip None values so defaults apply cleanly
                data = {k: v for k, v in data.items() if v is not None}

                result = svc.create_goal(**data)
                print(f"\n✅ Goal created! ID: {result['goal_id']}")
                _print_goal(result["goal"])

            # ----------------------------
            # 2. Get Goal by ID
            # ----------------------------
            elif choice == 2:
                print("\n🔍 GET GOAL")
                print("-" * 60)
                goal_id         = _ask_int("Goal ID: ", required=True)
                include_deleted = input("Include deleted? (y/n, default n): ").strip().lower() == "y"

                goal = svc.get_goal(goal_id, include_deleted=include_deleted)
                _print_goal(goal)

            # ----------------------------
            # 3. Update Goal
            # ----------------------------
            elif choice == 3:
                print("\n✏️  UPDATE GOAL")
                print("-" * 60)
                print("Updatable fields: name, description, target_amount,")
                print("                  start_date, end_date, category_id,")
                print("                  account_id, status, is_global")
                print()
                goal_id = _ask_int("Goal ID: ", required=True)

                updates = {}
                name = input("New name         (Enter to skip): ").strip()
                if name:
                    updates["name"] = name

                desc = input("New description  (Enter to skip): ").strip()
                if desc:
                    updates["description"] = desc

                amt = _ask_float("New target amount (Enter to skip): ")
                if amt is not None:
                    updates["target_amount"] = amt

                s = _ask_date("New start date YYYY-MM-DD (Enter to skip): ")
                if s:
                    updates["start_date"] = s

                e = _ask_date("New end date   YYYY-MM-DD (Enter to skip): ")
                if e:
                    updates["end_date"] = e

                cat = _ask_int("New category_id  (Enter to skip): ")
                if cat is not None:
                    updates["category_id"] = cat

                acc = _ask_int("New account_id   (Enter to skip): ")
                if acc is not None:
                    updates["account_id"] = acc

                status = input("New status (active/completed/failed/paused, Enter to skip): ").strip()
                if status:
                    updates["status"] = status

                if not updates:
                    print("⚠️  No changes entered.")
                else:
                    result = svc.update_goal(goal_id, **updates)
                    print(f"\n✅ {result['message']}")
                    _print_goal(result["goal"])

            # ----------------------------
            # 4. Soft Delete
            # ----------------------------
            elif choice == 4:
                print("\n🗑️  SOFT DELETE GOAL")
                print("-" * 60)
                goal_id = _ask_int("Goal ID: ", required=True)
                result  = svc.delete_goal(goal_id, soft=True)
                print(f"\n✅ {result['message']}")

            # ----------------------------
            # 5. Hard Delete
            # ----------------------------
            elif choice == 5:
                print("\n💥 HARD DELETE GOAL")
                print("-" * 60)
                goal_id = _ask_int("Goal ID: ", required=True)
                confirm = input(f"⚠️  Permanently delete goal {goal_id}? (yes to confirm): ").strip()
                if confirm.lower() == "yes":
                    result = svc.delete_goal(goal_id, soft=False)
                    print(f"\n✅ {result['message']}")
                else:
                    print("❌ Cancelled.")

            # ----------------------------
            # 6. Restore
            # ----------------------------
            elif choice == 6:
                print("\n♻️  RESTORE GOAL")
                print("-" * 60)
                goal_id = _ask_int("Goal ID: ", required=True)
                result  = svc.restore_goal(goal_id)
                print(f"\n✅ {result['message']}")

            # ----------------------------
            # 7. List Goals
            # ----------------------------
            elif choice == 7:
                print("\n📋 LIST GOALS")
                print("-" * 60)
                print("Leave any filter blank to skip it.")
                print()

                goal_type = input("Filter by type (saving/spending/budget_cap, Enter to skip): ").strip() or None
                status    = input("Filter by status (active/completed/failed/paused, Enter to skip): ").strip() or None
                cat_id    = _ask_int("Filter by category_id (Enter to skip): ")
                acc_id    = _ask_int("Filter by account_id  (Enter to skip): ")
                inc_del   = input("Include deleted? (y/n, default n): ").strip().lower() == "y"
                g_view    = _ask_global_view(role)
                w_prog    = input("Include live progress? (y/n, default y): ").strip().lower() != "n"
                limit     = _ask_int("Limit (Enter for no limit): ")
                offset    = _ask_int("Offset (Enter for 0): ")

                result = svc.list_goals(
                    goal_type=goal_type,
                    status=status,
                    category_id=cat_id,
                    account_id=acc_id,
                    include_deleted=inc_del,
                    global_view=g_view,
                    with_progress=w_prog,
                    limit=limit,
                    offset=offset,
                )

                print(f"\n✅ Found {result['count']} goal(s).")
                for g in result["goals"]:
                    _print_goal(g)

            # ================================================================
            # PROGRESS & TRACKING
            # ================================================================

            # ----------------------------
            # 8. Get Progress (single)
            # ----------------------------
            elif choice == 8:
                print("\n📊 GET GOAL PROGRESS")
                print("-" * 60)
                goal_id = _ask_int("Goal ID: ", required=True)
                goal    = svc.get_progress(goal_id)
                _print_goal(goal)

            # ----------------------------
            # 9. All Active Progress
            # ----------------------------
            elif choice == 9:
                print("\n📊 ALL ACTIVE GOALS — LIVE PROGRESS")
                print("-" * 60)
                goals = svc.get_all_progress()

                if not goals:
                    print("⚠️  No active goals found.")
                else:
                    print(f"Found {len(goals)} active goal(s) — sorted by urgency (least days left first).\n")
                    for g in goals:
                        _print_goal(g)

            # ----------------------------
            # 10. Check Budget Cap
            # ----------------------------
            elif choice == 10:
                print("\n🚦 CHECK BUDGET CAP")
                print("-" * 60)
                print("Check by category OR account (at least one required).")
                cat_id = _ask_int("Category ID (Enter to skip): ")
                acc_id = None
                if not cat_id:
                    acc_id = _ask_int("Account ID (Enter to skip): ")

                if not cat_id and not acc_id:
                    print("⚠️  Provide at least category_id or account_id.")
                else:
                    start = _ask_date("Override start date (Enter to use goal dates): ")
                    end   = _ask_date("Override end date   (Enter to use goal dates): ")

                    result = svc.check_budget_cap(
                        category_id=cat_id,
                        account_id=acc_id,
                        start_date=start,
                        end_date=end,
                    )

                    label = f"category {cat_id}" if cat_id else f"account {acc_id}"
                    overall = "🔴 EXCEEDED" if result["any_exceeded"] else "🟢 Within limits"
                    print(f"\n✅ Budget cap check for {label}: {overall}")

                    if not result["caps"]:
                        print("   No budget_cap goals found for this filter.")
                    else:
                        print(f"\n{'Goal ID':<10} {'Name':<25} {'Target':>12} {'Current':>12} {'%':>8} {'Status'}")
                        print("-" * 80)
                        for cap in result["caps"]:
                            status_icon = "🔴 OVER" if cap["exceeded"] else "🟢 OK  "
                            print(
                                f"{cap['goal_id']:<10} "
                                f"{cap['name'][:24]:<25} "
                                f"{cap['target_amount']:>12,.2f} "
                                f"{cap['current_amount']:>12,.2f} "
                                f"{cap['progress_pct']:>7.1f}% "
                                f"{status_icon}"
                            )
                            if cap["exceeded"]:
                                print(f"{'':>48} ↳ Overspend: {cap['overspend']:,.2f}")

            # ================================================================
            # STATUS MANAGEMENT
            # ================================================================

            # ----------------------------
            # 11. Auto-update statuses
            # ----------------------------
            elif choice == 11:
                print("\n🔄 AUTO-UPDATE ALL STATUSES")
                print("-" * 60)
                result = svc.auto_update_statuses()
                changed = result["total_changed"]
                if changed == 0:
                    print("✅ All goals already up-to-date. No changes needed.")
                else:
                    print(f"✅ {changed} goal(s) updated:")
                    print(f"\n{'Goal ID':<10} {'Name':<25} {'Old Status':<15} {'New Status'}")
                    print("-" * 65)
                    for u in result["updated"]:
                        print(
                            f"{u['goal_id']:<10} "
                            f"{u['name'][:24]:<25} "
                            f"{u['old_status']:<15} "
                            f"→  {u['new_status']}"
                        )

            # ----------------------------
            # 12. Mark complete
            # ----------------------------
            elif choice == 12:
                print("\n✅ MARK GOAL AS COMPLETED")
                print("-" * 60)
                goal_id = _ask_int("Goal ID: ", required=True)
                result  = svc.mark_complete(goal_id)
                print(f"\n✅ {result.get('message', 'Goal marked as completed.')}")

            # ----------------------------
            # 13. Pause
            # ----------------------------
            elif choice == 13:
                print("\n⏸️  PAUSE GOAL")
                print("-" * 60)
                goal_id = _ask_int("Goal ID: ", required=True)
                result  = svc.pause_goal(goal_id)
                print(f"\n✅ {result.get('message', 'Goal paused.')}")

            # ----------------------------
            # 14. Resume
            # ----------------------------
            elif choice == 14:
                print("\n▶️  RESUME GOAL")
                print("-" * 60)
                goal_id = _ask_int("Goal ID: ", required=True)
                result  = svc.resume_goal(goal_id)
                print(f"\n✅ {result.get('message', 'Goal resumed.')}")

            # ================================================================
            # DASHBOARD & AUDIT
            # ================================================================

            # ----------------------------
            # 15. Summary / Dashboard
            # ----------------------------
            elif choice == 15:
                print("\n📈 GOALS SUMMARY — DASHBOARD")
                print("=" * 60)
                summary = svc.get_summary()

                print(f"Generated at : {summary['generated_at']}")
                print(f"Total goals  : {summary['total_goals']}")

                print("\nBy Status:")
                for status, count in summary["by_status"].items():
                    bar = "█" * count
                    print(f"  {status:<12}: {count:>3}  {bar}")

                print("\nBy Type:")
                for gtype, count in summary["by_type"].items():
                    bar = "█" * count
                    print(f"  {gtype:<12}: {count:>3}  {bar}")

                if summary["caps_exceeded"]:
                    print(f"\n🔴 BUDGET CAPS EXCEEDED ({len(summary['caps_exceeded'])}):")
                    for cap in summary["caps_exceeded"]:
                        print(f"  Goal #{cap['goal_id']} — {cap['name']} — overspend: {cap['overspend']:,.2f}")
                else:
                    print("\n🟢 All budget caps within limits.")

                if summary["active_goals"]:
                    print(f"\n🎯 ACTIVE GOALS (sorted by urgency):")
                    print(f"  {'ID':<6} {'Name':<25} {'Type':<12} {'Progress':>10} {'Days Left':>10} {'On Track'}")
                    print("  " + "-" * 75)
                    for g in summary["active_goals"]:
                        on_track = "✅" if g["on_track"] else "⚠️ "
                        print(
                            f"  {g['goal_id']:<6} "
                            f"{g['name'][:24]:<25} "
                            f"{g['goal_type']:<12} "
                            f"{g['progress_pct']:>9.1f}% "
                            f"{g['days_left']:>10} "
                            f"  {on_track}"
                        )
                else:
                    print("\n⚠️  No active goals.")

            # ----------------------------
            # 16. Audit Logs
            # ----------------------------
            elif choice == 16:
                print("\n🔍 VIEW AUDIT LOGS")
                print("-" * 60)
                goal_id = _ask_int("Filter by Goal ID (Enter for all): ")
                g_view  = _ask_global_view(role)

                logs = svc.view_audit_logs(goal_id=goal_id, global_view=g_view)

                if not logs:
                    print("⚠️  No audit log entries found.")
                else:
                    print(f"\n✅ {len(logs)} log entry/entries found:\n")
                    for log in logs:
                        print(f"  [{log.get('timestamp')}] "
                              f"Action: {log.get('action'):<20} "
                              f"Goal ID: {log.get('target_id'):<6} "
                              f"By: {log.get('performed_by', 'N/A')}")

            # ----------------------------
            # 17. Exit
            # ----------------------------
            elif choice == 17:
                print("\n👋 Exiting goals tester.")
                break

            else:
                print("⚠️  Invalid option. Please choose 1–17.")

        except GoalNotFoundError as e:
            print(f"\n❌ Not Found: {e}")
        except GoalValidationError as e:
            print(f"\n❌ Validation Error: {e}")
        except GoalDatabaseError as e:
            print(f"\n❌ Database Error: {e}")
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user.")
            break
        except Exception as exc:
            print(f"\n❌ Unexpected Error: {exc}")
            import traceback
            traceback.print_exc()

    # ----------------------------
    # Cleanup
    # ----------------------------
    conn.close()
    print("\n🔒 Database connection closed.")
    print("✅ Goals tester finished.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🎯 GOALS SERVICE TESTER")
    print("=" * 60)
    print("\nThis interactive tester allows you to:")
    print("  • Create, read, update and delete goals")
    print("  • Track saving, spending and budget cap goals")
    print("  • View live progress computed from transactions")
    print("  • Check budget caps in real time")
    print("  • Auto-update goal statuses")
    print("  • View the full audit trail")
    print()

    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()