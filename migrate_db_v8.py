import sqlite3


def migrate():
    conn = sqlite3.connect("garage.db")
    cursor = conn.cursor()
    columns_to_add = [
        ("repair_started_at", "DATETIME"),
        ("repair_notes", "TEXT"),
    ]

    for column_name, column_type in columns_to_add:
        try:
            cursor.execute(
                f"ALTER TABLE repair_orders ADD COLUMN {column_name} {column_type}"
            )
            print(f"Added column {column_name} successfully.")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                print(f"Column {column_name} already exists.")
            else:
                raise

    # Phiếu đang sửa từ trước chưa có mốc bắt đầu: dùng giờ tiếp nhận
    # (hoặc giờ tạo phiếu) để giao diện không bị trống.
    cursor.execute(
        """
        UPDATE repair_orders
        SET repair_started_at = COALESCE(NULLIF(reception_datetime, ''), created_at)
        WHERE status = 'In Progress' AND repair_started_at IS NULL
        """
    )

    conn.commit()
    conn.close()
    print("Migration v8 completed.")


if __name__ == "__main__":
    migrate()
