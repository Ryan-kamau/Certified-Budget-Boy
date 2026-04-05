#database connection setup
import mysql.connector
from importlib.resources import files
import os
import sys
from mysql.connector import Error
import configparser
from fintrack.core.utils import ConfigurationError, error_logger
from pathlib import Path

class DatabaseConnection:
    def __init__(self):
        self.connection = None


    def _get_runtime_root(self) -> Path:
        """Return the correct runtime root across all environments."""

        # ── PyInstaller (onefile temp extraction) ──
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)

        # ── PyInstaller (onedir / exe location) ──
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent

        # ── Pip install or dev ──
        return Path.cwd()

    def _load_config(self):
        """Load DB config with fallback + setup integration."""
        config = configparser.ConfigParser()

        # ── 1. ENV override (highest priority) ───────────────────
        env_path = os.getenv("FINTRACK_CONFIG")
        if env_path:
            config_path = Path(env_path)
        else:
            # ── 2. Default runtime location ───────────────────────
            config_path = self._get_runtime_root() / "config" / "config.ini"

        # ── 3. If config missing → guide user to setup ───────────
        if not config_path.exists():
            try:
                template = files("fintrack.config").joinpath("config.template.ini")
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(template.read_text())
            except Exception:
                pass
            raise ConfigurationError(
                f"Config file not found at {config_path}\n\n"
                "Run setup first:\n"
                "  fintrack-setup\n"
                "  OR\n"
                "  budget-tracker --setup"
            )

        # ── 4. Load config ───────────────────────────────────────
        config.read(config_path)

        if "mysql" not in config:
            raise ConfigurationError(
                f"Invalid config file: {config_path}\n"
                "Missing [mysql] section."
            )

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
            error_logger.log_error(
                e,
                location="DatabaseConnection.get_connection",
                extra="host=" + str(db_config.get("host", "unknown")) +
                      ", database=" + str(db_config.get("database", "unknown")),
            )
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
        self.close_connection()


        
if __name__ == "__main__":
    db = DatabaseConnection()
    connection = db.get_connection()
    if connection:
        print("Connection test passed ✅")
        db.close_connection()

    
         



    
