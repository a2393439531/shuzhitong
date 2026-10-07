"""请求依赖：JWT 鉴权与审计日志。原创实现。"""
from datetime import datetime

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import decode_token
from .database import get_conn

bearer = HTTPBearer(auto_error=False)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="token 无效")
    conn = get_conn()
    try:
        try:
            user_id = int(payload.get("sub"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=401, detail="token 无效")
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    if user["is_active"] == 0:
        raise HTTPException(status_code=403, detail="用户已被禁用")
    return user


def client_ip(request: Request | None) -> str:
    if request is None or request.client is None:
        return ""
    return request.client.host or ""


def log_audit(
    user,
    action: str,
    detail: str = "",
    request: Request | None = None,
    elapsed_ms: int = 0,
    result: str = "成功",
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO audit_log
               (user_id, username, action, detail, ip, elapsed_ms, result, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user["id"] if user is not None else None,
                user["username"] if user is not None else "",
                action,
                detail,
                client_ip(request),
                elapsed_ms,
                result,
                now_str(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
