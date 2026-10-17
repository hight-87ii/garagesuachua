"""Migration: them cot vong doi nhan su cho bang users.

Chay 1 lan:  python migrate_active.py
An toan chay lai nhieu lan (kiem tra PRAGMA truoc khi ALTER).
"""
import sqlite3

DB = "garage.db"
COLS = [
    ("is_active", "INTEGER NOT NULL DEFAULT 1"),
    ("leave_reason", "VARCHAR"),
    ("leave_date", "VARCHAR"),
    ("return_date", "VARCHAR"),
]

def main():
    db = sqlite3.connect(DB)
    have = {c[1] for c in db.execute("PRAGMA table_info(users)").fetchall()}
    for name, ddl in COLS:
        if name in have:
            print(f"exists, skip: {name}")
            continue
        db.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")
        print(f"added: {name}")
    db.commit()
    # Tai khoan cu mac dinh dang hoat dong
    db.execute("UPDATE users SET is_active = 1 WHERE is_active IS NULL")
    db.commit()
    db.close()
    print("migrate_active done.")

if __name__ == "__main__":
    main()
