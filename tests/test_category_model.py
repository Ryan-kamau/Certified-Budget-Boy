from core.database import DatabaseConnection
from models.user_model import UserModel
from pprint import pprint
from models.category_model import CategoryModel
from datetime import datetime



def print_menu():
    print("\n📂 CATEGORY MANAGER TEST MENU")
    print("=" * 40)
    print("1. Add category")
    print("2. List all categories (flat)")
    print("3. List subcategories")
    print("4. Get category by ID")
    print("5. Update category")
    print("6. Move category")
    print("7. Soft delete category")
    print("8. Hard delete category")
    print("9. Restore category")
    print("10. Exit")
    print("=" * 40)


def main():
    db = DatabaseConnection()
    conn = db.get_connection()
    if not conn:
        return None

    um = UserModel(conn)
    name = input("Username: ").strip()
    password = input("Password: ").strip()
    auth_result = um.authenticate(name, password)
    if not auth_result.get("success"):
        print(auth_result.get("message", "Login failed."))
        return
    current_user = auth_result.get("user")
    manager = CategoryModel(conn, current_user)  # Example: admin user
    print("✅ Connected to database and initialized CategoryManager.")

    while True:
        print_menu()
        try:
            choice = int(input("👉 Enter your choice: "))
        except ValueError:
            print("⚠️ Invalid choice. Please enter a number.")
            continue

        try:
            if choice == 1:
                name = input("Enter category name: ").strip()
                parent = input("Parent ID (leave blank if none): ").strip()
                descrip = input("Description (leave blank if none): ").strip()
                is_global = str(input("Global view (y/n): ")).lower() == "y"
                parent_id = int(parent) if parent else None
                descrip = str(descrip) if descrip else None
                result = manager.add_category(name, parent_id, descrip)
                pprint(result)

            elif choice == 2:
                include_deleted = input("Include deleted? (y/n): ").lower() == "y"
                flat = input("Flat view? (y/n): ").lower() == "y"
                section = input("Want to view own/global/user: ").lower()
                data = manager.list_categories(flat=flat, include_deleted=include_deleted, section=section)
                pprint(data)

            elif choice == 3:
                pid = input("Parent ID (leave blank for top-level): ").strip()
                parent_id = int(pid) if pid else None
                include_deleted = input("Include deleted? (y/n): ").lower() == "y"
                section = input("Want to view own/global/user: ").lower()
                data = manager.list_subcategories(parent_id, include_deleted, section=section)
                pprint(data)

            elif choice == 4:
                cid = int(input("Enter category ID: "))
                data = manager.get_category(cid)
                pprint(data)

            elif choice == 5:
                cid = int(input("Enter category ID: "))
                new_name = input("Enter new name: ")
                description = input("Enter Description (Can leave blank): ")
                global_view = input("Global view (y/n): ").lower() == "y"
                result = manager.update_category(cid, new_name, description, global_view)
                pprint(result)

            elif choice == 6:
                cid = int(input("Enter category ID: "))
                new_parent = input("Enter new parent ID (blank for root): ").strip()
                new_parent_id = int(new_parent) if new_parent else None
                result = manager.move_category(cid, new_parent_id)
                pprint(result)

            elif choice == 7:
                cid = int(input("Enter category ID: "))
                recursive = input("Recursive delete? (y/n): ").lower() == "y"
                rows = manager.delete_category(cid, soft=True, recursive=recursive)
                print(f"🗑️ Soft deleted {rows} category(s).")

            elif choice == 8:
                cid = int(input("Enter category ID: "))
                recursive = input("Recursive delete? (y/n): ").lower() == "y"
                rows = manager.delete_category(cid, soft=False, recursive=recursive)
                print(f"💀 Hard deleted {rows} category(s).")

            elif choice == 9:
                cid = int(input("Enter category ID: "))
                recursive = input("Recursive restore? (y/n): ").lower() == "y"
                rows = manager.restore_category(cid, recursive=recursive)
                print(f"🔄 Restored {rows} category(s).")

            elif choice == 10:
                print("👋 Exiting tester. Goodbye!")
                break

            else:
                print("⚠️ Invalid option. Try again.")

        except Exception as e:
            print(f"❌ MySQL Error: {e}")
        except Exception as ex:
            print(f"⚠️ Error: {ex}")

    conn.close()
    print("🔒 Connection closed.")


if __name__ == "__main__":
    main()
