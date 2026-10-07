"""认责矩阵：字段—流程—责任。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit
from ..permissions import require_role

router = APIRouter(prefix="/api/responsibilities", tags=["responsibilities"])


class RespBody(BaseModel):
    object_id: int
    field_name: str
    business_owner_dept: str = ""
    authority_source: str = ""
    source_process_id: int | None = None
    input_role: str = ""
    review_role: str = ""
    data_steward: str = ""
    tech_owner: str = ""
    org_unit: str = ""
    valid_from: str | None = None
    valid_to: str | None = None
    agent_for: str = ""


@router.get("")
def list_responsibilities(object_id: int | None = None,
                          user=Depends(get_current_user)):
    sql = """SELECT r.*, o.code AS object_code, o.name AS object_name
             FROM responsibilities r
             JOIN biz_objects o ON o.id = r.object_id WHERE 1=1"""
    params: list = []
    if object_id is not None:
        sql += " AND r.object_id = ?"
        params.append(object_id)
    sql += " ORDER BY r.id"
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()


@router.post("")
def create_responsibility(body: RespBody, request: Request,
                          user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM biz_objects WHERE id = ?", (body.object_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="对象不存在")
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO responsibilities
               (object_id, field_name, business_owner_dept, authority_source,
                source_process_id, input_role, review_role, data_steward,
                tech_owner, org_unit, valid_from, valid_to, agent_for)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (body.object_id, body.field_name, body.business_owner_dept,
             body.authority_source, body.source_process_id, body.input_role,
             body.review_role, body.data_steward, body.tech_owner, body.org_unit,
             body.valid_from, body.valid_to, body.agent_for),
        )
        conn.commit()
        r = dict(conn.execute(
            "SELECT * FROM responsibilities WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "新增认责",
              f"新增认责：对象 {body.object_id} 字段 {body.field_name}", request)
    return r


@router.put("/{resp_id}")
def update_responsibility(resp_id: int, body: RespBody, request: Request,
                          user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM responsibilities WHERE id = ?", (resp_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="认责记录不存在")
        conn.execute(
            """UPDATE responsibilities SET object_id=?, field_name=?,
               business_owner_dept=?, authority_source=?, source_process_id=?,
               input_role=?, review_role=?, data_steward=?, tech_owner=?,
               org_unit=?, valid_from=?, valid_to=?, agent_for=? WHERE id=?""",
            (body.object_id, body.field_name, body.business_owner_dept,
             body.authority_source, body.source_process_id, body.input_role,
             body.review_role, body.data_steward, body.tech_owner, body.org_unit,
             body.valid_from, body.valid_to, body.agent_for, resp_id),
        )
        conn.commit()
        r = dict(conn.execute(
            "SELECT * FROM responsibilities WHERE id = ?", (resp_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "更新认责",
              f"更新认责 {resp_id}：对象 {body.object_id} 字段 {body.field_name}", request)
    return r


@router.delete("/{resp_id}")
def delete_responsibility(resp_id: int, request: Request,
                          user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM responsibilities WHERE id = ?", (resp_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="认责记录不存在")
        conn.execute("DELETE FROM responsibilities WHERE id = ?", (resp_id,))
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "删除认责", f"删除认责记录 {resp_id}", request)
    return {"ok": True}
