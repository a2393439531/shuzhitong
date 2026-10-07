"""审计日志查询（admin+）。"""
from fastapi import APIRouter, Depends

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user
from ..permissions import require_role

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(username: str | None = None, action: str | None = None,
               page: int = 1, page_size: int = 20,
               user=Depends(get_current_user)):
    require_role(user, "admin")
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    sql = "SELECT * FROM audit_log WHERE 1=1"
    params: list = []
    if username:
        sql += " AND username LIKE ?"
        params.append(f"%{username}%")
    if action:
        sql += " AND action LIKE ?"
        params.append(f"%{action}%")
    conn = get_conn()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM ({sql})", params).fetchone()["c"]
        items = rows_to_dicts(conn.execute(
            sql + " ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size]))
    finally:
        conn.close()
    return {"total": total, "page": page, "page_size": page_size, "items": items}
