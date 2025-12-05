# tests/user_model_test.py
from core.database import DatabaseConnection
from models.user_model import UserModel


def main():
    db = DatabaseConnection()
    conn = db.get_connection()
    user_model = UserModel(conn)

    while True:
        print("\n" + "=" * 60)
        print("🔐 USER MODEL TEST MENU")
        print("=" * 60)
        print("1️⃣  Register user")
        print("2️⃣  Authenticate user (login)")
        print("3️⃣  Promote user to admin")
        print("4️⃣  Demote admin to user")
        print("5️⃣  Deactivate user")
        print("6️⃣  Activate user")
        print("7️⃣  Delete user")
        print("8️⃣  List all users (admin only)")
        print("9️⃣  Change password")
        print("🔟  Change security answer")
        print("11️⃣ Logout")
        print("12️⃣ Close connection & Exit")
        print("=" * 60)

        try:
            choice = int(input("Enter choice → ").strip())
        except ValueError:
            print("❌ Invalid input. Enter a number.")
            continue

        match choice:
            case 1:
                username = input("Enter username: ")
                password = input("Enter password(visible): ")
                sec_answer = input("What is your favourite colour? \nEnter security answer(visible): ")
                role = input("Enter role (admin/user): ").strip().lower()
                res = user_model.register(username, password, sec_answer, role)
                print(res)

            case 2:
                username = input("Username: ")
                password = input("Password(visible): ")
                res = user_model.authenticate(username, password)
                print(res)

            case 3:
                username = input("Username to promote: ")
                res = user_model.promote_to_admin(username)
                print(res)

            case 4:
                username = input("Username to demote: ")
                res = user_model.demote_to_user(username)
                print(res)

            case 5:
                username = input("Username to deactivate: ")
                res = user_model.deactivate_user(username)
                print(res)

            case 6:
                username = input("Username to activate: ")
                res = user_model.activate_user(username)
                print(res)

            case 7:
                username = input("Username to delete: ")
                res = user_model.delete_user(username)
                print(res)

            case 8:
                res = user_model.list_users()
                print(res)

            case 9:
                username = input("Enter your username: ")
                secur_ans = input("Enter security answer(visible): ")
                new_pass = input("Enter new password(visible): ")
                res = user_model.change_password(username, new_pass, secur_ans)
                print(res)

            case 10:
                username = input("Enter username: ")
                new_ans = input("Enter new security answer(visible): ")
                res = user_model.change_security_answer(username, new_ans)
                print(res)

            case 11:
                res = user_model.logout()
                print(res)

            case 12:
                print("👋 Closing connection and exiting...")
                user_model.close()
                break

            case _:
                print("❌ Invalid option, please try again.")


if __name__ == "__main__":
    main()
