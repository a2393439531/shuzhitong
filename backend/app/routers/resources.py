"""数据资源目录：查询/维护/提交审批/下架。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..permissions import require_role
from ..utils import parse_resource

router = APIRouter(prefix="/api/resources", tags=["resources"])


class ResourceBody(BaseModel):
    res_code: str
    name: str
    domain_id: int | None = None
    object_id: int | None = None
    source_system: str = ""
    table_or_api: str = ""
    fields_desc: str = ""
    lineage: str = ""
    authority_source: str = ""
    owner_dept: str = ""
    related_standards: str = ""
    update_freq: str = ""
    quality_status: str = ""
    access_scope: str = ""
    service_mode: str = ""
    description: str = ""


def _get_resource_or_404(conn, resource_id: int):
    r = conn.execute("SELECT * FROM resources WHERE id = ?", (resource_id,)).fetchone()
    if r is None:
        raise HTTPException(status_code=404, detail="资源不存在")
    return r


_RESOURCE_FIELDS = (
    "res_code, name, domain_id, object_id, source_system, table_or_api, fields_desc,"
    " lineage, authority_source, owner_dept, related_standards, update_freq,"
    " quality_status, access_scope, service_mode, description"
)


@router.get("")
def list_resources(status: str | None = None, q: str | None = None,
                   user=Depends(get_current_user)):
    sql = "SELECT * FROM resources WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if q:
        sql += " AND (res_code LIKE ? OR name LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY id"
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()


@router.post("")
def create_resource(body: ResourceBody, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM resources WHERE res_code = ?", (body.res_code,)
        ).fetchone():
            raise HTTPException(status_code=400, detail="资源编码已存在")
        cur = conn.cursor()
        cur.execute(
            f"""INSERT INTO resources ({_RESOURCE_FIELDS}, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '已登记', ?)""",
            (body.res_code, body.name, body.domain_id, body.object_id,
             body.source_system, body.table_or_api, body.fields_desc, body.lineage,
             body.authority_source, body.owner_dept, body.related_standards,
             body.update_freq, body.quality_status, body.access_scope,
             body.service_mode, body.description, now_str()),
        )
        conn.commit()
        r = dict(conn.execute(
            "SELECT * FROM resources WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "登记数据资源",
              f"登记数据资源 {body.res_code} {body.name}", request)
    return r


@router.get("/{resource_id}")
def get_resource(resource_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        r = parse_resource(_get_resource_or_404(conn, resource_id))
        std_list = []
        if r["related_standards"]:
            q = ",".join("?" for _ in r["related_standards"])
            std_list = rows_to_dicts(conn.execute(
                f"SELECT id, code, name, version, status FROM standards WHERE id IN ({q})",
                tuple(int(i) for i in r["related_standards"])))
        r["related_standard_list"] = std_list
        return r
    finally:
        conn.close()


@router.put("/{resource_id}")
def update_resource(resource_id: int, body: ResourceBody, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        r = _get_resource_or_404(conn, resource_id)
        if r["status"] not in ("已登记",):
            raise HTTPException(status_code=400, detail="仅已登记状态的资源可修改")
        if conn.execute(
            "SELECT 1 FROM resources WHERE res_code = ? AND id != ?",
            (body.res_code, resource_id),
        ).fetchone():
            raise HTTPException(status_code=400, detail="资源编码已存在")
        conn.execute(
            f"""UPDATE resources SET {_RESOURCE_FIELDS.replace(',', '=?,')}=?
                WHERE id=?""",
            (body.res_code, body.name, body.domain_id, body.object_id,
             body.source_system, body.table_or_api, body.fields_desc, body.lineage,
             body.authority_source, body.owner_dept, body.related_standards,
             body.update_freq, body.quality_status, body.access_scope,
             body.service_mode, body.description, resource_id),
        )
        conn.commit()
        r = dict(conn.execute(
            "SELECT * FROM resources WHERE id = ?", (resource_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "更新数据资源",
              f"更新数据资源 {body.res_code} {body.name}", request)
    return r


@router.post("/{resource_id}/submit")
def submit_resource(resource_id: int, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        r = _get_resource_or_404(conn, resource_id)
        if r["status"] != "已登记":
            raise HTTPException(status_code=400, detail="仅已登记状态的资源可提交审批")
        now = now_str()
        cur = conn.cursor()
        cur.execute("UPDATE resources SET status = '技术核验中' WHERE id = ?",
                    (resource_id,))
        cur.execute(
            """INSERT INTO approvals
               (biz_type, biz_id, title, applicant, status, current_step, created_at)
               VALUES ('目录发布', ?, ?, ?, '待审批', 1, ?)""",
            (resource_id, f"目录发布审批：{r['res_code']} {r['name']}",
             user["username"], now),
        )
        approval_id = cur.lastrowid
        for seq, step_name in [(1, "技术核验"), (2, "归口审核")]:
            cur.execute(
                """INSERT INTO approval_steps
                   (approval_id, seq, step_name, approver_role, decision)
                   VALUES (?, ?, ?, 'admin', '待定')""",
                (approval_id, seq, step_name),
            )
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "提交目录发布审批",
              f"提交资源 {r['res_code']} {r['name']} 目录发布审批", request)
    return {"ok": True, "approval_id": approval_id}


@router.post("/{resource_id}/offline")
def offline_resource(resource_id: int, request: Request,
                     user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        r = _get_resource_or_404(conn, resource_id)
        if r["status"] == "已下架":
            raise HTTPException(status_code=400, detail="资源已下架")
        # 按 object_id 关联判定：已发布的服务引用了该资源对应的对象
        deps = rows_to_dicts(conn.execute(
            """SELECT * FROM services
               WHERE object_id = ? AND status = '已发布'""",
            (r["object_id"],))) if r["object_id"] else []
        if deps:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "存在已发布的服务引用该资源，无法下架",
                    "dependencies": [
                        {"id": d["id"], "name": d["name"], "version": d["version"]}
                        for d in deps
                    ],
                },
            )
        conn.execute("UPDATE resources SET status = '已下架' WHERE id = ?",
                     (resource_id,))
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "下架数据资源",
              f"下架数据资源 {r['res_code']} {r['name']}", request)
    return {"ok": True}
