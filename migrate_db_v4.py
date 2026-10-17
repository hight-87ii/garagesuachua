import sqlite3

db_path = "garage.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE appointments ADD COLUMN appointment_type VARCHAR DEFAULT 'Repair'")
    print("Added appointment_type to appointments")
except sqlite3.OperationalError as e:
    print(f"Error (appointments): {e}")

try:
    cursor.execute("ALTER TABLE repair_orders ADD COLUMN order_type VARCHAR DEFAULT 'Repair'")
    print("Added order_type to repair_orders")
except sqlite3.OperationalError as e:
    print(f"Error (repair_orders): {e}")

conn.commit()
conn.close()
