#database connection setup
import mysql.connector
from mysql.connector import Error
import configparser
import os

class DatabaseConnection:
    def __init__(self):
        self.connection = None

    def _load_config(self):
        """Reads database credentials from config/config.ini safely."""
        config = configparser.ConfigParser()

        #connect database path with config.ini path
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(BASE_DIR, "config", "config.ini")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"⚠️ Config file not found: {config_path}")
        
        config.read(config_path)

        return {
            'host' : config.get('mysql', 'host'),
            'user' : config.get('mysql', 'user'),
            'password' : config.get('mysql', 'password'),
            'database' : config.get('mysql', 'database'),
            'port' : config.getint('mysql', 'port')
        }

    def get_connection(self):
        """Establishes a connection to the MySQL database."""
        try:
            db_config = self._load_config()
            self.connection = mysql.connector.connect(**db_config)

            if self.connection.is_connected():
                print("✅ Database connection successful.")
            return self.connection
            
        except Error as e:
            print(f"❌ Error connecting to MySQL: {e}")
            self.connection =  None
        

    def close_connection(self):
        """Closes the given MySQL connection."""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            print("🔌 Connection closed.")
        
        # ---------- Context Management ----------
    def __enter__(self):
        """Used for 'with' statements."""
        self.get_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Automatically closes connection when leaving context."""
        self.close()


        
if __name__ == "__main__":
    db = DatabaseConnection()
    connection = db.get_connection()
    if connection:
        print("Connection test passed ✅")
        db.close_connection()

    
         



    
