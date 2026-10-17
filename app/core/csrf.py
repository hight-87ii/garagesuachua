"""CSRF dùng mô hình Double Submit Cookie.

- Server đặt cookie `csrf_token` (đọc được bởi JS) khi đăng nhập.
- Mọi form POST (base.html) được JS tự chèn `<input name="csrf_token">`.
- Mọi `fetch` JSON được JS tự chèn header `x-csrf-token`.
- Middleware chỉ kiểm tra khi request đã có cookie đăng nhập,
  nên /login và /register được miễn kiểm tra.
"""
import secrets
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER = "x-csrf-token"

EXEMPT_PATHS = {
    "/login",
    "/register",
    "/logout",
    "/docs",
    "/redoc",
    "/openapi.json",
}

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _is_exempt(request: Request) -> bool:
    path = request.url.path
    if path.startswith("/static"):
        return True
    return path in EXEMPT_PATHS


async def csrf_protect(request: Request, call_next):
    if request.method in SAFE_METHODS or _is_exempt(request):
        return await call_next(request)

    # Chưa đăng nhập thì để router xử lý redirect, không chặn CSRF.
    if not request.cookies.get("access_token"):
        return await call_next(request)

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        sent_token = request.headers.get(CSRF_HEADER, "")
    else:
        try:
            # Đọc body trước để Starlette cache và replay cho route bên dưới.
            await request.body()
            form = await request.form()
            sent_token = form.get(CSRF_FORM_FIELD, "")
        except Exception:
            sent_token = ""

    if not cookie_token or not sent_token or not secrets.compare_digest(str(sent_token), cookie_token):
        if "application/json" in content_type or "application/json" in request.headers.get("accept", ""):
            return JSONResponse(status_code=403, content={"detail": "CSRF token không hợp lệ."})
        return RedirectResponse(url="/login", status_code=303)

    return await call_next(request)
