"""Rate limit chong spam key Gemini cho 2 endpoint agent.

- 20 req / 60s / user (key = username `sub`, fallback IP client).
- Sliding window bang list timestamp + Lock (memory single-process).
- Qua han -> 429 + header Retry-After (giay).
- dependencies khai bao SAU require_roles nen 401/403 (auth/RBAC) chay
  truoc: request chua login / sai role khong bi dem.
- Gioi han: multi-worker khong share dem (can Redis de share).
"""
import time
from threading import Lock
from fastapi import Depends, HTTPException, Request
from app.routers.auth import get_current_user

RATE_LIMIT_MAX_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 60

_hits: dict[str, list[float]] = {}
_lock = Lock()


def _now() -> float:
    return time.time()


def check_rate_limit(key: str,
                     max_requests: int = RATE_LIMIT_MAX_REQUESTS,
                     window: int = RATE_LIMIT_WINDOW_SECONDS) -> int:
    """Tra 0 neu cho phep (da ghi nhan hit); nguoc lai so giay cho."""
    now = _now()
    with _lock:
        lst = [t for t in _hits.get(key, []) if now - t < window]
        if len(lst) >= max_requests:
            retry = int(window - (now - lst[0])) + 1
            _hits[key] = lst
            return retry
        lst.append(now)
        _hits[key] = lst
        return 0


def reset_rate_limit(key: str | None = None) -> None:
    """Xoa dem (cho test). None = xoa het."""
    with _lock:
        if key is None:
            _hits.clear()
        else:
            _hits.pop(key, None)


async def agent_rate_limit(request: Request, user: dict = Depends(get_current_user)):
    """Dependency dung chung cho 2 endpoint agent. get_current_user duoc
    FastAPI cache trong request nen khong query DB lan 2."""
    sub = (user or {}).get("sub")
    client_ip = request.client.host if getattr(request, "client", None) else "unknown"
    retry = check_rate_limit(f"agent:{sub or client_ip}")
    if retry:
        raise HTTPException(
            status_code=429,
            detail="Bạn thao tác quá nhanh. Vui lòng thử lại sau ít giây.",
            headers={"Retry-After": str(retry)},
        )
    return user
