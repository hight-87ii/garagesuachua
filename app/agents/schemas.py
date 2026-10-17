"""Schema chuan cho AI agents (thay query param roi rac).

- ChatIn: customer agent chat/tu van/dat lich nhap.
- DiagnoseIn: technical agent chan doan.
- RBAC giu nguyen o rbac.py (require_roles); auth qua cookie JWT
  get_current_user (role doc lai tu DB, khong tin token).
"""
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    vehicle_id: Optional[int] = None
    history: List[Any] = Field(default_factory=list)


class DiagnoseIn(BaseModel):
    symptom: str = Field(..., min_length=1, max_length=2000)
    license_plate: Optional[str] = Field(default=None, max_length=20)
    history: List[Any] = Field(default_factory=list)


class ManagerChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: List[Any] = Field(default_factory=list)


class MaintenanceIn(BaseModel):
    """Maintenance agent: phan tich ODO/lich su + nhac bao duong theo xe.

    - message: cau hoi/yeu cau tu nhien.
    - vehicle_id: xe can chan doan bao duong (tuy chon; khach chi duoc xe cua minh).
    """
    message: str = Field(..., min_length=1, max_length=2000)
    vehicle_id: Optional[int] = None
    history: List[Any] = Field(default_factory=list)


class BillingIn(BaseModel):
    """Billing agent: bao gia + hoa don (ban nhap) + cong no.

    - message: cau hoi/yeu cau tu nhien.
    - order_id: phieu sua chua can bao gia (tuy chon; co the doc tu '#id').
    - discount_percent: % giam gia ap dung khi tinh (tuy chon).
    """
    message: str = Field(..., min_length=1, max_length=2000)
    order_id: Optional[int] = None
    discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    history: List[Any] = Field(default_factory=list)


class InventoryIn(BaseModel):
    """Inventory agent: kiem tra ton kho, canh bao, goi y phu tung, du doan nhap.

    - message: cau hoi/yeu cau tu nhien.
    - vehicle_id: scope goi y phu tung theo xe (tuy chon).
    - part_number: tra cuu 1 ma phu tung tuong minh (tuy chon).
    """
    message: str = Field(..., min_length=1, max_length=2000)
    vehicle_id: Optional[int] = None
    part_number: Optional[str] = Field(default=None, max_length=50)
    history: List[Any] = Field(default_factory=list)


class ScheduleIn(BaseModel):
    """Scheduling & Reception agent: lich hen + tiep nhan.

    - message: cau hoi/yeu cau tu nhien.
    - vehicle_id / appointment_id: tro tường minh (an toan hon parse cau).
    - date / time / preferred_technician_id: goi y cua UI (tuy chon).
    """
    message: str = Field(..., min_length=1, max_length=2000)
    vehicle_id: Optional[int] = None
    appointment_id: Optional[int] = None
    date: Optional[str] = Field(default=None, max_length=20)
    time: Optional[str] = Field(default=None, max_length=10)
    preferred_technician_id: Optional[int] = None
    history: List[Any] = Field(default_factory=list)
