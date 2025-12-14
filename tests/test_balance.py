"""
Interactive Balance Service Tester

A menu-driven test interface for the BalanceService module.
Tests all balance functionality through a simple CLI menu.

TODO: Update the following before running:
1. Import paths if your structure is different (line 9-12)
"""

from pprint import pprint
from datetime import datetime, date

# ============================================================================
# TODO: UPDATE THESE IMPORTS BASED ON YOUR PROJECT STRUCTURE
# ============================================================================
from core.database import DatabaseConnection
from models.user_model import UserModel
from features.balance import BalanceService  # TODO: Update path if needed


def print_menu():
    """Display the main menu"""
    print("\n⚖️  BALANCE SERVICE TEST MENU")
    print("=" * 60)
    print("BALANCE QUERIES:")
    print("  1. Get account balance")
    print("  2. Get all account balances")
    print("  3. Get net worth summary")
    print()
    print("TRANSACTION OPERATIONS:")
    print("  4. Apply income (increase balance)")
    print("  5. Apply expense (decrease balance)")
    print("  6. Apply transfer (between accounts)")
    print("  7. Reverse transaction")
    print()
    print("BALANCE REBUILDING:")
    print("  8. Rebuild single account balance")
    print("  9. Rebuild all account balances")
    print()
    print("HEALTH & MONITORING:")
    print("  10. Run balance health check")
    print()
    print("  11. Exit")
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
    balance_service = BalanceService(conn, current_user)

    print(f"\n✅ Logged in as: {current_user.get('username')} (ID: {current_user.get('user_id')})")
    print(f"✅ Role: {current_user.get('role')}")
    print("✅ BalanceService ready.")

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
            # BALANCE QUERIES
            # ================================================================
            
            # ----------------------------
            # 1. GET ACCOUNT BALANCE
            # ----------------------------
            if choice == 1:
                print("\n💰 GET ACCOUNT BALANCE")
                print("-" * 60)
                
                account_id = int(input("Account ID: "))
                
                result = balance_service.get_account_balance(account_id)
                
                print("\n✅ Account Balance Details:")
                print("-" * 60)
                print(f"Account ID: {result['account_id']}")
                print(f"Account Name: {result['account_name']}")
                print(f"Account Type: {result['account_type']}")
                print(f"Current Balance: {result['current_balance']:.2f}")
                print(f"Opening Balance: {result['opening_balance']:.2f}")
                print(f"Active: {'Yes' if result['is_active'] else 'No'}")
                print(f"Owner: {result['owner']}")

            # ----------------------------
            # 2. GET ALL BALANCES
            # ----------------------------
            elif choice == 2:
                print("\n💰 GET ALL ACCOUNT BALANCES")
                print("-" * 60)
                
                include_deleted = input("Include deleted accounts? (y/n): ").strip().lower() == 'y'
                
                result = balance_service.get_all_balances(include_deleted=include_deleted)
                
                print(f"\n✅ Found {len(result)} accounts")
                print("-" * 60)
                
                if result:
                    total_balance = sum(b['current_balance'] for b in result if b['is_active'])
                    
                    for balance in result:
                        status = "🟢" if balance['is_active'] else "🔴"
                        deleted = " (DELETED)" if balance['is_deleted'] else ""
                        
                        print(f"\n{status} {balance['account_name']}{deleted}")
                        print(f"   ID: {balance['account_id']}")
                        print(f"   Type: {balance['account_type']}")
                        print(f"   Current: {balance['current_balance']:.2f}")
                        print(f"   Opening: {balance['opening_balance']:.2f}")
                    
                    print("\n" + "=" * 60)
                    print(f"💵 TOTAL (Active only): {total_balance:.2f}")
                else:
                    print("  (no accounts found)")

            # ----------------------------
            # 3. GET NET WORTH
            # ----------------------------
            elif choice == 3:
                print("\n💎 NET WORTH SUMMARY")
                print("-" * 60)
                
                result = balance_service.get_net_worth()
                
                print(f"\n✅ Net Worth Report")
                print("-" * 60)
                print(f"User ID: {result['user_id']}")
                print(f"Total Net Worth: {result['total_net_worth']:.2f}")
                print(f"Active Accounts: {result['active_accounts']}")
                print(f"Timestamp: {result['timestamp']}")
                
                print("\n📊 Breakdown by Account Type:")
                print("-" * 60)
                for acc_type, amount in result['breakdown_by_type'].items():
                    print(f"  {acc_type.capitalize()}: {amount:.2f}")

            # ================================================================
            # TRANSACTION OPERATIONS
            # ================================================================
            
            # ----------------------------
            # 4. APPLY INCOME
            # ----------------------------
            elif choice == 4:
                print("\n💵 APPLY INCOME (Increase Balance)")
                print("-" * 60)
                
                account_id = int(input("Account ID: "))
                amount = float(input("Income amount: "))
                transaction_id = int(input("Transaction ID (for logging): "))
                
                result = balance_service.apply_transaction_change(
                    transaction_id=transaction_id,
                    transaction_type="income",
                    amount=amount,
                    account_id=account_id
                )
                
                print("\n✅ Income Applied Successfully!")
                print("-" * 60)
                print(f"Account ID: {result['account_id']}")
                print(f"Old Balance: {result['old_balance']:.2f}")
                print(f"New Balance: {result['new_balance']:.2f}")
                print(f"Change: +{result['change']:.2f}")
                print(f"Transaction ID: {result['changed_by_transaction']}")

            # ----------------------------
            # 5. APPLY EXPENSE
            # ----------------------------
            elif choice == 5:
                print("\n💳 APPLY EXPENSE (Decrease Balance)")
                print("-" * 60)
                
                account_id = int(input("Account ID: "))
                amount = float(input("Expense amount: "))
                transaction_id = int(input("Transaction ID (for logging): "))
                
                allow_overdraft = input("Allow overdraft? (y/n): ").strip().lower() == 'y'
                
                try:
                    result = balance_service.apply_transaction_change(
                        transaction_id=transaction_id,
                        transaction_type="expense",
                        amount=amount,
                        account_id=account_id,
                        allow_overdraft=allow_overdraft
                    )
                    
                    print("\n✅ Expense Applied Successfully!")
                    print("-" * 60)
                    print(f"Account ID: {result['account_id']}")
                    print(f"Old Balance: {result['old_balance']:.2f}")
                    print(f"New Balance: {result['new_balance']:.2f}")
                    print(f"Change: {result['change']:.2f}")
                    print(f"Transaction ID: {result['changed_by_transaction']}")
                    
                except Exception as e:
                    print(f"\n❌ Error: {e}")

            # ----------------------------
            # 6. APPLY TRANSFER
            # ----------------------------
            elif choice == 6:
                print("\n🔄 APPLY TRANSFER (Between Accounts)")
                print("-" * 60)
                
                source_id = int(input("Source Account ID: "))
                dest_id = int(input("Destination Account ID: "))
                amount = float(input("Transfer amount: "))
                transaction_id = int(input("Transaction ID (for logging): "))
                
                allow_overdraft = input("Allow overdraft? (y/n): ").strip().lower() == 'y'
                
                try:
                    result = balance_service.apply_transaction_change(
                        transaction_id=transaction_id,
                        transaction_type="transfer",
                        amount=amount,
                        source_account_id=source_id,
                        destination_account_id=dest_id,
                        allow_overdraft=allow_overdraft
                    )
                    
                    print("\n✅ Transfer Applied Successfully!")
                    print("-" * 60)
                    
                    print("\n📤 Source Account:")
                    print(f"   Account ID: {result['source']['account_id']}")
                    print(f"   Old Balance: {result['source']['old_balance']:.2f}")
                    print(f"   New Balance: {result['source']['new_balance']:.2f}")
                    print(f"   Change: {result['source']['change']:.2f}")
                    
                    print("\n📥 Destination Account:")
                    print(f"   Account ID: {result['destination']['account_id']}")
                    print(f"   Old Balance: {result['destination']['old_balance']:.2f}")
                    print(f"   New Balance: {result['destination']['new_balance']:.2f}")
                    print(f"   Change: +{result['destination']['change']:.2f}")
                    
                except Exception as e:
                    print(f"\n❌ Error: {e}")

            # ----------------------------
            # 7. REVERSE TRANSACTION
            # ----------------------------
            elif choice == 7:
                print("\n↩️  REVERSE TRANSACTION")
                print("-" * 60)
                print("This reverses the balance effects of a transaction.")
                print()
                
                transaction_id = int(input("Transaction ID to reverse: "))
                
                print("\nOriginal Transaction Details:")
                trans_type = input("Transaction Type (income/expense/transfer): ").strip().lower()
                amount = float(input("Amount: "))
                
                transaction_data = {
                    "transaction_type": trans_type,
                    "amount": amount
                }
                
                if trans_type in ["income", "expense"]:
                    account_id = int(input("Account ID: "))
                    transaction_data["account_id"] = account_id
                
                elif trans_type == "transfer":
                    source_id = int(input("Source Account ID: "))
                    dest_id = int(input("Destination Account ID: "))
                    transaction_data["source_account_id"] = source_id
                    transaction_data["destination_account_id"] = dest_id
                
                try:
                    result = balance_service.reverse_transaction_change(
                        transaction_id=transaction_id,
                        transaction_data=transaction_data
                    )
                    
                    print("\n✅ Transaction Reversed Successfully!")
                    print("-" * 60)
                    pprint(result)
                    
                except Exception as e:
                    print(f"\n❌ Error: {e}")

            # ================================================================
            # BALANCE REBUILDING
            # ================================================================
            
            # ----------------------------
            # 8. REBUILD SINGLE ACCOUNT
            # ----------------------------
            elif choice == 8:
                print("\n🔧 REBUILD ACCOUNT BALANCE")
                print("-" * 60)
                print("This recalculates balance from all transactions.")
                print("⚠️  Use this if balance seems incorrect.")
                print()
                
                account_id = int(input("Account ID: "))
                
                confirm = input(f"⚠️  Rebuild balance for account {account_id}? (y/n): ").strip().lower()
                
                if confirm == 'y':
                    result = balance_service.rebuild_account_balance(account_id)
                    
                    print("\n✅ Balance Rebuilt Successfully!")
                    print("-" * 60)
                    print(f"Account ID: {result['account_id']}")
                    print(f"Old Balance: {result['old_balance']:.2f}")
                    print(f"New Balance: {result['new_balance']:.2f}")
                    print(f"Difference: {result['difference']:.2f}")
                    print(f"Transactions Processed: {result['transactions_processed']}")
                    
                    if abs(result['difference']) > 0.01:
                        print("\n⚠️  WARNING: Balance was corrected!")
                        print(f"   Adjustment: {result['difference']:.2f}")
                else:
                    print("\n❌ Cancelled.")

            # ----------------------------
            # 9. REBUILD ALL BALANCES
            # ----------------------------
            elif choice == 9:
                print("\n🔧 REBUILD ALL ACCOUNT BALANCES")
                print("-" * 60)
                print("This recalculates balances for ALL your accounts.")
                print("⚠️  This may take a while if you have many transactions.")
                print()
                
                confirm = input("⚠️  Rebuild ALL account balances? Type 'REBUILD' to confirm: ").strip()
                
                if confirm == 'REBUILD':
                    print("\n⏳ Rebuilding balances...")
                    result = balance_service.rebuild_all_balances()
                    
                    print("\n✅ All Balances Rebuilt!")
                    print("-" * 60)
                    print(f"User ID: {result['user_id']}")
                    print(f"Accounts Rebuilt: {result['accounts_rebuilt']}")
                    print(f"Timestamp: {result['timestamp']}")
                    
                    print("\n📊 Results:")
                    for r in result['results']:
                        if 'error' in r:
                            print(f"\n❌ Account {r['account_id']}: ERROR - {r['error']}")
                        else:
                            status = "✅" if abs(r['difference']) < 0.01 else "⚠️"
                            print(f"\n{status} Account {r['account_id']}")
                            print(f"   Old: {r['old_balance']:.2f} → New: {r['new_balance']:.2f}")
                            print(f"   Difference: {r['difference']:.2f}")
                            print(f"   Transactions: {r['transactions_processed']}")
                else:
                    print("\n❌ Cancelled.")

            # ================================================================
            # HEALTH & MONITORING
            # ================================================================
            
            # ----------------------------
            # 10. HEALTH CHECK
            # ----------------------------
            elif choice == 10:
                print("\n🏥 BALANCE HEALTH CHECK")
                print("-" * 60)
                
                result = balance_service.run_balance_health_check()
                
                print(f"\n✅ Health Check Complete")
                print("-" * 60)
                print(f"User ID: {result['user_id']}")
                print(f"Timestamp: {result['timestamp']}")
                print(f"Total Issues Found: {result['total_issues']}")
                
                if result['total_issues'] > 0:
                    print("\n⚠️  ISSUES DETECTED:")
                    print("=" * 60)
                    
                    for check in result['checks']:
                        print(f"\n🔴 Account: {check['account_name']} (ID: {check['account_id']})")
                        for issue in check['issues']:
                            print(f"   • {issue}")
                else:
                    print("\n✅ All accounts healthy! No issues detected.")

            # ----------------------------
            # EXIT
            # ----------------------------
            elif choice == 11:
                print("\n👋 Exiting balance service tester.")
                break

            else:
                print("⚠️  Invalid option. Please choose 1-11.")

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
    print("✅ Balance service tester finished.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("⚖️  BALANCE SERVICE TESTER")
    print("=" * 60)
    print("\nThis interactive tester allows you to:")
    print("  • Query account balances and net worth")
    print("  • Apply income, expense, and transfer operations")
    print("  • Reverse transactions")
    print("  • Rebuild balances from scratch")
    print("  • Run health checks on your accounts")
    print()
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()