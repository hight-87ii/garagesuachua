import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "garage.db")
conn = sqlite3.connect(db_path)
try:
    conn.execute("ALTER TABLE employee_profiles ADD COLUMN hire_date VARCHAR;")
    print("Added hire_date successfully")
except sqlite3.OperationalError as e:
    print(f"Error: {e}")
conn.commit()
conn.close()
