#User_model
from typing import Optional, Dict, List, Any
from core.database import DatabaseConnection
from mysql.connector import Error
import bcrypt


class UserModel:
    """
    Handles user registration, authentication, and role checks.
    Stores passwords using bcrypt.
    """
    
    def __init__(self, conn: Optional[Any] = None) -> None:
        """
        Initialize the UserModel.
        
        Args:
            conn (Optional[Any]): Optional existing database connection.
                                 If not provided, a new one will be created.
        """
        db = DatabaseConnection()
        self.conn = conn or db.get_connection()
        self.current_user: Optional[Dict[str, Any]]

    #INTERNAL helpers
    def _get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self.conn.cursor(dictionary=True) as cur:       
            cur.execute(
                "SELECT user_id, username, password_hash, role, is_active, security_answer_hash "
                "FROM users WHERE username = %s",
                (username,),
                )
            return cur.fetchone()
    

    def _hash(self, value: str) -> str:
        """Hash a password or security answer using bcrypt."""
        return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    
    def _check_password(self, plain: str, hashed: str) -> bool:
        """Verify a bcrypt hashed password."""
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    
    def _require_admin(self):
        """Raise if current user is not admin."""
        if not self.current_user or self.current_user.get("role") != "admin":
            raise PermissionError("Only admins can perform this action.")
        
    def _require_login(self):
        """Ensure a user is logged in."""
        if not self.current_user:
            raise PermissionError("You must be logged in to perform this action.")

         
    # ==========================================================
    # REGISTRATION & AUTHENTICATION
    # ==========================================================

    def register(
            self,
            username: str,
            password: str,
            security_answer: str,
            role: str
    )   -> Dict[str,Any]:
        """
        Register a new user. The first user automatically becomes admin.
        Only admins can create other admins after that.
        """
        cur = None
        try:
            if not isinstance(username, str) or not password:
                raise ValueError("Username and password are required.")
            if not isinstance(password, str):
                password = str(password)
            if len(password) < 6:
                raise ValueError("Password must be at least 6 characters long.")

            with self.conn.cursor(buffered=True) as cur:
                cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
                if cur.fetchone():
                    raise ValueError("Username already exists.")
                
                #assign first admin
                if role not in ["admin", "user"]:
                    raise ValueError("YOU CAN ONLY REGISTER ROLES AS admin OR user")
                
                cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' FOR UPDATE")
                (admin_count,) = cur.fetchone()
                first_user = admin_count == 0

                if role == 'admin' and not first_user:
                    self._require_admin()

                password_hash = self._hash(password)
                sec_hash = self._hash(security_answer)
                assigned_role = "admin" if first_user else role

                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, security_answer_hash, role)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (username, password_hash, sec_hash, role),
                )
                self.conn.commit()
                uid = cur.lastrowid

                user = self._get_user_by_username(username)
                self.current_user =  {
                    "user_id" : user.get('user_id'),
                    "username" : user.get('username'),
                    "role" : user.get('role')
                }
                
                return {
                    "success": True,
                    "message": f"User '{username}' registered successfully as {assigned_role}.",
                    "user_id": uid
                }
            
        except (ValueError, PermissionError) as e:
            return {"success": False, "message": f"Error : {str(e)}", "user_id": None}

        except Exception as e:
            self.conn.rollback()
            return {"success": False, "message": f"Database error: {e}", "user_id": None}


    #Authenticate user
    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user and set as current_user."""
        try:
            user = self._get_user_by_username(username)
            
            if not user:
                return {"success": False, "message": "User not found."}
            if not user.get("is_active"):
                return {"success": False, "message": "Account is deactivated."}
            if not self._check_password(password, user.get("password_hash")):
                return {"success": False, "message": "Incorrect password."}
            
            if self._check_password(password, user.get('password_hash')):
                self.current_user =  {
                    "user_id" : user.get('user_id'),
                    "username" : user.get('username'),
                    "role" : user.get('role')
                }

            return {
            "success": True,
            "message": "Login successful.",
            "user": self.current_user,
            }
        except Error as db_err:
            return {"success": False, "message": f"Database error: {db_err}"}

        except Exception as e:
            return {"success": False, "message": f"Unexpected error: {e}"}


    def logout(self) -> Dict[str, Any]:
        """Clear current session."""
        self.current_user = None
        return {"success": True, "message": "Logout successful."}
    
    # ==========================================================
    # USER MANAGEMENT (ADMIN ONLY)
    # ==========================================================
    def promote_to_admin(self, username: str) -> Dict[str, Any]:
        self._require_admin()
        with self.conn.cursor() as cur:
            try:
                cur.execute("UPDATE users SET role = 'admin' WHERE username = %s", (username,))
                self.conn.commit()
                return {
                    "success": True if cur.rowcount > 0 else False,
                    "message": f"{username} promoted." if cur.rowcount > 0 else "User not found.",
                }
            
            except Exception as e:
                self.conn.rollback()
                return {"success": False, "message": f"Error: {e}"}

    def demote_to_user(self, username) -> Dict[str, Any]:
        self._require_admin()
        with self.conn.cursor() as cur:
            try:
                cur.execute("UPDATE users SET role = 'user' WHERE username = %s", (username,))
                self.conn.commit()
                return {
                    "success": True if cur.rowcount > 0 else False,
                    "message": f"{username} demoted." if cur.rowcount > 0 else "User not found.",
                }
            except Exception as e:
                self.conn.rollback()
                return {"success": False, "message": f"Error: {e}"}

    def deactivate_user(self, username: str) -> Dict[str, Any]:
        self._require_admin()
        with self.conn.cursor() as cur:

            try:
                cur.execute("UPDATE users SET is_active = 0 WHERE username = %s", (username,))
                self.conn.commit()
                return {
                    "success": True if cur.rowcount > 0 else False,
                    "message": f"{username} deactivated." if cur.rowcount > 0 else "User not found.",
                }
            except Exception as e:
                self.conn.rollback()
                return {"success": False, "message": f"Error: {e}"}


    def activate_user(self, username: str) -> Dict[str, Any]:
        self._require_admin()
        with self.conn.cursor() as cur:
            try:
                cur.execute("UPDATE users SET is_active = 1 WHERE username = %s", (username,))
                self.conn.commit()
                return {
                    "success": True if cur.rowcount > 0 else False,
                    "message": f"{username} activated." if cur.rowcount > 0 else "User not found.",
                } 
            except Exception as e:
                self.conn.rollback()
                return {"success": False, "message": f"Error: {e}"}

    def delete_user(self, username: str) -> bool:
        self._require_admin()
        with self.conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM users WHERE username = %s", (username,))
                self.conn.commit()
                return cur.rowcount > 0
            except Exception as e:
                self.conn.rollback()
                return {"success": False, "message": f"Error: {e}"}

    def list_users(self) -> Dict[str, Any]:
        """List all users."""
        try:
            self._require_admin()
            with self.conn.cursor(dictionary=True) as cur:
                cur.execute("SELECT user_id, username, role, is_active, created_at FROM users")
                users = cur.fetchall()
                return {"success": True, "users": users}
        except Exception as e:
            return {"success": False, "message": f"Error: {e}"}

    # ==========================================================
    # USER SELF-SERVICE FUNCTIONS
    # ==========================================================
    def change_password(self, username: str, new_password: str, secur_ans: str) -> Dict[str, Any]:
        """Allow user to change their password."""
        try:
            self._require_login()
            user = self._get_user_by_username(username)
            if not user:
                return {"success": False, "message": "User not found."}

            if not self._check_password(secur_ans, user.get('security_answer_hash')):
                return {"success": False, "message": "Incorrect security answer."}

            if len(new_password) < 6:
                return {"success": False, "message": "Password must be at least 6 characters long."}

            new_hash = self._hash(new_password)
            with self.conn.cursor() as cur:
                cur.execute("UPDATE users SET password_hash = %s WHERE username = %s", (new_hash, username))
                self.conn.commit()
                return {
                    "success": True if cur.rowcount > 0 else False,
                    "message": "Password updated successfully." if cur.rowcount > 0 else "No update made.",
                }

        except Exception as e:
            self.conn.rollback()
            return {"success": False, "message": f"Error: {e}"}

    def change_security_answer(self, username: str, new_answer: str) -> Dict[str, Any]:
        """Change user’s security answer."""
        try:
            self._require_login()
            new_hash = self._hash(new_answer)
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET security_answer_hash = %s WHERE username = %s",
                    (new_hash, username),
                )
                self.conn.commit()
                return {
                    "success": True if cur.rowcount > 0 else False,
                    "message": "Security answer updated successfully."
                    if cur.rowcount > 0
                    else "No update made.",
                }

        except Exception as e:
            self.conn.rollback()
            return {"success": False, "message": f"Error: {e}"}

    def get_all_user_details(self, username: str, *, password: Optional[str], security_answer: Optional[str]) -> Dict[str, Any]:
        """
        Return all users' details (admin or user) only if the provided credentials 
        match the current logged-in user.
        """
        try:
            # Ensure someone is logged in
            self._require_login()

            # Fetch current user's stored record
            user = self._get_user_by_username(self.current_user.get("username"))
            if not user:
                return {"success": False, "message": "Current user not found."}
            
            if not password or not security_answer:
                raise ValueError("Input either Password or Security answer.....OR both")

            # Verify that provided credentials belong to the current user
            if username != user.get("username"):
                return {"success": False, "message": "Invalid username for current user."}
            if password:
                if not self._check_password(password, user.get("password_hash")):
                    return {"success": False, "message": "Incorrect password."}
            if security_answer:
                if not self._check_password(security_answer, user.get("security_answer_hash")):
                    return {"success": False, "message": "Incorrect security answer."}
                


            # Fetch all users
            with self.conn.cursor(dictionary=True) as cur:
                cur.execute(
                    "SELECT user_id, username, role, is_active, created_at, updated_at FROM users"
                )
                users = cur.fetchall()

            return {
                "success": True,
                "message": "User details retrieved successfully.",
                "users": users,
            }

        except PermissionError as e:
            return {"success": False, "message": str(e)}

        except Exception as e:
            return {"success": False, "message": f"Error retrieving user details: {e}"}


    # ==========================================================
    # CLEANUP
    # ==========================================================

    def close(self):
        """Gracefully close the connection."""
        if self.conn:
            try:
                self.conn.close()
                self.conn = None
            except Exception:
                pass