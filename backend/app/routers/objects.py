"""业务对象：CRUD + 对象卡聚合 + 属性/关系/流程关联。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..permissions import require_role
from ..utils import parse_resource, parse_standard

router = APIRouter(prefix="/api/objects", tags=["objects"])


class ObjectBody(BaseModel):
    code: str
    name: str
    definition: str = ""
    domain_id: int | None = None
    owner_dept: str = ""
    unique_id_desc: str = ""


class AttrBody(BaseModel):
    name: str
    data_type: str = ""
    is_key: int = 0
    description: str = ""


class RelationBody(BaseModel):
    to_object_id: int
    rel_type: str
    description: str = ""
    effective_from: str | None = None
    effective_to: str | None = None


class LinkProcessBody(BaseModel):
    process_id: int
    role_in_process: str = ""


def _get_object_or_404(conn, object_id: int):
    obj = conn.execute(
        "SELECT * FROM biz_objects WHERE id = ?", (object_id,)
    ).fetchone()
    if obj is None:
        raise HTTPException(status_code=404, detail="对象不存在")
    return obj


@router.get("")
def list_objects(domain_id: int | None = None, q: str | None = None,
                 user=Depends(get_current_user)):
    sql = "SELECT * FROM biz_objects WHERE 1=1"
    params: list = []
    if domain_id is not None:
        sql += " AND domain_id = ?"
        params.append(domain_id)
    if q:
        sql += " AND (code LIKE ? OR name LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY id"
    conn = get_conn()
    try:
        rows = rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()
    return rows


@router.post("")
def create_object(body: ObjectBody, request: Request, user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM biz_objects WHERE code = ?", (body.code,)
        ).fetchone():
            raise HTTPException(status_code=400, detail="对象编码已存在")
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO biz_objects
               (code, name, definition, domain_id, owner_dept, unique_id_desc, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (body.code, body.name, body.definition, body.domain_id,
             body.owner_dept, body.unique_id_desc, now_str()),
        )
        conn.commit()
        obj_id = cur.lastrowid
        obj = dict(conn.execute(
            "SELECT * FROM biz_objects WHERE id = ?", (obj_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "创建对象", f"创建业务对象 {body.code} {body.name}", request)
    return obj


@router.get("/{object_id}")
def get_object(object_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        obj = _get_object_or_404(conn, object_id)
        return dict(obj)
    finally:
        conn.close()


@router.put("/{object_id}")
def update_object(object_id: int, body: ObjectBody, request: Request,
                  user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        _get_object_or_404(conn, object_id)
        if conn.execute(
            "SELECT 1 FROM biz_objects WHERE code = ? AND id != ?",
            (body.code, object_id),
        ).fetchone():
            raise HTTPException(status_code=400, detail="对象编码已存在")
        conn.execute(
            """UPDATE biz_objects SET code=?, name=?, definition=?, domain_id=?,
               owner_dept=?, unique_id_desc=? WHERE id=?""",
            (body.code, body.name, body.definition, body.domain_id,
             body.owner_dept, body.unique_id_desc, object_id),
        )
        conn.commit()
        obj = dict(conn.execute(
            "SELECT * FROM biz_objects WHERE id = ?", (object_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "更新对象", f"更新业务对象 {body.code} {body.name}", request)
    return obj


@router.delete("/{object_id}")
def delete_object(object_id: int, request: Request, user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        obj = _get_object_or_404(conn, object_id)
        conn.execute("DELETE FROM object_attrs WHERE object_id = ?", (object_id,))
        conn.execute(
            "DELETE FROM object_relations WHERE from_object_id = ? OR to_object_id = ?",
            (object_id, object_id),
        )
        conn.execute("DELETE FROM object_processes WHERE object_id = ?", (object_id,))
        conn.execute("DELETE FROM responsibilities WHERE object_id = ?", (object_id,))
        conn.execute("DELETE FROM biz_objects WHERE id = ?", (object_id,))
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "删除对象", f"删除业务对象 {obj['code']} {obj['name']}", request)
    return {"ok": True}


@router.get("/{object_id}/card")
def object_card(object_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        obj = dict(_get_object_or_404(conn, object_id))
        attrs = rows_to_dicts(conn.execute(
            "SELECT * FROM object_attrs WHERE object_id = ? ORDER BY id", (object_id,)))

        relations = []
        for direction, sql in (
            ("out", """SELECT r.*, o.code AS peer_code, o.name AS peer_name
                        FROM object_relations r
                        JOIN biz_objects o ON o.id = r.to_object_id
                        WHERE r.from_object_id = ? ORDER BY r.id"""),
            ("in", """SELECT r.*, o.code AS peer_code, o.name AS peer_name
                       FROM object_relations r
                       JOIN biz_objects o ON o.id = r.from_object_id
                       WHERE r.to_object_id = ? ORDER BY r.id"""),
        ):
            for r in rows_to_dicts(conn.execute(sql, (object_id,))):
                r["direction"] = direction
                relations.append(r)

        procs = rows_to_dicts(conn.execute(
            """SELECT p.*, op.role_in_process FROM object_processes op
               JOIN processes p ON p.id = op.process_id
               WHERE op.object_id = ? ORDER BY p.id""", (object_id,)))
        processes = [
            {"process": {k: p[k] for k in p if k != "role_in_process"},
             "role_in_process": p["role_in_process"]}
            for p in procs
        ]

        resources = [parse_resource(r) for r in rows_to_dicts(conn.execute(
            "SELECT * FROM resources WHERE object_id = ? ORDER BY id", (object_id,)))]

        # 对象关联的标准：其资源目录 related_standards 中引用的标准
        std_ids: set[int] = set()
        for res in resources:
            for sid in res.get("related_standards") or []:
                try:
                    std_ids.add(int(sid))
                except (ValueError, TypeError):
                    pass
        standards = []
        if std_ids:
            q = ",".join("?" for _ in std_ids)
            standards = [parse_standard(s) for s in rows_to_dicts(conn.execute(
                f"SELECT * FROM standards WHERE id IN ({q}) ORDER BY id",
                tuple(std_ids)))]

        responsibilities = rows_to_dicts(conn.execute(
            "SELECT * FROM responsibilities WHERE object_id = ? ORDER BY id", (object_id,)))
        source_systems = [
            r["source_system"] for r in conn.execute(
                "SELECT DISTINCT source_system FROM resources WHERE object_id = ?",
                (object_id,)).fetchall()
        ]
        quality_issues = rows_to_dicts(conn.execute(
            "SELECT * FROM quality_issues WHERE object_id = ? ORDER BY id", (object_id,)))
        services = rows_to_dicts(conn.execute(
            "SELECT * FROM services WHERE object_id = ? ORDER BY id", (object_id,)))
        indicators = rows_to_dicts(conn.execute(
            "SELECT * FROM indicators WHERE object_id = ? ORDER BY id", (object_id,)))
    finally:
        conn.close()
    return {
        "object": obj,
        "attrs": attrs,
        "relations": relations,
        "processes": processes,
        "resources": resources,
        "standards": standards,
        "responsibilities": responsibilities,
        "source_systems": source_systems,
        "quality_issues": quality_issues,
        "services": services,
        "indicators": indicators,
    }


@router.post("/{object_id}/attrs")
def add_attr(object_id: int, body: AttrBody, request: Request,
             user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        _get_object_or_404(conn, object_id)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO object_attrs (object_id, name, data_type, is_key, description)
               VALUES (?, ?, ?, ?, ?)""",
            (object_id, body.name, body.data_type, body.is_key, body.description),
        )
        conn.commit()
        attr = dict(conn.execute(
            "SELECT * FROM object_attrs WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "新增对象属性", f"对象 {object_id} 新增属性 {body.name}", request)
    return attr


@router.post("/{object_id}/relations")
def add_relation(object_id: int, body: RelationBody, request: Request,
                 user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        _get_object_or_404(conn, object_id)
        _get_object_or_404(conn, body.to_object_id)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO object_relations
               (from_object_id, to_object_id, rel_type, description, effective_from, effective_to)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (object_id, body.to_object_id, body.rel_type, body.description,
             body.effective_from, body.effective_to),
        )
        conn.commit()
        rel = dict(conn.execute(
            "SELECT * FROM object_relations WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "新增对象关系",
              f"对象 {object_id} -> {body.to_object_id} 关系 {body.rel_type}", request)
    return rel


@router.post("/{object_id}/link-process")
def link_process(object_id: int, body: LinkProcessBody, request: Request,
                 user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        _get_object_or_404(conn, object_id)
        if conn.execute(
            "SELECT 1 FROM processes WHERE id = ?", (body.process_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="流程不存在")
        conn.execute(
            """INSERT OR REPLACE INTO object_processes (object_id, process_id, role_in_process)
               VALUES (?, ?, ?)""",
            (object_id, body.process_id, body.role_in_process),
        )
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "关联对象流程",
              f"对象 {object_id} 关联流程 {body.process_id}（{body.role_in_process}）", request)
    return {"ok": True}
