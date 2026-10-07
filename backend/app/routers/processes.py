"""业务流程：CRUD + 节点管理。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit
from ..permissions import require_role

router = APIRouter(prefix="/api/processes", tags=["processes"])


class ProcessBody(BaseModel):
    code: str
    name: str
    domain_id: int | None = None
    owner_dept: str = ""
    description: str = ""


class NodeBody(BaseModel):
    seq: int
    node_name: str
    produces_data: str = ""
    uses_data: str = ""
    input_role: str = ""
    review_role: str = ""
    check_rules: str = ""


def _get_process_or_404(conn, process_id: int):
    p = conn.execute("SELECT * FROM processes WHERE id = ?", (process_id,)).fetchone()
    if p is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    return p


@router.get("")
def list_processes(user=Depends(get_current_user)):
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute("SELECT * FROM processes ORDER BY id"))
    finally:
        conn.close()


@router.post("")
def create_process(body: ProcessBody, request: Request, user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM processes WHERE code = ?", (body.code,)
        ).fetchone():
            raise HTTPException(status_code=400, detail="流程编码已存在")
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO processes (code, name, domain_id, owner_dept, description)
               VALUES (?, ?, ?, ?, ?)""",
            (body.code, body.name, body.domain_id, body.owner_dept, body.description),
        )
        conn.commit()
        p = dict(conn.execute(
            "SELECT * FROM processes WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "创建流程", f"创建业务流程 {body.code} {body.name}", request)
    return p


@router.get("/{process_id}")
def get_process(process_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        p = dict(_get_process_or_404(conn, process_id))
        p["nodes"] = rows_to_dicts(conn.execute(
            "SELECT * FROM process_nodes WHERE process_id = ? ORDER BY seq",
            (process_id,)))
    finally:
        conn.close()
    return p


@router.put("/{process_id}")
def update_process(process_id: int, body: ProcessBody, request: Request,
                   user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        _get_process_or_404(conn, process_id)
        if conn.execute(
            "SELECT 1 FROM processes WHERE code = ? AND id != ?",
            (body.code, process_id),
        ).fetchone():
            raise HTTPException(status_code=400, detail="流程编码已存在")
        conn.execute(
            """UPDATE processes SET code=?, name=?, domain_id=?, owner_dept=?, description=?
               WHERE id=?""",
            (body.code, body.name, body.domain_id, body.owner_dept,
             body.description, process_id),
        )
        conn.commit()
        p = dict(conn.execute(
            "SELECT * FROM processes WHERE id = ?", (process_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "更新流程", f"更新业务流程 {body.code} {body.name}", request)
    return p


@router.post("/{process_id}/nodes")
def add_node(process_id: int, body: NodeBody, request: Request,
             user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        _get_process_or_404(conn, process_id)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO process_nodes
               (process_id, seq, node_name, produces_data, uses_data, input_role, review_role, check_rules)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (process_id, body.seq, body.node_name, body.produces_data, body.uses_data,
             body.input_role, body.review_role, body.check_rules),
        )
        conn.commit()
        node = dict(conn.execute(
            "SELECT * FROM process_nodes WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "新增流程节点", f"流程 {process_id} 新增节点 {body.node_name}", request)
    return node
