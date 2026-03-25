#!/usr/bin/env python3
"""
Export current MySQL schema into data/seeds.sql

Works from:
  - project root
  - scripts directory
  - module execution: python -m data.schema_db
"""

from pathlib import Path
from core.database import DatabaseConnection
import mysql.connector


# ─────────────────────────────────────────────────────────────
# Path Resolution (robust — works everywhere)
# ─────────────────────────────────────────────────────────────
def get_project_root() -> Path:
    """
    Walk up directories until we find a folder that looks like the project root.
    (contains 'core' or 'data')
    """
    current = Path(__file__).resolve()

    for parent in [current] + list(current.parents):
        if (parent / "core").exists() and (parent / "data").exists():
            return parent

    # fallback: 2 levels up
    return current.parent.parent


def get_output_path() -> Path:
    root = get_project_root()
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "seeds.sql"


# ─────────────────────────────────────────────────────────────
# Main Export Logic
# ─────────────────────────────────────────────────────────────
def export_schema():
    print("\n📦 Exporting database schema...\n")

    # Connect to DB
    db_connection = DatabaseConnection()
    conn = db_connection.get_connection()
    cur = conn.cursor()

    # Get output file path
    output_file = get_output_path()
    print(f"📁 Writing to: {output_file}\n")

    cur.execute("SHOW TABLES")
    tables = cur.fetchall()

    if not tables:
        print("⚠️ No tables found in database.")
        return

    with open(output_file, "w", encoding="utf-8") as f:
        for (table_name,) in tables:
            try:
                # Get CREATE TABLE statement
                cur.execute(f"SHOW CREATE TABLE `{table_name}`")
                create_stmt = cur.fetchone()[1]

                # Write schema
                f.write(f"-- Table: {table_name}\n")
                f.write(f"DROP TABLE IF EXISTS `{table_name}`;\n")
                f.write(create_stmt + ";\n\n")

                print(f"✔ Exported: {table_name}")

            except Exception as e:
                print(f"❌ Failed: {table_name} → {e}")

    cur.close()
    conn.close()

    print("\n🎉 Schema export complete!\n")


# ─────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    export_schema()