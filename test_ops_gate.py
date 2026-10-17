"""P8-05/06 ops gate: health/env policy/CSRF/quota/backup restore drill."""
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.csrf import CSRF_COOKIE_NAME, CSRF_HEADER, csrf_protect
from app.database import Base
from app.models.models import User
from app.agents.schemas import DiagnoseIn
from app.agents.technical_agent.router import diagnose_vehicle
import ops_backup


class _URL:
    path = "/agent/customer/chat"


class _Req:
    method = "POST"
    url = _URL()
    cookies = {"access_token": "jwt", CSRF_COOKIE_NAME: "csrf-ok"}
    headers = {"content-type": "application/json", "accept": "application/json"}

    async def body(self):
        return b"{}"

    async def form(self):
        return {}


async def _next(_request):
    return JSONResponse({"ok": True})


def test_ops_gate_health_env_csrf_quota_backup():
    # Env policy source of truth.
    from app.routers import auth
    assert len(auth.SECRET_KEY) >= 32
    assert isinstance(auth.COOKIE_SECURE, bool)

    # /health exists and returns deploy-check OK.
    import main
    assert asyncio.run(main.health_check())["status"] == "ok"

    # CSRF JSON: missing header -> 403; matching header -> pass.
    resp = asyncio.run(csrf_protect(_Req(), _next))
    assert resp.status_code == 403
    req_ok = _Req()
    req_ok.headers = {"content-type": "application/json", CSRF_HEADER: "csrf-ok"}
    resp_ok = asyncio.run(csrf_protect(req_ok, _next))
    assert resp_ok.status_code == 200

    # Quota 429 từ Gemini wrapper -> router 503 TV, không crash.
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    db.add(User(username="ops_tech", password_hash="x", full_name="T", phone="1", role="technician", is_active=1))
    db.commit()
    try:
        with patch("app.services.gemini_service.get_gemini_response", side_effect=Exception("429 Quota exceeded")), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""):
            try:
                asyncio.run(diagnose_vehicle(DiagnoseIn(symptom="máy rung"), db, {"sub": "ops_tech", "role": "technician"}))
            except HTTPException as e:
                assert e.status_code == 503
                assert "giới hạn" in e.detail
            else:
                raise AssertionError("quota phải trả 503 TV")
    finally:
        db.close()

    # Backup/restore drill trong temp root: garage.db + data/chroma_db.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        root = Path(td)
        old_root, old_backup, old_db, old_chroma = ops_backup.ROOT, ops_backup.BACKUP_ROOT, ops_backup.DB_FILES, ops_backup.CHROMA_DIR
        ops_backup.ROOT = root
        ops_backup.BACKUP_ROOT = root / "backup" / "ops"
        ops_backup.DB_FILES = [root / "garage.db", root / "garage.db-wal", root / "garage.db-shm"]
        ops_backup.CHROMA_DIR = root / "data" / "chroma_db"
        try:
            with __import__("sqlite3").connect(root / "garage.db") as conn:
                conn.execute("CREATE TABLE smoke(id INTEGER PRIMARY KEY)")
            ops_backup.CHROMA_DIR.mkdir(parents=True)
            (ops_backup.CHROMA_DIR / "index.txt").write_text("ok", encoding="utf-8")
            dest = ops_backup.create_backup()
            vr = ops_backup.verify_restore(dest)
            assert vr["ok"] is True and vr["tables"] >= 1 and vr["chroma_present"] is True
        finally:
            ops_backup.ROOT, ops_backup.BACKUP_ROOT, ops_backup.DB_FILES, ops_backup.CHROMA_DIR = old_root, old_backup, old_db, old_chroma
