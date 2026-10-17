import sqlite3
import datetime

db_path = "garage.db"

new_columns = [
    # Kỹ thuật
    ("oem_code", "VARCHAR"),
    ("manufacturer_code", "VARCHAR"),
    ("brand", "VARCHAR"),
    ("origin", "VARCHAR"),
    ("dimensions", "VARCHAR"),
    ("unit", "VARCHAR"),
    ("weight", "VARCHAR"),
    ("shelf_life", "VARCHAR"),
    # Tương thích
    ("compatible_make", "VARCHAR"),
    ("compatible_model", "VARCHAR"),
    ("compatible_year", "VARCHAR"),
    ("compatible_version", "VARCHAR"),
    ("compatible_engine", "VARCHAR"),
    ("compatible_fuel", "VARCHAR"),
    # Kho hàng
    ("warehouse", "VARCHAR"),
    ("shelf_location", "VARCHAR"),
    ("min_stock", "INTEGER DEFAULT 0"),
    ("max_stock", "INTEGER DEFAULT 0"),
    ("status", "VARCHAR DEFAULT 'Đang kinh doanh'"),
    # Nhập hàng
    ("supplier", "VARCHAR"),
    ("supplier_code", "VARCHAR"),
    ("purchase_price", "INTEGER DEFAULT 0"),
    ("vat_rate", "VARCHAR"),
    ("first_import_date", "VARCHAR"),
    # Bảo hành
    ("has_warranty", "VARCHAR"),
    ("warranty_period", "VARCHAR"),
    ("warranty_conditions", "TEXT"),
    ("warranty_notes", "TEXT"),
    # Mã vạch
    ("barcode", "VARCHAR"),
    ("qrcode", "VARCHAR"),
    ("serial_number", "VARCHAR"),
    # Lịch sử
    ("created_by", "VARCHAR"),
    ("created_at", "DATETIME"),
    ("updated_by", "VARCHAR"),
    ("updated_at", "DATETIME")
]

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

for col_name, col_type in new_columns:
    try:
        cursor.execute(f"ALTER TABLE spare_parts ADD COLUMN {col_name} {col_type}")
        print(f"Added column {col_name}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print(f"Column {col_name} already exists")
        else:
            print(f"Error adding {col_name}: {e}")
            
# Fill existing created_at
cursor.execute("UPDATE spare_parts SET created_at = ? WHERE created_at IS NULL", (datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f"),))
conn.commit()
conn.close()
print("Migration v2 completed.")
