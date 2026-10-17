"""Quét dọn lịch hẹn: quá hẹn tự hủy + xóa lịch đã hủy quá hạn."""
from datetime import datetime, timedelta

NOSHOW_GRACE_HOURS = 24


def _appt_deadline(appt):
    """Mốc quá hẹn = ngày + giờ hẹn + 24h. Thiếu giờ thì tính hết ngày hẹn."""
    try:
        d = datetime.strptime((appt.appointment_date or "").strip(), "%Y-%m-%d")
    except (ValueError, AttributeError):
        return None
    t = (appt.appointment_time or "").strip()
    try:
        hh, mm = t.split(":")[:2]
        d = d.replace(hour=int(hh), minute=int(mm))
    except (ValueError, AttributeError):
        d = d.replace(hour=23, minute=59)
    return d + timedelta(hours=NOSHOW_GRACE_HOURS)


def auto_cancel_noshow(db) -> int:
    """Hủy lịch hẹn thành công nhưng quá 24h sau giờ hẹn vẫn không tới xưởng.

    Chỉ áp dụng khi phiếu sửa chữa liên kết chưa được tiếp nhận (chưa có
    reception_datetime). Trả về số lịch vừa bị hủy.
    """
    from app.models.models import Appointment, RepairOrder
    now = datetime.utcnow()
    pending = db.query(Appointment).filter(
        Appointment.status.in_(["Pending", "Confirmed"])
    ).all()
    n = 0
    for appt in pending:
        deadline = _appt_deadline(appt)
        if deadline is None or deadline > now:
            continue
        linked = db.query(RepairOrder).filter(
            RepairOrder.appointment_id == appt.id
        ).all()
        # Khách đã tới (đã tiếp nhận xe) thì không phải no-show
        if any(o.reception_datetime for o in linked):
            continue
        appt.status = "Cancelled"
        appt.cancelled_at = now
        n += 1
        # Phiếu chưa làm gì thì hủy theo để khỏi kẹt bảng việc
        for order in linked:
            if order.status == "Pending" and not order.reception_datetime and not order.invoice:
                order.status = "Cancelled"
    if n:
        db.commit()
    return n
