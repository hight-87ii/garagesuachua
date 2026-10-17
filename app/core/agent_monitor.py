"""Agent call logging + dashboard counters.

Log dạng JSON-lines vào ``logs/agent.log`` (có rotation). Mỗi record chỉ chứa
metadata vận hành: user_id, vehicle_id, độ dài prompt, ok/fail, latency, lỗi
đã phân loại. Không ghi full prompt, tên khách/KTV, biển số hay traceback.
"""
from __future__ import annotations

import json
import logging
import hashlib
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Any


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "agent.log"
LOGGER_NAME = "threeh.agent_calls"


def _agent_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    target = os.path.abspath(str(LOG_FILE))
    if not any(isinstance(h, RotatingFileHandler) and getattr(h, "_agent_log_file", None) == target
               for h in logger.handlers):
        handler = RotatingFileHandler(
            LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        handler._agent_log_file = target  # type: ignore[attr-defined]
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def classify_agent_error(message: str | None) -> str | None:
    """Nhóm lỗi để dashboard bắt quota/503 Gemini nhanh."""
    text = (message or "").lower()
    if not text:
        return "empty"
    if "vượt quá giới hạn" in text or "quota" in text or "429" in text:
        return "quota"
    if "quá tải" in text or "503" in text or "unavailable" in text:
        return "503"
    return "other"


def mask_sensitive_id(value: str | None) -> str | None:
    """Mask định danh nhạy cảm (VD biển số) để log audit không lộ PII."""
    if not value:
        return None
    raw = "".join(ch for ch in str(value).upper() if ch.isalnum())
    if len(raw) <= 4:
        return "***"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"***{raw[-4:]}#{digest}"


def log_agent_call(*, agent: str, user_id: int | None, vehicle_id: int | None,
                   prompt_len: int, ok: bool, latency_ms: int,
                   error: str | None = None) -> None:
    record: dict[str, Any] = {
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "date": date.today().isoformat(),
        "agent": agent,
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "prompt_len": int(prompt_len or 0),
        "ok": bool(ok),
        "latency_ms": int(latency_ms or 0),
        "error": error if not ok else None,
    }
    try:
        _agent_logger().info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        # Logging không được làm hỏng request chính.
        logging.getLogger("threeh.agents").warning("agent call logging failed", exc_info=False)


def _iter_log_lines():
    files = [LOG_FILE] + [LOG_DIR / f"agent.log.{i}" for i in range(1, 6)]
    for path in files:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                yield from f
        except OSError:
            continue


def read_agent_daily_stats(days: int = 14) -> dict[str, Any]:
    """Đếm ok/fail/quota/503 theo ngày từ log để hiện ở dashboard manager."""
    today = date.today()
    start = today - timedelta(days=max(days - 1, 0))
    buckets: dict[str, dict[str, int]] = {}
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        buckets[d] = {"date": d, "total": 0, "ok": 0, "fail": 0, "quota": 0, "503": 0}

    for line in _iter_log_lines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        d = rec.get("date") or str(rec.get("ts", ""))[:10]
        if d not in buckets:
            continue
        b = buckets[d]
        b["total"] += 1
        if rec.get("ok"):
            b["ok"] += 1
        else:
            b["fail"] += 1
            err = rec.get("error")
            if err in ("quota", "503"):
                b[err] += 1

    series = [buckets[d] for d in sorted(buckets)]
    today_key = today.isoformat()
    totals = {"total": 0, "ok": 0, "fail": 0, "quota": 0, "503": 0}
    for b in series:
        for k in totals:
            totals[k] += b[k]
    return {"today": buckets.get(today_key, totals.copy()), "days": series, "totals": totals}
