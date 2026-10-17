"""Backup/restore drill vận hành cho ThreeH Workshop.

Backup hằng ngày:
    python ops_backup.py backup

Thử restore tuần/lần (không ghi đè dữ liệu thật, restore vào temp rồi kiểm tra):
    python ops_backup.py backup --verify-restore

Artifact gồm:
  - garage.db (+ -wal/-shm nếu có)
  - data/chroma_db/ nếu có
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parent
DB_FILES = [ROOT / "garage.db", ROOT / "garage.db-wal", ROOT / "garage.db-shm"]
CHROMA_DIR = ROOT / "data" / "chroma_db"
BACKUP_ROOT = ROOT / "backup" / "ops"


def _copy_path(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return True


def create_backup(dest_root: Path = BACKUP_ROOT) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = dest_root / stamp
    dest.mkdir(parents=True, exist_ok=False)
    copied = []
    for src in DB_FILES:
        if _copy_path(src, dest / src.name):
            copied.append(src.name)
    if _copy_path(CHROMA_DIR, dest / "data" / "chroma_db"):
        copied.append("data/chroma_db")
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(ROOT),
        "copied": copied,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not copied:
        raise RuntimeError("Không tìm thấy garage.db hoặc data/chroma_db để backup.")
    return dest


def verify_restore(backup_dir: Path) -> dict:
    """Restore vào temp dir và kiểm tra SQLite mở được + Chroma dir tồn tại nếu có."""
    backup_dir = backup_dir.resolve()
    if not backup_dir.exists():
        raise FileNotFoundError(backup_dir)
    with TemporaryDirectory(prefix="threeh_restore_", ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        db_src = backup_dir / "garage.db"
        if not db_src.exists():
            raise RuntimeError("Backup thiếu garage.db")
        db_dst = tmp / "garage.db"
        shutil.copy2(db_src, db_dst)
        conn = sqlite3.connect(db_dst)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
            tables = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        finally:
            conn.close()
        chroma_src = backup_dir / "data" / "chroma_db"
        chroma_ok = chroma_src.exists() and any(chroma_src.rglob("*"))
        return {"ok": True, "tables": tables, "chroma_present": bool(chroma_ok)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["backup", "verify-restore"])
    p.add_argument("--backup-dir", help="Thư mục backup để verify; mặc định dùng backup mới tạo.")
    p.add_argument("--verify-restore", action="store_true", help="Sau backup, restore thử vào temp dir.")
    args = p.parse_args()

    if args.command == "backup":
        dest = create_backup()
        print(f"BACKUP_OK {dest}")
        if args.verify_restore:
            print("RESTORE_VERIFY", json.dumps(verify_restore(dest), ensure_ascii=False))
    else:
        if not args.backup_dir:
            raise SystemExit("verify-restore cần --backup-dir")
        print("RESTORE_VERIFY", json.dumps(verify_restore(Path(args.backup_dir)), ensure_ascii=False))


if __name__ == "__main__":
    main()
