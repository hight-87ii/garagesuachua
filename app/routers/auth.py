from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
import os
from dotenv import load_dotenv

from app.database import get_db
from app.models.models import User
from app.core.csrf import CSRF_COOKIE_NAME, generate_csrf_token

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Cấu hình bảo mật
load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    raise RuntimeError("JWT_SECRET_KEY phải được cấu hình và dài ít nhất 32 ký tự.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
DEMO_ENABLED = os.getenv("SHOW_DEMO_ACCOUNTS", "true").lower() == "true"
REMEMBER_ME_EXPIRE_MINUTES = int(os.getenv("REMEMBER_ME_EXPIRE_MINUTES", "43200"))
JWT_ISSUER = "threeh-workshop"
JWT_AUDIENCE = "threeh-workshop-web"

def verify_password(plain_password, hashed_password):
    # Khắc phục lỗi tương thích bằng cách dùng bcrypt trực tiếp thay vì passlib
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except (AttributeError, TypeError, ValueError):
        return False

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_access_token(data: dict):
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "iat": now,
        "exp": expire,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_from_cookie(request: Request, db: Session | None = None):
    """Giải mã cookie và, nếu có DB session, xác thực lại tài khoản/role hiện tại."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["sub", "iat", "exp", "iss", "aud"]},
        )
    except jwt.InvalidTokenError:
        return None

    if db is None:
        return payload

    db_user = db.query(User).filter(User.username == payload["sub"]).first()
    if not db_user:
        return None
    # Tài khoản bị khóa (nghỉ việc/tạm nghỉ): coi như chưa đăng nhập ở mọi nơi.
    if getattr(db_user, "is_active", 1) == 0:
        return None

    # Không tin role/name trong token: luôn dùng dữ liệu hiện tại từ DB.
    payload["role"] = db_user.role
    payload["name"] = db_user.full_name
    payload["user_id"] = db_user.id
    return payload

def get_current_user(request: Request, db: Session = Depends(get_db)):
    """FastAPI dependency dùng chung cho mọi API cần đăng nhập."""
    user = get_current_user_from_cookie(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Vui lòng đăng nhập.")
    return user

class RoleChecker:
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles

    def __call__(self, user: dict = Depends(get_current_user)):
        allowed_roles = {getattr(role, "value", role) for role in self.allowed_roles}
        if user.get("role") not in allowed_roles and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập trang này.")
        return user

# --- GIAO DIỆN ---

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"demo_enabled": DEMO_ENABLED})


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request=request, name="forgot_password.html", context={"demo_enabled": DEMO_ENABLED})

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={})

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token", path="/", samesite="lax")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/", samesite="lax")
    return response

# --- API XỬ LÝ ---

@router.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(None),
    db: Session = Depends(get_db)
):
    # Kiểm tra xem tài khoản đã tồn tại chưa
    db_user = db.query(User).filter(User.username == username).first()
    if db_user:
        return templates.TemplateResponse(request=request, name="register.html", context={
            "error": "Tên đăng nhập đã tồn tại!"
        })
    
    # Tạo user mới (Mặc định là Khách hàng)
    new_user = User(
        username=username,
        password_hash=get_password_hash(password),
        full_name=full_name,
        phone=phone,
        email=email,
        role="customer"
    )
    db.add(new_user)
    db.commit()

    return RedirectResponse(url="/login?registered=1", status_code=302)


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    remember_me: str = Form(None),
    db: Session = Depends(get_db)
):
    # Tìm user
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request=request, name="login.html", context={
            "error": "Sai tên đăng nhập hoặc mật khẩu! Vui lòng kiểm tra lại.",
            "username": username,
            "demo_enabled": DEMO_ENABLED,
        })
    if getattr(user, "is_active", 1) == 0:
        return templates.TemplateResponse(request=request, name="login.html", context={
            "error": "Tài khoản đã bị khóa (nghỉ việc/tạm nghỉ). Vui lòng liên hệ quản lý.",
            "username": username,
            "demo_enabled": DEMO_ENABLED,
        })

    remember = remember_me == "1"
    expire_minutes = REMEMBER_ME_EXPIRE_MINUTES if remember else ACCESS_TOKEN_EXPIRE_MINUTES
    # Token chỉ định danh user; role và tên luôn được lấy lại từ DB ở mỗi request.
    token_data = {"sub": user.username}
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expire_minutes)
    token_data.update({"iat": now, "exp": expire, "iss": JWT_ISSUER, "aud": JWT_AUDIENCE})
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

    # Trả về chuyển hướng và set cookie
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=expire_minutes * 60,
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=generate_csrf_token(),
        httponly=False,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=expire_minutes * 60,
    )
    return response
