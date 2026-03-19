from core.database import DatabaseConnection
import mysql.connector

# Connect to your local database
db_connection = DatabaseConnection()
conn = db_connection.get_connection()


cur = conn.cursor()
cur.execute("SHOW TABLES")
tables = cur.fetchall()

# Open file to write schema
with open("seeds.sql", "w") as f:
    try:
        for (table_name,) in tables:
            # Get CREATE statement
            cur.execute(f"SHOW CREATE TABLE {table_name}")
            create_stmt = cur.fetchone()[1]

            # Write DROP + CREATE
            f.write(f"DROP TABLE IF EXISTS `{table_name}`;\n")
            f.write(create_stmt + ";\n\n")
            print(f"✔ Printed schema for {table_name}")
    except Exception as e:
        print(f"Failed to write {table_name} schema: {e}")
cur.close()
conn.close()
