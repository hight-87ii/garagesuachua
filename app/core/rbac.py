from enum import Enum
from fastapi import HTTPException, Depends
from app.routers.auth import get_current_user

class Role(str, Enum):
    TECHNICIAN = "technician"
    CUSTOMER = "customer"
    MANAGER = "manager"
    ADMIN = "admin"

def require_roles(allowed_roles: list[Role]):
    def role_checker(user: dict = Depends(get_current_user)):
        allowed_values = {role.value for role in allowed_roles}
        user_role = user.get("role")
        if user_role not in allowed_values and user_role != Role.ADMIN.value:
            raise HTTPException(
                status_code=403, 
                detail=f"Không có quyền truy cập. Yêu cầu quyền: {[r.value for r in allowed_roles]}"
            )
        return user
    return role_checker
