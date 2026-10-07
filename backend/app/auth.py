"""密码哈希（SHA-256 加盐）与 JWT（HS256）。原创实现。"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings


def _signing_key() -> str:
    # 经 settings 统一管理；禁止把密钥打进日志或返回前端
    return settings.SZT_JWT_SECRET


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return digest, salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return secrets.compare_digest(digest, password_hash)


def create_token(user_id: int, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, _signing_key(), algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, _signing_key(), algorithms=["HS256"])
