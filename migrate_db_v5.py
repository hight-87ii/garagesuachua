import sqlite3

def migrate():
    conn = sqlite3.connect('garage.db')
    cursor = conn.cursor()

    columns_to_add = [
        ("vehicle_images", "TEXT"),
        ("symptom_severity", "VARCHAR"),
        ("abnormal_sounds", "VARCHAR"),
        ("warning_lights", "VARCHAR"),
        ("key_count", "INTEGER")
    ]

    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE repair_orders ADD COLUMN {col_name} {col_type}")
            print(f"Added column {col_name} successfully.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"Column {col_name} already exists.")
            else:
                print(f"Error adding {col_name}: {e}")

    conn.commit()
    conn.close()
    print("Migration v5 completed.")

if __name__ == "__main__":
    migrate()
