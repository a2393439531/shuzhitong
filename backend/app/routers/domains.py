"""业务领域：只读查询。"""
from fastapi import APIRouter, Depends

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user

router = APIRouter(prefix="/api/domains", tags=["domains"])


@router.get("")
def list_domains(user=Depends(get_current_user)):
    conn = get_conn()
    try:
        rows = rows_to_dicts(conn.execute("SELECT * FROM domains ORDER BY id"))
    finally:
        conn.close()
    return rows
