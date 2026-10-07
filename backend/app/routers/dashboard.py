"""工作台统计。"""
from fastapi import APIRouter, Depends

from ..database import get_conn
from ..deps import get_current_user
from ..permissions import ROLE_LEVEL
from .approvals import _pending_todo_sql

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(user=Depends(get_current_user)):
    conn = get_conn()
    try:
        sql = f"SELECT COUNT(*) AS c FROM approvals a WHERE {_pending_todo_sql()}"
        params: list = []
        if ROLE_LEVEL.get(user["role"], 0) < ROLE_LEVEL["admin"]:
            sql += " AND a.applicant = ?"
            params.append(user["username"])
        todo_count = conn.execute(sql, params).fetchone()["c"]
        objects_count = conn.execute(
            "SELECT COUNT(*) AS c FROM biz_objects").fetchone()["c"]
        resources_published = conn.execute(
            "SELECT COUNT(*) AS c FROM resources WHERE status = '已发布'"
        ).fetchone()["c"]
        standards_published = conn.execute(
            "SELECT COUNT(*) AS c FROM standards WHERE status = '已发布'"
        ).fetchone()["c"]
        open_issues = conn.execute(
            "SELECT COUNT(*) AS c FROM quality_issues WHERE status != '已关闭'"
        ).fetchone()["c"]
    finally:
        conn.close()
    return {
        "todo_count": todo_count,
        "objects_count": objects_count,
        "resources_published": resources_published,
        "standards_published": standards_published,
        "open_issues": open_issues,
    }
