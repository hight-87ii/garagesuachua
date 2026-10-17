"""Test logging/monitoring AI agent: JSONL rotation-safe, PII-safe, dashboard stats."""
import json
import logging
import tempfile
from pathlib import Path

from app.core import agent_monitor as am


def _reset_logger_handlers():
    lg = logging.getLogger(am.LOGGER_NAME)
    for h in list(lg.handlers):
        h.close()
        lg.removeHandler(h)


def main():
    old_dir, old_file = am.LOG_DIR, am.LOG_FILE
    with tempfile.TemporaryDirectory() as td:
        am.LOG_DIR = Path(td)
        am.LOG_FILE = Path(td) / "agent.log"
        _reset_logger_handlers()
        try:
            am.log_agent_call(agent="customer", user_id=1, vehicle_id=2,
                              prompt_len=1234, ok=True, latency_ms=50)
            am.log_agent_call(agent="technical", user_id=3, vehicle_id=None,
                              prompt_len=4321, ok=False, latency_ms=75, error="quota")
            am.log_agent_call(agent="technical", user_id=3, vehicle_id=9,
                              prompt_len=100, ok=False, latency_ms=80, error="503")

            rows = [json.loads(line) for line in am.LOG_FILE.read_text(encoding="utf-8").splitlines()]
            assert len(rows) == 3, rows
            assert rows[0]["user_id"] == 1 and rows[0]["vehicle_id"] == 2
            assert rows[0]["prompt_len"] == 1234 and rows[0]["ok"] is True
            # Không log prompt/tên/biển số/raw PII.
            forbidden = {"prompt", "message", "full_name", "license_plate", "plate"}
            assert not (forbidden & set(rows[0].keys())), rows[0]

            stats = am.read_agent_daily_stats(days=1)
            assert stats["today"]["total"] == 3, stats
            assert stats["today"]["ok"] == 1 and stats["today"]["fail"] == 2, stats
            assert stats["today"]["quota"] == 1 and stats["today"]["503"] == 1, stats
            assert am.classify_agent_error("Hệ thống AI đã vượt quá giới hạn truy cập") == "quota"
            assert am.classify_agent_error("Hệ thống AI hiện đang quá tải") == "503"
            assert am.mask_sensitive_id("70R-111.11").startswith("***1111#")
            print("ALL AGENT MONITOR CASES PASSED.")
        finally:
            _reset_logger_handlers()
            am.LOG_DIR, am.LOG_FILE = old_dir, old_file


if __name__ == "__main__":
    main()
