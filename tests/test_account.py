"""
Interactive Accounts Tester

A menu-driven test interface for the AccountModel module.
Tests all account functionality through a simple CLI menu.

TODO: Update the following before running:
1. Import paths if your structure is different (line 9-11)
"""

from pprint import pprint
from datetime import datetime

# ============================================================================
# TODO: UPDATE THESE IMPORTS BASED ON YOUR PROJECT STRUCTURE
# ============================================================================
from core.database import DatabaseConnection
from models.user_model import UserModel
from models.account_model import AccountModel  # TODO: Update path if needed


def print_menu():
    """Display the main menu"""
    print("\n💰 ACCOUNTS TEST MENU")
    print("=" * 60)
    print("CRUD OPERATIONS:")
    print("  1. Create account")
    print("  2. Get account by ID")
    print("  3. List accounts")
    print("  4. Update account")
    print("  5. Soft delete account")
    print("  6. Hard delete account")
    print("  7. Restore account")
    print()
    print("AUDIT & LOGS:")
    print("  8. View audit logs (all)")
    print("  9. View audit logs (specific account)")
    print()
    print("  10. Exit")
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
    account_manager = AccountModel(conn, current_user)

    print(f"\n✅ Logged in as: {current_user.get('username')} (ID: {current_user.get('user_id')})")
    print(f"✅ Role: {current_user.get('role')}")
    print("✅ AccountModel ready.")

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
            # CRUD OPERATIONS
            # ================================================================
            
            # ----------------------------
            # 1. CREATE ACCOUNT
            # ----------------------------
            if choice == 1:
                print("\n➕ CREATE ACCOUNT")
                print("-" * 60)
                
                name = input("Account name: ").strip()
                description = input("Description (optional): ").strip() or None
                
                print("\nAvailable account types:")
                print("  - cash")
                print("  - bank")
                print("  - mobile_money")
                print("  - credit")
                print("  - savings")
                print("  - other")
                
                account_type = input("\nAccount type: ").strip().lower()
                balance = float(input("Current balance: "))
                opening_balance = float(input("Opening balance: "))
                
                is_global = input("Make global? (y/n): ").strip().lower() == 'y'
                
                data = {
                    "name": name,
                    "description": description,
                    "account_type": account_type,
                    "balance": balance,
                    "opening_balance": opening_balance,
                    "is_global": 1 if is_global else 0
                }
                
                result = account_manager.create(**data)
                
                print(f"\n✅ Account created successfully!")
                print(f"Account ID: {result['account_id']}")

            # ----------------------------
            # 2. GET ACCOUNT BY ID
            # ----------------------------
            elif choice == 2:
                print("\n🔍 GET ACCOUNT BY ID")
                print("-" * 60)
                
                account_id = int(input("Account ID: "))
                include_deleted = input("Include deleted? (y/n): ").strip().lower() == 'y'
                global_view = input("Global view? (y/n): ").strip().lower() == 'y'
                
                result = account_manager.get_account(
                    account_id,
                    include_deleted=include_deleted,
                    global_view=global_view
                )
                
                print("\n✅ Account Details:")
                print("-" * 60)
                print(f"ID: {result['account_id']}")
                print(f"Name: {result['name']}")
                print(f"Type: {result['account_type']}")
                print(f"Balance: {result['balance']}")
                print(f"Opening Balance: {result['opening_balance']}")
                print(f"Description: {result.get('description', 'N/A')}")
                print(f"Owner: {result.get('owned_by_username', 'N/A')}")
                print(f"Active: {'Yes' if result['is_active'] else 'No'}")
                print(f"Deleted: {'Yes' if result['is_deleted'] else 'No'}")
                print(f"Created: {result['created_at']}")

            # ----------------------------
            # 3. LIST ACCOUNTS
            # ----------------------------
            elif choice == 3:
                print("\n📋 LIST ACCOUNTS")
                print("-" * 60)
                
                account_type = input("Filter by type (or leave blank): ").strip() or None
                limit = input("Limit (default: all): ").strip()
                limit = int(limit) if limit else None
                offset = input("Offset (default: 0): ").strip()
                offset = int(offset) if offset else None
                
                include_deleted = input("Include deleted? (y/n): ").strip().lower() == 'y'
                global_view = input("Global view? (y/n): ").strip().lower() == 'y'
                
                result = account_manager.list_account(
                    account_type=account_type,
                    limit=limit,
                    offset=offset,
                    include_deleted=include_deleted,
                    global_view=global_view
                )
                
                print(f"\n✅ Found {result['count']} accounts")
                print("-" * 60)
                
                if result['accounts']:
                    for acc in result['accounts']:
                        status = "🔴" if acc['is_deleted'] else "🟢"
                        print(f"\n{status} ID {acc['account_id']}: {acc['name']}")
                        print(f"   Type: {acc['account_type']}")
                        print(f"   Balance: {acc['balance']}")
                        print(f"   Owner: {acc.get('owned_by_username', 'N/A')}")
                else:
                    print("  (no accounts found)")

            # ----------------------------
            # 4. UPDATE ACCOUNT
            # ----------------------------
            elif choice == 4:
                print("\n✏️  UPDATE ACCOUNT")
                print("-" * 60)
                
                account_id = int(input("Account ID: "))
                
                print("\nLeave blank to skip any field.")
                print("-" * 60)
                
                updates = {}
                
                name = input("New name: ").strip()
                if name:
                    updates["name"] = name
                
                description = input("New description: ").strip()
                if description:
                    updates["description"] = description
                
                account_type = input("New account type: ").strip()
                if account_type:
                    updates["account_type"] = account_type
                
                balance = input("New balance: ").strip()
                if balance:
                    updates["balance"] = float(balance)
                
                opening_balance = input("New opening balance: ").strip()
                if opening_balance:
                    updates["opening_balance"] = float(opening_balance)
                
                active = input("Set active? (y/n/skip): ").strip().lower()
                if active in ['y', 'n']:
                    updates["active"] = 1 if active == 'y' else 0
                
                is_global = input("Make global? (y/n/skip): ").strip().lower()
                if is_global in ['y', 'n']:
                    updates["is_global"] = 1 if is_global == 'y' else 0
                
                if not updates:
                    print("\n⚠️  No updates provided.")
                else:
                    result = account_manager.update_account(account_id, **updates)
                    print(f"\n✅ {result['message']}")
                    print("\nUpdated account:")
                    pprint(result['update'])

            # ----------------------------
            # 5. SOFT DELETE ACCOUNT
            # ----------------------------
            elif choice == 5:
                print("\n🗑️  SOFT DELETE ACCOUNT")
                print("-" * 60)
                
                account_id = int(input("Account ID: "))
                
                confirm = input(f"⚠️  Soft delete account {account_id}? (y/n): ").strip().lower()
                
                if confirm == 'y':
                    result = account_manager.delete_account(account_id, soft=True)
                    print(f"\n✅ {result['message']}")
                else:
                    print("\n❌ Cancelled.")

            # ----------------------------
            # 6. HARD DELETE ACCOUNT
            # ----------------------------
            elif choice == 6:
                print("\n🗑️  HARD DELETE ACCOUNT")
                print("-" * 60)
                print("⚠️  WARNING: This permanently deletes the account!")
                
                account_id = int(input("Account ID: "))
                
                confirm = input(f"⚠️  PERMANENTLY delete account {account_id}? Type 'DELETE' to confirm: ").strip()
                
                if confirm == 'DELETE':
                    result = account_manager.delete_account(account_id, soft=False)
                    print(f"\n✅ {result['message']}")
                else:
                    print("\n❌ Cancelled.")

            # ----------------------------
            # 7. RESTORE ACCOUNT
            # ----------------------------
            elif choice == 7:
                print("\n♻️  RESTORE ACCOUNT")
                print("-" * 60)
                
                account_id = int(input("Account ID: "))
                
                result = account_manager.restore_account(account_id)
                print(f"\n✅ {result['message']}")

            # ================================================================
            # AUDIT & LOGS
            # ================================================================
            
            # ----------------------------
            # 8. VIEW ALL AUDIT LOGS
            # ----------------------------
            elif choice == 8:
                print("\n📜 VIEW AUDIT LOGS (ALL)")
                print("-" * 60)
                
                global_view = input("Global view? (y/n): ").strip().lower() == 'y'
                
                result = account_manager.view_audit_logs(global_view=global_view)
                
                print(f"\n✅ Found {len(result)} audit log entries")
                print("-" * 60)
                
                if result:
                    for i, log in enumerate(result[:20], 1):  # Show first 20
                        print(f"\n{i}. Log ID: {log.get('log_id')}")
                        print(f"   Account ID: {log.get('account_id')}")
                        print(f"   Action: {log.get('action')}")
                        print(f"   Performed by: {log.get('performed_by')}")
                        
                        if log.get('old_balance') is not None or log.get('new_balance') is not None:
                            print(f"   Old Balance: {log.get('old_balance')}")
                            print(f"   New Balance: {log.get('new_balance')}")
                        
                        if log.get('transaction_id'):
                            print(f"   Transaction ID: {log.get('transaction_id')}")
                        
                        print(f"   Timestamp: {log.get('timestamp')}")
                        
                        if log.get('changed_fields'):
                            print(f"   Changed Fields: {log.get('changed_fields')}")
                        
                        print("   " + "-" * 50)
                    
                    if len(result) > 20:
                        print(f"\n  ... and {len(result) - 20} more entries")
                else:
                    print("  (no logs found)")

            # ----------------------------
            # 9. VIEW AUDIT LOGS FOR SPECIFIC ACCOUNT
            # ----------------------------
            elif choice == 9:
                print("\n📜 VIEW AUDIT LOGS (SPECIFIC ACCOUNT)")
                print("-" * 60)
                
                account_id = int(input("Account ID: "))
                global_view = input("Global view? (y/n): ").strip().lower() == 'y'
                
                # Get all logs first, then filter by account_id
                all_logs = account_manager.view_audit_logs(global_view=global_view)
                result = [log for log in all_logs if log.get('account_id') == account_id]
                
                print(f"\n✅ Found {len(result)} audit log entries for account {account_id}")
                print("-" * 60)
                
                if result:
                    for i, log in enumerate(result, 1):
                        print(f"\n{i}. Log ID: {log.get('log_id')}")
                        print(f"   Action: {log.get('action')}")
                        print(f"   Performed by: {log.get('performed_by')}")
                        
                        if log.get('old_balance') is not None or log.get('new_balance') is not None:
                            print(f"   Old Balance: {log.get('old_balance')}")
                            print(f"   New Balance: {log.get('new_balance')}")
                        
                        if log.get('transaction_id'):
                            print(f"   Transaction ID: {log.get('transaction_id')}")
                        
                        print(f"   Timestamp: {log.get('created_at')}")
                        
                        if log.get('changed_fields'):
                            print(f"   Changed Fields: {log.get('changed_fields')}")
                        
                        if log.get('old_values'):
                            print(f"   Old Values: {log.get('old_values')}")
                        
                        if log.get('new_values'):
                            print(f"   New Values: {log.get('new_values')}")
                        
                        print("   " + "-" * 50)
                else:
                    print("  (no logs found for this account)")

            # ----------------------------
            # EXIT
            # ----------------------------
            elif choice == 10:
                print("\n👋 Exiting accounts tester.")
                break

            else:
                print("⚠️  Invalid option. Please choose 1-10.")

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
    print("✅ Accounts tester finished.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("💰 ACCOUNT MODEL TESTER")
    print("=" * 60)
    print("\nThis interactive tester allows you to:")
    print("  • Create, read, update, delete accounts")
    print("  • List and filter accounts")
    print("  • Restore soft-deleted accounts")
    print("  • View comprehensive audit logs")
    print()
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()