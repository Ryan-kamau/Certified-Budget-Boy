from core.database import DatabaseConnection
from models.user_model import UserModel
from models.transactions_model import TransactionModel
from datetime import date
from pprint import pprint


def print_menu():
    print("\n💰 TRANSACTION MANAGER TEST MENU")
    print("=" * 50)
    print("1. Create transaction")
    print("2. Get transaction by ID")
    print("3. Update transaction")
    print("4. List transactions")
    print("5. Soft delete transaction")
    print("6. Hard delete transaction")
    print("7. Restore transaction")
    print("8. View audit logs for transaction")
    print("9. Exit")
    print("=" * 50)


def main():
    # ---------------------------
    # Database & Authentication
    # ---------------------------
    db = DatabaseConnection()
    conn = db.get_connection()
    if not conn:
        print("❌ Could not establish DB connection.")
        return None

    um = UserModel(conn)
    auth_result = um.authenticate("Dexter", "Butcher")
    if not auth_result.get("success"):
        print(auth_result.get("message", "Login failed."))
        return

    current_user = auth_result.get("user")
    manager = TransactionModel(conn, current_user)
    print("✅ Connected to database and initialized TransactionModel.")

    # ---------------------------
    # Menu Loop
    # ---------------------------
    while True:
        print_menu()
        try:
            choice = int(input("👉 Enter your choice: "))
        except ValueError:
            print("⚠️ Invalid choice. Please enter a number.")
            continue

        try:
            # ---------------------------------------------------
            # 1. CREATE TRANSACTION
            # ---------------------------------------------------
            if choice == 1:
                print("\n🧾 CREATE TRANSACTION")

                title = input("Title: ").strip()
                description = input("Description (optional): ").strip() or None
                amount = float(input("Amount: ").strip())
                tx_type = input("Type (income/expense/transfer/debts): ").strip().lower()
                payment_method = input(
                    "Payment method (cash/bank/mobile_money/credit_card/other): "
                ).strip() or "mobile_money"
                transaction_date = input("Transaction date (YYYY-MM-DD): ").strip()

                # ---- Category + Parent ----
                category_id = input("Category ID (optional): ").strip()
                category_id = int(category_id) if category_id else None

                parent_id = input("Parent transaction ID (optional): ").strip()
                parent_id = int(parent_id) if parent_id else None

                # ---- NEW REQUIRED INPUTS ----
                account_id = None
                source_account_id = None
                destination_account_id = None

                if tx_type in ["income", "expense"]:
                    account_id = int(input("Account ID (required): ").strip())

                elif tx_type == "transfer":
                    source_account_id = int(input("Source account ID: ").strip())
                    destination_account_id = int(input("Destination account ID: ").strip())

                allow_overdraft = input("Allow overdraft? (y/n): ").strip().lower() == "y"
                is_global = input("Set as global? (y/n): ").strip().lower() == "y"

                tx_data = {
                    "title": title,
                    "description": description,
                    "amount": amount,
                    "transaction_type": tx_type,
                    "payment_method": payment_method,
                    "category_id": category_id,
                    "parent_transaction_id": parent_id,
                    "transaction_date": date.fromisoformat(transaction_date),
                    "is_global": int(is_global),
                    "account_id": account_id,
                    "source_account_id": source_account_id,
                    "destination_account_id": destination_account_id,
                    "allow_overdraft": allow_overdraft,
                }

                result = manager.create_transaction(**tx_data)
                pprint(result)

            # ---------------------------------------------------
            # 2. GET TRANSACTION
            # ---------------------------------------------------
            elif choice == 2:
                print("\n🔍 GET TRANSACTION")

                tid = int(input("Enter transaction ID: ").strip())
                include_children = input("Include children? (y/n): ").strip().lower() == "y"
                include_deleted = input("Include deleted? (y/n): ").strip().lower() == "y"
                global_view = input("Global view? (y/n): ").strip().lower() == "y"

                result = manager.get_transaction(
                    tid,
                    include_children=include_children,
                    include_deleted=include_deleted,
                    global_view=global_view,
                )
                pprint(result)

            # ---------------------------------------------------
            # 3. UPDATE TRANSACTION
            # ---------------------------------------------------
            elif choice == 3:
                print("\n✏️ UPDATE TRANSACTION")
                tid = int(input("Transaction ID: ").strip())

                updates = {}
                print("Leave fields blank to skip.")

                title = input("New title: ").strip()
                category_id = input("Category ID: ").strip()
                parent_id = input("Parent ID: ").strip()
                amount = input("New amount: ").strip()
                payment = input("New payment method: ").strip()
                description = input("New description: ").strip()

                # ---- NEW ACCOUNT FIELDS ----
                account_id = input("New account_id: ").strip()
                source_account_id = input("New source_account_id: ").strip()
                destination_account_id = input("New destination_account_id: ").strip()
                allow_overdraft = input("Allow overdraft? (y/n): ").strip().lower()

                if title:
                    updates["title"] = title
                if category_id:
                    updates["category_id"] = int(category_id)
                if parent_id:
                    updates["parent_transaction_id"] = int(parent_id)
                if amount:
                    updates["amount"] = float(amount)
                if payment:
                    updates["payment_method"] = payment
                if description:
                    updates["description"] = description
                if account_id:
                    updates["account_id"] = int(account_id)
                if source_account_id:
                    updates["source_account_id"] = int(source_account_id)
                if destination_account_id:
                    updates["destination_account_id"] = int(destination_account_id)
                if allow_overdraft in ["y", "n"]:
                    updates["allow_overdraft"] = allow_overdraft == "y"

                if not updates:
                    print("⚠️ No updates provided.")
                else:
                    result = manager.update_transaction(tid, **updates)
                    pprint(result)

            # ---------------------------------------------------
            # 4. LIST TRANSACTIONS
            # ---------------------------------------------------
            elif choice == 4:
                print("\n📜 LIST TRANSACTIONS")

                transaction_type = input(
                    "Transaction type (income/expense/transfer/debts, blank=none): "
                ).strip().lower() or None

                payment_method = input(
                    "Payment method (mobile_money/cash/bank/credit_card/other, blank=none): "
                ).strip().lower() or None

                start_date = input("Start date (YYYY-MM-DD, blank=none): ").strip()
                end_date = input("End date (YYYY-MM-DD, blank=none): ").strip()

                category_id = input("Category ID (optional): ").strip()
                account_id = input("Account ID filter (optional): ").strip()
                limit = input("Limit (blank=none): ").strip()
                offset = input("Offset (blank=none): ").strip()
                include_deleted = input("Include deleted? (y/n): ").strip().lower() == "y"
                global_view = input("Global view? (y/n): ").strip().lower() == "y"

                start_date = date.fromisoformat(start_date) if start_date else None
                end_date = date.fromisoformat(end_date) if end_date else None
                category_id = int(category_id) if category_id else None
                account_id = int(account_id) if account_id else None
                limit = int(limit) if limit else None
                offset = int(offset) if offset else None

                data = manager.list_transactions(
                    transaction_type=transaction_type,
                    payment_method=payment_method,
                    start_date=start_date,
                    end_date=end_date,
                    category_id=category_id,
                    account_id=account_id,
                    limit=limit,
                    offset=offset,
                    include_deleted=include_deleted,
                    global_view=global_view,
                )
                pprint(data)

            # ---------------------------------------------------
            # 5. SOFT DELETE
            # ---------------------------------------------------
            elif choice == 5:
                print("\n🗑️ SOFT DELETE TRANSACTION")

                tid = int(input("Enter transaction ID: ").strip())
                recurs = input("Delete children also? (y/n): ").strip().lower() == "y"

                data = manager.delete_transaction(tid, soft=True, recursive=recurs)
                pprint(data)

            # ---------------------------------------------------
            # 6. HARD DELETE
            # ---------------------------------------------------
            elif choice == 6:
                print("\n💀 HARD DELETE TRANSACTION")

                tid = int(input("Enter transaction ID: ").strip())
                recurs = input("Delete children also? (y/n): ").strip().lower() == "y"

                data = manager.delete_transaction(tid, soft=False, recursive=recurs)
                pprint(data)

            # ---------------------------------------------------
            # 7. RESTORE TRANSACTION
            # ---------------------------------------------------
            elif choice == 7:
                print("\n🔄 RESTORE TRANSACTION")

                tid = int(input("Enter transaction ID: ").strip())
                recurs = input("Restore children also? (y/n): ").strip().lower() == "y"

                data = manager.restore_transaction(tid, recurs)
                pprint(data)

            # ---------------------------------------------------
            # 9. VIEW AUDIT LOGS
            # ---------------------------------------------------
            elif choice == 8:
                print("\n📒 VIEW AUDIT LOGS")

                tid = input("Enter transaction ID to view logs: ").strip()

                tid = int(tid) if tid else None
                try:
                    logs = manager.view_audit_logs(
                        target_id=tid
                    )
                    pprint(logs)
                except Exception as e:
                    print(f"❌ Error fetching audit logs: {e}")


            elif choice == 9:
                print("👋 Exiting tester. Goodbye!")
                break

            else:
                print("⚠️ Invalid option. Try again.")

        except Exception as e:
            print(f"❌ Error: {e}")

    conn.close()
    print("🔒 Connection closed.")


if __name__ == "__main__":
    main()
