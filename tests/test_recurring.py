from core.database import DatabaseConnection
from models.user_model import UserModel
from features.recurring import RecurringModel
from datetime import datetime, timedelta, date
from pprint import pprint


def print_menu():
    print("\n🔁 RECURRING TRANSACTION TEST MENU")
    print("=" * 50)
    print("1. Create recurring")
    print("2. Get recurring by ID")
    print("3. List recurring")
    print("4. Update recurring")
    print("5. Soft delete recurring")
    print("6. Hard delete recurring")
    print("7. Restore recurring")
    print("8. Run recurring now (manual trigger)")
    print("9. Preview next run date")
    print("10. View recurring logs")
    print("11. Exit")
    print("=" * 50)


def main():
    # ----------------------------
    # DB & Authentication
    # ----------------------------
    db = DatabaseConnection()
    conn = db.get_connection()

    if not conn:
        print("❌ Could not establish database connection.")
        return
    username= input("Name? ")
    password = input("Password: ")

    um = UserModel(conn)
    auth = um.authenticate(username, password)

    if not auth.get("success"):
        print(auth.get("message"))
        return

    current_user = auth["user"]
    manager = RecurringModel(conn, current_user)

    print("✅ Connected & RecurringModel ready.")

    # ----------------------------
    # Menu loop
    # ----------------------------
    while True:
        print_menu()

        try:
            choice = int(input("👉 Enter choice: "))
        except ValueError:
            print("⚠️ Invalid input.")
            continue

        try:
            # ----------------------------
            # 1. CREATE
            # ----------------------------
            if choice == 1:
                print("\n🧾 CREATE RECURRING")

                name = input("Name: ").strip()
                desc = input("Description (optional): ").strip() or None
                freq = input("Frequency (daily/weekly/monthly/yearly): ").strip().lower()
                amount = float(input("Amount: "))
                cat_id = input("Category ID: ")
                trans_type = input("Type (income/expense/transfer/debts): ").strip()
                next_due_str = input("Next Due Date (YYYY-MM-DD): ").strip()
                next_due = datetime.fromisoformat(next_due_str)
                cat_id = cat_id if isinstance(cat_id, int) else None
 
                data = {
                    "name": name,
                    "description": desc,
                    "frequency": freq,
                    "next_due": next_due,
                    "amount": amount,
                    "category_id": cat_id,
                    "transaction_type": trans_type,
                }

                result = manager.create(**data)
                pprint(result)

            # ----------------------------
            # 2. GET
            # ----------------------------
            elif choice == 2:
                rid = int(input("Recurring ID: "))
                incl = input("Include deleted? (y/n): ").lower() == "y"
                gview = input("Global view? (y/n): ").lower() == "y"

                result = manager.get_recurring(rid, include_deleted=incl, global_view=gview)
                pprint(result)

            # ----------------------------
            # 3. LIST
            # ----------------------------
            elif choice == 3:
                freq = input("Frequency filter (or blank): ").strip()
                freq = freq if freq else None

                trans_type = input("Transaction type filter (or blank): ").strip()
                trans_type = trans_type if trans_type else None

                incl = input("Include deleted? (y/n): ").lower() == "y"
                gview = input("Global view? (y/n): ").lower() == "y"

                data = manager.list(
                    frequency=freq,
                    trans_type=trans_type,
                    include_deleted=incl,
                    global_view=gview,
                )
                pprint(data)

            # ----------------------------
            # 4. UPDATE
            # ----------------------------
            elif choice == 4:
                rid = int(input("Recurring ID: "))
                updates = {}

                print("Leave blank to skip editing any field.")

                # BASIC TEXT FIELDS
                name = input("New name: ").strip() or None
                description = input("New description: ").strip() or None

                # FREQUENCY + INTERVAL
                frequency = input("New frequency (daily/weekly/monthly/yearly): ").strip() or None
                interval_value = input("New interval value (number): ").strip() or None

                # AMOUNT FIELDS
                amount = input("New base amount: ").strip() or None
                override_amount = input("Override amount (leave blank to remove): ").strip() or None


                # TYPE + PAYMENT
                transaction_type = input("New type (income/expense/debt/transfer/other): ").strip() or None
                payment_method = input("New payment method (cash/bank/mobile_money/credit_card/other): ").strip() or None

                # DATE FIELDS
                next_due = input("New next_due (YYYY-MM-DD): ").strip() or None
                pause_until = input("Pause until (YYYY-MM-DD): ").strip() or None

                # BOOLS
                skip_next = input("Skip next run? (Y/N): ").strip().lower() == "y"
                is_global = input("Make global? (Y/N): ").strip().lower() == "y"
                is_active = input("Activate? (Y/N): ").strip().lower() == "y"

                # OPTIONAL MISC
                max_missed_runs = input("Max missed runs: ").strip() or None
                notes = input("Notes: ").strip() or None

                # BUILD UPDATE DICT
                updates = {}

                if name: updates["name"] = name
                if description: updates["description"] = description
                if frequency: updates["frequency"] = frequency
                if interval_value: updates["interval_value"] = int(interval_value)
                if amount: updates["amount"] = float(amount)

                # override_amount can be None explicitly
                if override_amount == "":
                    updates["override_amount"] = None
                elif override_amount:
                    updates["override_amount"] = float(override_amount)


                if transaction_type:
                    updates["transaction_type"] = transaction_type

                if payment_method:
                    updates["payment_method"] = payment_method

                if next_due:
                    updates["next_due"] = datetime.fromisoformat(next_due)

                if pause_until:
                    updates["pause_until"] = datetime.fromisoformat(pause_until)

                if max_missed_runs:
                    updates["max_missed_runs"] = int(max_missed_runs)

                if notes:
                    updates["notes"] = notes

                # boolean flags
                updates["skip_next"] = skip_next
                updates["is_global"] = is_global
                updates["is_active"] = is_active


                result = manager.update(rid, **updates)
                pprint(result)

            # ----------------------------
            # 5. SOFT DELETE
            # ----------------------------
            elif choice == 5:
                rid = int(input("Recurring ID: "))
                result = manager.delete_recurring(rid, soft=True)
                pprint(result)

            # ----------------------------
            # 6. HARD DELETE
            # ----------------------------
            elif choice == 6:
                rid = int(input("Recurring ID: "))
                result = manager.delete_recurring(rid, soft=False)
                pprint(result)

            # ----------------------------
            # 7. RESTORE
            # ----------------------------
            elif choice == 7:
                rid = int(input("Recurring ID: "))
                result = manager.restore(rid)
                pprint(result)

            # ----------------------------
            # 8. RUN NOW
            # ----------------------------
            elif choice == 8:
                data = manager.run_due()  # You have run logic in recurring.py
                pprint(data)

            # ----------------------------
            # 9. PREVIEW NEXT RUN
            # ----------------------------
            elif choice == 9:
                rid = input("Recurring ID: ")
                rid = int(rid) if rid else None      
                data = manager.preview_next_run(rid)
                pprint(data)

            # ----------------------------
            # 10. VIEW LOGS
            # ----------------------------
            elif choice == 10:
                rid = input("Recurring ID (leave blank for all): ").strip()
                status = input("Status filter (generated/skipped/failed or blank): ").strip()
                limit = input("Limit: ").strip()

                data = manager.get_history(
                    recurring_id=int(rid) if rid else None,
                    status=status if status else None,
                    limit=int(limit) if limit else None,
                )

                pprint(data)


            # ----------------------------
            # EXIT
            # ----------------------------
            elif choice == 11:
                print("👋 Exiting tester.")
                break

            else:
                print("⚠️ Invalid option.")

        except Exception as exc:
            print(f"❌ Error: {exc}")

    conn.close()
    print("🔒 Connection closed.")

if __name__ == "__main__":
    main()