import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.models import User

def export_users_to_files():
    db = SessionLocal()
    
    # 1. Export Customers
    customers = db.query(User).filter(User.role == "customer").all()
    with open("accounts_customer.md", "w", encoding="utf-8") as f:
        f.write("# Danh sách tài khoản Khách hàng\n\n")
        f.write("| ID | Tài khoản (Username) | Mật khẩu | Họ và Tên | Điện thoại | Email |\n")
        f.write("|---|---|---|---|---|---|\n")
        for u in customers:
            pwd = "123" if u.username.startswith("kh_") or u.username == "khachhang" else "(Đã mã hóa)"
            f.write(f"| {u.id} | {u.username} | {pwd} | {u.full_name or ''} | {u.phone or ''} | {u.email or ''} |\n")
            
    # 2. Export Technicians
    technicians = db.query(User).filter(User.role == "technician").all()
    with open("accounts_technician.md", "w", encoding="utf-8") as f:
        f.write("# Danh sách tài khoản Kỹ thuật viên\n\n")
        f.write("| ID | Tài khoản (Username) | Mật khẩu | Họ và Tên | Điện thoại | Email |\n")
        f.write("|---|---|---|---|---|---|\n")
        for u in technicians:
            f.write(f"| {u.id} | {u.username} | 123 | {u.full_name or ''} | {u.phone or ''} | {u.email or ''} |\n")

    # 3. Export Managers (and admin)
    managers = db.query(User).filter(User.role.in_(["manager", "admin"])).all()
    with open("accounts_manager.md", "w", encoding="utf-8") as f:
        f.write("# Danh sách tài khoản Quản lý / Admin\n\n")
        f.write("| ID | Tài khoản (Username) | Mật khẩu | Chức vụ | Họ và Tên | Điện thoại | Email |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for u in managers:
            f.write(f"| {u.id} | {u.username} | 123 | {u.role.upper()} | {u.full_name or ''} | {u.phone or ''} | {u.email or ''} |\n")

    db.close()
    print("Exported 3 files successfully.")

if __name__ == "__main__":
    export_users_to_files()
