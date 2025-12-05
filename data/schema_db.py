
import mysql.connector

# Connect to your local database
conn = mysql.connector.connect(
    host="127.0.0.1",
    user="root",           # change to your username
    password="kevindebRyan17.",  # change to your password
    database="budget_tracker"   # change to your database
)

cur = conn.cursor()
cur.execute("SHOW TABLES")

# Open file to write schema
with open("seeds.sql", "w") as f:
    for (table_name,) in cur.fetchall():
        # Get CREATE statement
        cur.execute(f"SHOW CREATE TABLE {table_name}")
        create_stmt = cur.fetchone()[1]

        # Write DROP + CREATE
        f.write(f"DROP TABLE IF EXISTS `{table_name}`;\n")
        f.write(create_stmt + ";\n\n")

cur.close()
conn.close()
