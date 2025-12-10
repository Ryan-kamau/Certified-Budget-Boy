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
    print("8. Exit")
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
            if choice == 1:
                print("\n🧾 CREATE TRANSACTION")
                title = input("Title: ").strip()
                description = input("Description (optional): ").strip() or None
                amount = float(input("Amount: "))
                tx_type = input("Type (income/expense/transfer/debts): ").strip().lower()
                payment_method = input("Payment method (cash/bank/mobile_money/credit_card/other): ").strip() or "mobile_money"
                transaction_date = input("Transaction date (YYYY-MM-DD): ").strip()
                category_id = input("Category ID (optional): ").strip()
                category_id = int(category_id) if category_id else None
                parent_id = input("Parent transaction ID (optional): ").strip()
                parent_id = int(parent_id) if parent_id else None
                global_view = input("Global view (y/n): ").lower() == "y"
 
                tx_data = {
                    "title": title,
                    "description": description,
                    "amount": amount,
                    "transaction_type": tx_type,
                    "payment_method": payment_method,
                    "category_id": category_id,
                    "parent_transaction_id": parent_id,
                    "transaction_date": date.fromisoformat(transaction_date),
                    "globaal_view": global_view,
                }

                result = manager.create_transaction(**tx_data)
                pprint(result)

            elif choice == 2:
                print("\n🔍 GET TRANSACTION")
                tid = int(input("Enter transaction ID: "))
                include_children = input("Include children? (y/n): ").lower() == "y"
                include_deleted = input("Include deleted? (y/n): ").lower() == "y"
                global_view = input("Global or own view (y/n): ").lower() == "y"
                result = manager.get_transaction(tid, include_children, include_deleted=include_deleted, global_view=global_view)
                pprint(result)

            elif choice == 3:
                print("\n✏️ UPDATE TRANSACTION")
                tid = int(input("Transaction ID: "))
                updates = {}
                print("Leave fields blank to skip.")
                title = input("New title: ").strip() or None
                category_id = input("Category ID: ") or None
                parent_id = input("Parent ID: ") or None
                amount = input("New amount: ").strip() or None
                payment = input("New payment method: ").strip() or None
                description = input("New description: ").strip() or None

                if title:
                    updates["title"] = title
                if category_id:
                    updates["category_id"] = category_id
                if parent_id:
                    updates["parent_transaction_id"] = parent_id
                if amount:
                    updates["amount"] = float(amount)
                if payment:
                    updates["payment_method"] = payment
                if description:
                    updates["description"] = description

                if not updates:
                    print("⚠️ No updates provided.")
                else:
                    result = manager.update_transaction(tid, **updates)
                    pprint(result)

            elif choice == 4:
                print("\n📜 LIST TRANSACTIONS")
                transaction_type = input("Transaction type ('Income', 'Expense', 'Transfer', 'Debt'): ").lower().strip()
                payment_method = input("Payment Method ('mobile_money', 'Cash', 'Bank', 'credit_card', 'other'): ").lower().strip()
                start_date = input("Start date (YYYY-MM-DD, blank=none): ").strip() or None
                end_date = input("End date (YYYY-MM-DD, blank=none): ").strip() or None
                category_id = input("Category ID (optional): ").strip()
                limit = input("Limit (blank=none): ").strip()
                offset = input("Offset (blank=none): ").strip()
                include_deleted = input("Include deleted? (y/n): ").lower() == "y"
                global_view = input("Global or own view (y/n): ").lower() == "y"

                start_date = date.fromisoformat(start_date) if start_date else None
                end_date = date.fromisoformat(end_date) if end_date else None
                category_id = int(category_id) if category_id else None
                limit = int(limit) if limit else None
                offset = int(offset) if offset else None

                data = manager.list_transactions(
                    transaction_type=transaction_type,
                    payment_method=payment_method,
                    start_date=start_date,
                    end_date=end_date,
                    category_id=category_id,
                    limit=limit,
                    offset=offset,
                    include_deleted=include_deleted,
                    global_view=global_view,
                )
                pprint(data)

            elif choice == 5:
                print("\n🗑️ SOFT DELETE TRANSACTION")
                tid = int(input("Enter transaction ID: "))
                recurs = input("Do you want to delete children also....'y' or 'n') ").lower().strip() == 'y'
                recurs = input("Do you want to delete children also....'y' or 'n') ").lower().strip() == 'y'
                data = manager.delete_transaction(tid, soft=True, recursive=recurs)
                pprint(data)

            elif choice == 6:
                print("\n💀 HARD DELETE TRANSACTION")
                tid = int(input("Enter transaction ID: "))
                recurs = input("Do you want to delete children also....'y' or 'n') ").lower().strip() == 'y'
                data = manager.delete_transaction(tid, soft=False, recursive=recurs)
                pprint(data)

            elif choice == 7:
                print("\n🔄 RESTORE TRANSACTION")
                tid = int(input("Enter transaction ID: "))
                recurs = input("Do you want to restore children also....'y' or 'n') ").lower().strip() == 'y'
                data = manager.restore_transaction(tid, recurs)
                pprint(data)

            elif choice == 8:
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
