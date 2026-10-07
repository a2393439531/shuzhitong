"""认证：登录 / 当前用户。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import create_token, verify_password
from ..database import get_conn
from ..deps import get_current_user, log_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


def user_dict(u) -> dict:
    return {
        "id": u["id"],
        "username": u["username"],
        "real_name": u["real_name"],
        "role": u["role"],
        "dept": u["dept"],
        "is_active": u["is_active"],
    }


@router.post("/login")
def login(body: LoginBody, request: Request):
    conn = get_conn()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (body.username,)
        ).fetchone()
    finally:
        conn.close()
    if user is None or not verify_password(
        body.password, user["password_hash"], user["salt"]
    ):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user["is_active"] == 0:
        raise HTTPException(status_code=403, detail="用户已被禁用")
    token = create_token(user["id"], user["username"])
    log_audit(user, "用户登录", f"用户 {user['username']} 登录成功", request)
    return {"token": token, "user": user_dict(user)}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return user_dict(user)
