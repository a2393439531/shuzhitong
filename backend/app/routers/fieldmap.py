"""字段映射：源系统字段 ↔ 标准 / 主数据属性。原创实现。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..permissions import require_role

router = APIRouter(prefix="/api/field-mappings", tags=["field-mappings"])


class FieldMappingBody(BaseModel):
    source_system: str
    source_table: str = ""
    source_field: str
    standard_id: int | None = None
    md_model_id: int | None = None
    md_attr: str = ""
    object_id: int | None = None
    remark: str = ""


@router.get("")
def list_field_mappings(source_system: str | None = None,
                        object_id: int | None = None,
                        user=Depends(get_current_user)):
    sql = """SELECT fm.*, s.code AS standard_code, s.name AS standard_name,
                    m.code AS md_model_code, m.name AS md_model_name
             FROM field_mappings fm
             LEFT JOIN standards s ON s.id = fm.standard_id
             LEFT JOIN md_models m ON m.id = fm.md_model_id
             WHERE 1=1"""
    params: list = []
    if source_system:
        sql += " AND fm.source_system = ?"
        params.append(source_system)
    if object_id is not None:
        sql += " AND fm.object_id = ?"
        params.append(object_id)
    sql += " ORDER BY fm.id"
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()


@router.post("")
def create_field_mapping(body: FieldMappingBody, request: Request,
                         user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO field_mappings
               (source_system, source_table, source_field, standard_id,
                md_model_id, md_attr, object_id, remark, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (body.source_system, body.source_table, body.source_field,
             body.standard_id, body.md_model_id, body.md_attr,
             body.object_id, body.remark, now_str()),
        )
        conn.commit()
        fm = dict(conn.execute(
            "SELECT * FROM field_mappings WHERE id = ?",
            (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "创建字段映射",
              f"字段映射 {body.source_system}.{body.source_table}.{body.source_field}",
              request)
    return fm


@router.put("/{mapping_id}")
def update_field_mapping(mapping_id: int, body: FieldMappingBody, request: Request,
                         user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM field_mappings WHERE id = ?", (mapping_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="字段映射不存在")
        conn.execute(
            """UPDATE field_mappings
               SET source_system = ?, source_table = ?, source_field = ?,
                   standard_id = ?, md_model_id = ?, md_attr = ?,
                   object_id = ?, remark = ?
               WHERE id = ?""",
            (body.source_system, body.source_table, body.source_field,
             body.standard_id, body.md_model_id, body.md_attr,
             body.object_id, body.remark, mapping_id),
        )
        conn.commit()
        fm = dict(conn.execute(
            "SELECT * FROM field_mappings WHERE id = ?", (mapping_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "更新字段映射", f"字段映射 {mapping_id} 已更新", request)
    return fm


@router.delete("/{mapping_id}")
def delete_field_mapping(mapping_id: int, request: Request,
                         user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM field_mappings WHERE id = ?", (mapping_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="字段映射不存在")
        conn.execute("DELETE FROM field_mappings WHERE id = ?", (mapping_id,))
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "删除字段映射", f"字段映射 {mapping_id} 已删除", request)
    return {"deleted": mapping_id}
