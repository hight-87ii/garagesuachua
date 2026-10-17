"""Migration v9: tạo 12 bảng agent platform + seed roles/agents + backfill user_roles.

Chạy: python migrate_db_v9_agent_tables.py
An toàn: dùng Base.metadata.create_all (chỉ CREATE TABLE IF NOT EXISTS),
không sửa/xóa bảng cũ. Chạy lại nhiều lần được (idempotent).
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy.orm import Session
from app.database import engine, Base, SessionLocal
import app.models.models as M  # noqa: F401 - đăng ký models vào Base


SEED_ROLES = [
    ("customer", "Khách hàng / chủ xe"),
    ("technician", "Kỹ thuật viên"),
    ("manager", "Quản lý xưởng"),
    ("admin", "Quản trị viên"),
]

SEED_AGENTS = [
    ("customer", "Customer Agent", "Tư vấn khách hàng, xe, lịch hẹn, hóa đơn.", "gemini-2.0-flash", 0.7, 600),
    ("technical", "Technical Agent", "Chẩn đoán kỹ thuật, phụ tùng, báo giá sơ bộ.", "gemini-2.0-flash", 0.4, 800),
    ("manager", "Manager Agent", "Vận hành xưởng, KPI, kho, lịch hẹn.", "gemini-2.0-flash", 0.4, 800),
]


def migrate():
    Base.metadata.create_all(bind=engine)
    print("create_all xong (12 bảng mới nếu chưa có).")

    db: Session = SessionLocal()
    try:
        # 1. Seed roles
        for name, desc in SEED_ROLES:
            if not db.query(M.Role).filter(M.Role.name == name).first():
                db.add(M.Role(name=name, description=desc))
        db.commit()

        # 2. Backfill user_roles từ cột users.role cũ
        roles = {r.name: r.id for r in db.query(M.Role).all()}
        users = db.query(M.User).all()
        added = 0
        for u in users:
            rname = (u.role or "customer").strip() or "customer"
            rid = roles.get(rname)
            if not rid:
                continue
            exists = db.query(M.UserRole).filter(
                M.UserRole.user_id == u.id, M.UserRole.role_id == rid).first()
            if not exists:
                db.add(M.UserRole(user_id=u.id, role_id=rid))
                added += 1
        db.commit()
        print(f"Backfill user_roles: +{added} dòng từ users.role.")

        # 3. Seed agents
        for code, name, desc, model, temp, mtok in SEED_AGENTS:
            if not db.query(M.Agent).filter(M.Agent.code == code).first():
                db.add(M.Agent(code=code, name=name, description=desc,
                               model=model, temperature=temp, max_tokens=mtok))
        db.commit()

        counts = {
            t: db.query(m).count() for t, m in [
                ("roles", M.Role), ("user_roles", M.UserRole), ("agents", M.Agent),
                ("conversations", M.Conversation), ("messages", M.Message),
                ("agent_runs", M.AgentRun), ("tasks", M.Task),
                ("tool_executions", M.ToolExecution), ("memories", M.Memory),
                ("approvals", M.Approval), ("audit_logs", M.AuditLog),
                ("external_identities", M.ExternalIdentity),
            ]
        }
        for k, v in counts.items():
            print(f"  {k}: {v}")
    finally:
        db.close()
    print("Migration v9 completed.")


if __name__ == "__main__":
    migrate()
