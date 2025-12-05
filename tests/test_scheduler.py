"""
Interactive Scheduler Tester

A menu-driven test interface for the Scheduler module.
Tests all scheduler functionality through a simple CLI menu.

TODO: Update the following before running:
1. Database connection details (line 20-26)
2. Import paths if your structure is different (line 9-11)
"""

from pprint import pprint
from datetime import datetime, timedelta

# ============================================================================
# TODO: UPDATE THESE IMPORTS BASED ON YOUR PROJECT STRUCTURE
# ============================================================================
from core.database import DatabaseConnection
from models.user_model import UserModel
from core.scheduler import Scheduler  # TODO: Update path if needed


def print_menu():
    """Display the main menu"""
    print("\n🗓️  SCHEDULER TEST MENU")
    print("=" * 60)
    print("EXECUTION:")
    print("  1. Run all due recurring transactions")
    print("  2. Run scheduler job (cron-style)")
    print()
    print("PREVIEW & MONITORING:")
    print("  3. Preview next run for a recurring")
    print("  4. Get scheduler status")
    print("  5. Get upcoming due (next 7 days)")
    print()
    print("CONTROL OPERATIONS:")
    print("  6. Pause recurring transaction")
    print("  7. Resume recurring transaction")
    print("  8. Skip next occurrence")
    print("  9. Set one-time amount override")
    print("  10. Deactivate recurring")
    print("  11. Activate recurring")
    print()
    print("HISTORY:")
    print("  12. View execution history (all)")
    print("  13. View history for specific recurring")
    print("  14. View history by status")
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
    scheduler = Scheduler(conn, current_user)

    print(f"\n✅ Logged in as: {current_user.get('username')} (ID: {current_user.get('user_id')})")
    print(f"✅ Role: {current_user.get('role')}")
    print("✅ Scheduler ready.")

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
            # EXECUTION
            # ================================================================
            
            # ----------------------------
            # 1. RUN ALL DUE RECURRING
            # ----------------------------
            if choice == 1:
                print("\n🚀 RUNNING ALL DUE RECURRING TRANSACTIONS")
                print("-" * 60)
                
                result = scheduler.run_all_due_recurring()
                
                print(f"\nSuccess: {result['success']}")
                print(f"Created: {result['created_count']} transactions")
                print(f"Transaction IDs: {result['transaction_ids']}")
                print(f"Message: {result['message']}")

            # ----------------------------
            # 2. RUN SCHEDULER JOB
            # ----------------------------
            elif choice == 2:
                print("\n⏰ RUNNING SCHEDULER JOB (CRON-STYLE)")
                print("-" * 60)
                
                result = scheduler.run_scheduler_job()
                
                print(f"\nJob Status: {result['job_status']}")
                print(f"Start Time: {result['start_time']}")
                print(f"End Time: {result['end_time']}")
                print(f"User ID: {result['user_id']}")
                print(f"\nExecution Result:")
                pprint(result['result'])

            # ================================================================
            # PREVIEW & MONITORING
            # ================================================================
            
            # ----------------------------
            # 3. PREVIEW NEXT RUN
            # ----------------------------
            elif choice == 3:
                print("\n🔍 PREVIEW NEXT RUN")
                print("-" * 60)
                
                rid = int(input("Recurring ID: "))
                
                result = scheduler.preview_next_run(rid)
                pprint(result)

            # ----------------------------
            # 4. GET SCHEDULER STATUS
            # ----------------------------
            elif choice == 4:
                print("\n📊 SCHEDULER STATUS")
                print("-" * 60)
                
                result = scheduler.get_scheduler_status()
                
                print(f"\nTotal Active: {result['total_active']}")
                print(f"Total Paused: {result['total_paused']}")
                print(f"Total Overdue: {result['total_overdue']}")
                print(f"Timestamp: {result['timestamp']}")
                print(f"User ID: {result['user_id']}")

            # ----------------------------
            # 5. GET UPCOMING DUE
            # ----------------------------
            elif choice == 5:
                print("\n📅 UPCOMING DUE RECURRING TRANSACTIONS")
                print("-" * 60)
                
                days = input("Days ahead (default 7): ").strip()
                days = int(days) if days else 7
                
                result = scheduler.get_upcoming_due(days_ahead=days)
                
                print(f"\n✅ Found {len(result)} upcoming recurring transactions")
                
                if result:
                    print("\nUpcoming:")
                    for r in result:
                        print(f"  • ID {r['recurring_id']}: {r['name']} - Due: {r['next_due']}")
                else:
                    print("  (none)")

            # ================================================================
            # CONTROL OPERATIONS
            # ================================================================
            
            # ----------------------------
            # 6. PAUSE RECURRING
            # ----------------------------
            elif choice == 6:
                print("\n⏸️  PAUSE RECURRING TRANSACTION")
                print("-" * 60)
                
                rid = int(input("Recurring ID: "))
                pause_days = int(input("Pause for how many days? "))
                
                pause_until = datetime.now() + timedelta(days=pause_days)
                
                result = scheduler.pause_recurring(rid, pause_until)
                print(f"\n✅ Paused until {pause_until}")
                pprint(result)

            # ----------------------------
            # 7. RESUME RECURRING
            # ----------------------------
            elif choice == 7:
                print("\n▶️  RESUME RECURRING TRANSACTION")
                print("-" * 60)
                
                rid = int(input("Recurring ID: "))
                
                result = scheduler.resume_recurring(rid)
                print("\n✅ Resumed")
                pprint(result)

            # ----------------------------
            # 8. SKIP NEXT OCCURRENCE
            # ----------------------------
            elif choice == 8:
                print("\n⏭️  SKIP NEXT OCCURRENCE")
                print("-" * 60)
                
                rid = int(input("Recurring ID: "))
                
                result = scheduler.skip_next_occurrence(rid)
                print("\n✅ Next occurrence will be skipped")
                pprint(result)

            # ----------------------------
            # 9. SET ONE-TIME OVERRIDE
            # ----------------------------
            elif choice == 9:
                print("\n💰 SET ONE-TIME AMOUNT OVERRIDE")
                print("-" * 60)
                
                rid = int(input("Recurring ID: "))
                override_amount = float(input("Override amount: "))
                
                result = scheduler.set_one_time_override(rid, override_amount)
                print(f"\n✅ Next occurrence will use amount: {override_amount}")
                pprint(result)

            # ----------------------------
            # 10. DEACTIVATE RECURRING
            # ----------------------------
            elif choice == 10:
                print("\n🔴 DEACTIVATE RECURRING TRANSACTION")
                print("-" * 60)
                
                rid = int(input("Recurring ID: "))
                
                result = scheduler.deactivate_recurring(rid)
                print("\n✅ Deactivated")
                pprint(result)

            # ----------------------------
            # 11. ACTIVATE RECURRING
            # ----------------------------
            elif choice == 11:
                print("\n🟢 ACTIVATE RECURRING TRANSACTION")
                print("-" * 60)
                
                rid = int(input("Recurring ID: "))
                
                result = scheduler.activate_recurring(rid)
                print("\n✅ Activated")
                pprint(result)

            # ================================================================
            # HISTORY
            # ================================================================
            
            # ----------------------------
            # 12. VIEW ALL HISTORY
            # ----------------------------
            elif choice == 12:
                print("\n📜 EXECUTION HISTORY (ALL)")
                print("-" * 60)
                
                limit = input("Limit (default 50): ").strip()
                limit = int(limit) if limit else 50
                
                result = scheduler.get_recurring_history(limit=limit)
                
                print(f"\n✅ Found {len(result)} history records")
                
                if result:
                    for record in result[:10]:  # Show first 10
                        print(f"\n  Run Date: {record.get('run_date')}")
                        print(f"  Recurring ID: {record.get('recurring_id')}")
                        print(f"  Amount: {record.get('amount_used')}")
                        print(f"  Status: {record.get('status')}")
                        print(f"  Message: {record.get('message')}")
                        print("  " + "-" * 50)
                    
                    if len(result) > 10:
                        print(f"\n  ... and {len(result) - 10} more records")

            # ----------------------------
            # 13. VIEW HISTORY FOR SPECIFIC RECURRING
            # ----------------------------
            elif choice == 13:
                print("\n📜 EXECUTION HISTORY (SPECIFIC RECURRING)")
                print("-" * 60)
                
                rid = int(input("Recurring ID: "))
                limit = input("Limit (default 50): ").strip()
                limit = int(limit) if limit else 50
                
                result = scheduler.get_recurring_history(
                    recurring_id=rid,
                    limit=limit
                )
                
                print(f"\n✅ Found {len(result)} history records for recurring ID {rid}")
                pprint(result)

            # ----------------------------
            # 14. VIEW HISTORY BY STATUS
            # ----------------------------
            elif choice == 14:
                print("\n📜 EXECUTION HISTORY (BY STATUS)")
                print("-" * 60)
                
                print("\nAvailable statuses:")
                print("  - generated")
                print("  - skipped")
                print("  - failed")
                
                status = input("\nStatus filter: ").strip()
                limit = input("Limit (default 50): ").strip()
                limit = int(limit) if limit else 50
                
                result = scheduler.get_recurring_history(
                    status=status,
                    limit=limit
                )
                
                print(f"\n✅ Found {len(result)} records with status '{status}'")
                
                if result:
                    for record in result[:10]:
                        print(f"\n  Run Date: {record.get('run_date')}")
                        print(f"  Recurring ID: {record.get('recurring_id')}")
                        print(f"  Amount: {record.get('amount_used')}")
                        print(f"  Status: {record.get('status')}")
                        print(f"  Message: {record.get('message')}")
                        print("  " + "-" * 50)

            # ----------------------------
            # EXIT
            # ----------------------------
            elif choice == 15:
                print("\n👋 Exiting scheduler tester.")
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
    print("✅ Scheduler tester finished.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🗓️  SCHEDULER MODULE TESTER")
    print("=" * 60)
    print("\nThis interactive tester allows you to:")
    print("  • Execute recurring transactions")
    print("  • Monitor scheduler status")
    print("  • Control recurring behavior (pause/resume/skip)")
    print("  • View execution history")
    print()
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()