"""Test rate-limit 20 req/phut/user cho 2 endpoint agent + audit bien so.

Chay: python test_rate_limit.py (exit 0 = pass het).
"""
import asyncio
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from unittest.mock import patch

from fastapi import HTTPException, Request

from app.core import rate_limit as rl


def _req():
    return Request({"type": "http", "method": "POST", "headers": [],
                    "path": "/", "client": ("127.0.0.1", 12345)})


async def case1_20_ok_21_429():
    """20 req dau pass, req 21 -> 429 + Retry-After."""
    rl.reset_rate_limit()
    user = {"sub": "rl_u1", "role": "customer"}
    try:
        for _ in range(20):
            out = await rl.agent_rate_limit(_req(), user)
            assert out is user
        try:
            await rl.agent_rate_limit(_req(), user)
        except HTTPException as e:
            assert e.status_code == 429, e.status_code
            assert "Retry-After" in (e.headers or {}), "thieu Retry-After"
            print("PASS rl-1 20 ok, 21 -> 429 + Retry-After")
        else:
            raise AssertionError("rl-1: req 21 phai 429")
    finally:
        rl.reset_rate_limit()


async def case2_window_reset_rieng_user():
    """Het window duoc reset; moi user dem rieng."""
    rl.reset_rate_limit()
    box = [1000.0]
    try:
        with patch.object(rl, "_now", side_effect=lambda: box[0]):
            for _ in range(20):
                assert rl.check_rate_limit("a", max_requests=20, window=60) == 0
            assert rl.check_rate_limit("a", max_requests=20, window=60) > 0
            assert rl.check_rate_limit("b", max_requests=20, window=60) == 0
            box[0] += 61
            assert rl.check_rate_limit("a", max_requests=20, window=60) == 0
        print("PASS rl-2 het window reset + bucket rieng user")
    finally:
        rl.reset_rate_limit()


async def case3_hai_endpoint_deu_wire():
    """Ca 7 route agent deu co Depends(agent_rate_limit)."""
    from app.agents.customer_agent.router import router as cr
    from app.agents.technical_agent.router import router as tr
    from app.agents.manager_agent.router import router as mr
    from app.agents.scheduling_agent.router import router as sr
    from app.agents.inventory_agent.router import router as ir
    from app.agents.billing_agent.router import router as br
    from app.agents.maintenance_agent.router import router as nr
    endpoints = ((cr, "/agent/customer/chat"), (tr, "/agent/technical/diagnose"),
                 (mr, "/agent/manager/chat"), (sr, "/agent/scheduling/chat"),
                 (ir, "/agent/inventory/chat"), (br, "/agent/billing/chat"),
                 (nr, "/agent/maintenance/chat"))
    for router, path in endpoints:
        route = next(r for r in router.routes if getattr(r, "path", "") == path)
        deps = [getattr(d, "dependency", None) for d in route.dependencies]
        assert rl.agent_rate_limit in deps, f"{path} thieu rate limit"
    print("PASS rl-3 ca 7 endpoint deu wire agent_rate_limit")


async def case4_audit_bien_so():
    """Technical resolve xe -> log audit bien so."""
    import logging
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.database import Base
    from app.models.models import User, Vehicle
    from app.agents.schemas import DiagnoseIn
    from app.agents.technical_agent.router import diagnose_vehicle

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    db.add(User(username="rl_tech", password_hash="x", full_name="T", phone="1",
                role="technician", is_active=1))
    db.flush()
    u = db.query(User).filter_by(username="rl_tech").first()
    db.add(Vehicle(license_plate="70R-111.11", make="Toyota", model="Vios", user_id=u.id))
    db.commit()
    records = []
    class Cap(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())
    handler = Cap()
    lg = logging.getLogger("threeh.agents")
    old_level = lg.level
    lg.setLevel(logging.INFO)
    lg.addHandler(handler)
    try:
        with patch("app.services.gemini_service.get_gemini_response", return_value="M"), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""):
            await diagnose_vehicle(DiagnoseIn(symptom="kêu", license_plate="70r-111.11"),
                                   db, {"sub": "rl_tech", "role": "technician"})
    finally:
        lg.removeHandler(handler)
        lg.setLevel(old_level)
        db.close()
    assert any("vehicle_id=" in m and "plate_ref=***" in m and "70R-111.11" not in m
               for m in records), records
    print("PASS rl-4 audit log masked plate + user_id")


async def main():
    await case1_20_ok_21_429()
    await case2_window_reset_rieng_user()
    await case3_hai_endpoint_deu_wire()
    await case4_audit_bien_so()
    print("ALL 4 RATE-LIMIT CASES PASSED (mock, khong can key that).")


if __name__ == "__main__":
    asyncio.run(main())
