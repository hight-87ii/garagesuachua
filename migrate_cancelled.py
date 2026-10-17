import sqlite3
from datetime import datetime
con = sqlite3.connect("garage.db")
cur = con.cursor()
for table, col, ctype in [
    ("appointments", "cancelled_at", "DATETIME"),
    ("repair_orders", "appointment_id", "INTEGER"),
]:
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}")
        print("added", table, col)
    else:
        print("exists", table, col)
# Lich da huy tu truoc: lay moc hien tai de co them 1 ngay grace
now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
n = cur.execute("UPDATE appointments SET cancelled_at = ? WHERE status = 'Cancelled' AND cancelled_at IS NULL", (now,)).rowcount
con.commit()
print("backfilled cancelled:", n)
