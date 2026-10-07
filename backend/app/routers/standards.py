"""数据标准：查询/维护/提交审批/落标清单。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..permissions import require_role
from ..utils import parse_standard

router = APIRouter(prefix="/api/standards", tags=["standards"])


class StandardBody(BaseModel):
    code: str
    name: str
    std_type: str = ""
    version: str = ""
    business_def: str = ""
    allowed_values: str = ""
    authority_source: str = ""
    owner_dept: str = ""
    owner_role: str = ""
    check_rules: str = ""
    change_requirement: str = ""
    effective_date: str | None = None


def _get_standard_or_404(conn, standard_id: int):
    s = conn.execute("SELECT * FROM standards WHERE id = ?", (standard_id,)).fetchone()
    if s is None:
        raise HTTPException(status_code=404, detail="标准不存在")
    return s


@router.get("")
def list_standards(q: str | None = None, status: str | None = None,
                   user=Depends(get_current_user)):
    sql = "SELECT * FROM standards WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (code LIKE ? OR name LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY id"
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()


@router.post("")
def create_standard(body: StandardBody, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM standards WHERE code = ?", (body.code,)
        ).fetchone():
            raise HTTPException(status_code=400, detail="标准编码已存在")
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO standards
               (code, name, std_type, version, status, business_def, allowed_values,
                authority_source, owner_dept, owner_role, check_rules,
                change_requirement, effective_date, created_at)
               VALUES (?, ?, ?, ?, '草稿', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (body.code, body.name, body.std_type, body.version, body.business_def,
             body.allowed_values, body.authority_source, body.owner_dept,
             body.owner_role, body.check_rules, body.change_requirement,
             body.effective_date, now_str()),
        )
        conn.commit()
        s = dict(conn.execute(
            "SELECT * FROM standards WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "创建标准", f"创建数据标准 {body.code} {body.name}", request)
    return s


@router.get("/{standard_id}")
def get_standard(standard_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        s = dict(_get_standard_or_404(conn, standard_id))
        s["versions"] = rows_to_dicts(conn.execute(
            "SELECT * FROM std_versions WHERE standard_id = ? ORDER BY id",
            (standard_id,)))
        s = parse_standard(s)
    finally:
        conn.close()
    return s


@router.put("/{standard_id}")
def update_standard(standard_id: int, body: StandardBody, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        s = _get_standard_or_404(conn, standard_id)
        if s["status"] not in ("草稿",):
            raise HTTPException(status_code=400, detail="仅草稿状态的标准可修改")
        if conn.execute(
            "SELECT 1 FROM standards WHERE code = ? AND id != ?",
            (body.code, standard_id),
        ).fetchone():
            raise HTTPException(status_code=400, detail="标准编码已存在")
        conn.execute(
            """UPDATE standards SET code=?, name=?, std_type=?, version=?,
               business_def=?, allowed_values=?, authority_source=?, owner_dept=?,
               owner_role=?, check_rules=?, change_requirement=?, effective_date=?
               WHERE id=?""",
            (body.code, body.name, body.std_type, body.version, body.business_def,
             body.allowed_values, body.authority_source, body.owner_dept,
             body.owner_role, body.check_rules, body.change_requirement,
             body.effective_date, standard_id),
        )
        conn.commit()
        s = dict(conn.execute(
            "SELECT * FROM standards WHERE id = ?", (standard_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "更新标准", f"更新数据标准 {body.code} {body.name}", request)
    return s


@router.post("/{standard_id}/submit")
def submit_standard(standard_id: int, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        s = _get_standard_or_404(conn, standard_id)
        if s["status"] != "草稿":
            raise HTTPException(status_code=400, detail="仅草稿状态的标准可提交审批")
        now = now_str()
        cur = conn.cursor()
        cur.execute("UPDATE standards SET status = '审批中' WHERE id = ?",
                    (standard_id,))
        cur.execute(
            """INSERT INTO approvals
               (biz_type, biz_id, title, applicant, status, current_step, created_at)
               VALUES ('标准发布', ?, ?, ?, '待审批', 1, ?)""",
            (standard_id, f"标准发布审批：{s['code']} {s['name']}",
             user["username"], now),
        )
        approval_id = cur.lastrowid
        cur.execute(
            """INSERT INTO approval_steps
               (approval_id, seq, step_name, approver_role, decision)
               VALUES (?, 1, '归口审核', 'admin', '待定')""",
            (approval_id,),
        )
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "提交标准审批",
              f"提交标准 {s['code']} {s['name']} 发布审批", request)
    return {"ok": True, "approval_id": approval_id}


@router.get("/{standard_id}/adoption")
def standard_adoption(standard_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        _get_standard_or_404(conn, standard_id)
        return rows_to_dicts(conn.execute(
            "SELECT * FROM std_adoption WHERE standard_id = ? ORDER BY id",
            (standard_id,)))
    finally:
        conn.close()
