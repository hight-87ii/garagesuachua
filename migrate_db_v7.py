import sqlite3

def migrate():
    conn = sqlite3.connect('garage.db')
    cursor = conn.cursor()

    columns_to_add = [
        ("appointment_time", "VARCHAR"),  # Khung giờ hẹn (HH:MM) cho trang đặt lịch
    ]

    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE appointments ADD COLUMN {col_name} {col_type}")
            print(f"Added column {col_name} successfully.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"Column {col_name} already exists.")
            else:
                print(f"Error adding {col_name}: {e}")

    conn.commit()
    conn.close()
    print("Migration v7 completed.")

if __name__ == "__main__":
    migrate()
