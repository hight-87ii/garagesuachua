"""Chinh sach lich lam viec cua xuong — 1 nguon duy nhat cho moi duong dat lich.

- WORK_SLOTS: cac khung gio nhan xe (khop UI dat lich).
- HOLIDAYS_DDMM / HOLIDAYS_EXACT: ngay nghi (co dinh theo DD-MM va ngay cu the
  YYYY-MM-DD). Cau hinh them qua env GARAGE_HOLIDAYS_DDMM / GARAGE_HOLIDAYS.
- CLOSED_WEEKDAYS: thu trong tuan xuong nghi (0=Thu Hai ... 6=Chu Nhat).
  Mac dinh nghi Chu Nhat (khop "Thứ 2 - Thứ 7" o giao dien); doi qua
  GARAGE_CLOSED_WEEKDAYS (rong = mo ca tuan).

Khong import model/router -> an toan import tu bat ky dau (khong vong lap).
"""
from __future__ import annotations

import os
from datetime import datetime

try:  # Doc .env som de chinh sach nhan dung gia tri (khong bat buoc).
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Khung gio xuong nhan xe (08:00 - 17:00, nghi trua 11:30 - 13:30).
WORK_SLOTS = ["08:00", "09:00", "10:00", "10:30", "13:30", "14:30", "15:30", "16:30"]

_WEEKDAY_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm",
               "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

# Ngay le co dinh MAC DINH (DD-MM) — ngay le lon cua Viet Nam (duong lich).
_DEFAULT_HOLIDAYS_DDMM = ("01-01", "30-04", "01-05", "02-09")
# Thu nghi hang tuan MAC DINH: Chu Nhat (khop gio lam viec "Thứ 2 - Thứ 7").
_DEFAULT_CLOSED_WEEKDAYS = (6,)

HOLIDAYS_DDMM: set[str] = set()
HOLIDAYS_EXACT: set[str] = set()
CLOSED_WEEKDAYS: set[int] = set()


def _split_env(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


def reload_policy() -> None:
    """Doc lai chinh sach tu env (goi khi deploy / doi lich nghi)."""
    global HOLIDAYS_DDMM, HOLIDAYS_EXACT, CLOSED_WEEKDAYS
    HOLIDAYS_DDMM = set(_DEFAULT_HOLIDAYS_DDMM) | set(_split_env("GARAGE_HOLIDAYS_DDMM"))
    HOLIDAYS_EXACT = set(_split_env("GARAGE_HOLIDAYS"))
    # GARAGE_CLOSED_WEEKDAYS dat (ke ca rong) -> thay the mac dinh; khong dat -> mac dinh.
    raw_closed = os.getenv("GARAGE_CLOSED_WEEKDAYS")
    closed: set[int] = set() if raw_closed is not None else set(_DEFAULT_CLOSED_WEEKDAYS)
    for p in _split_env("GARAGE_CLOSED_WEEKDAYS"):
        try:
            wd = int(p)
        except ValueError:
            continue
        if 0 <= wd <= 6:
            closed.add(wd)
    CLOSED_WEEKDAYS = closed


reload_policy()


def is_valid_slot(time_str: str | None) -> bool:
    """True neu rong (chua chot gio) hoac gio nam trong WORK_SLOTS."""
    return not time_str or time_str in WORK_SLOTS


def day_off_reason(date_str: str | None) -> str | None:
    """Ly do xuong nghi cho ngay YYYY-MM-DD, nguoc lai None. Khong raise."""
    if not date_str:
        return None
    try:
        d = datetime.strptime(str(date_str).strip(), "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    key = d.strftime("%Y-%m-%d")
    if key in HOLIDAYS_EXACT or d.strftime("%d-%m") in HOLIDAYS_DDMM:
        return f"Xưởng nghỉ lễ ngày {d.strftime('%d/%m/%Y')}."
    if d.weekday() in CLOSED_WEEKDAYS:
        return (f"Xưởng nghỉ {_WEEKDAY_VI[d.weekday()]} hàng tuần "
                f"({d.strftime('%d/%m/%Y')}).")
    return None
