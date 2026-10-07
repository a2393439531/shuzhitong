"""角色层级与最低角色校验。原创实现。"""
from fastapi import HTTPException

ROLE_LEVEL = {
    "readonly": 0,
    "operator": 1,
    "admin": 2,
    "super_admin": 3,
}


def require_role(user, min_role: str) -> None:
    user_level = ROLE_LEVEL.get(user["role"], -1)
    need_level = ROLE_LEVEL.get(min_role, 99)
    if user_level < need_level:
        raise HTTPException(status_code=403, detail=f"需要 {min_role} 及以上角色")
