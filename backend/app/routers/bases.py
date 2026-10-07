"""四期：多基地配置 —— 基地档案与共性/差异两层治理。原创实现。"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import qa_engine as qa
from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..permissions import require_role
from ..utils import parse_json

router = APIRouter(prefix="/api/bases", tags=["bases"])


class BaseBody(BaseModel):
    code: str
    name: str
    stack_type: str = ""
    status: str = "运行中"
    description: str = ""


class DiffBody(BaseModel):
    base_code: str
    diff_type: str = ""          # 允许值/口径/必填/格式（标准）；口径（指标）
    diff_desc: dict | None = None  # 如 {"allowed_values": [...], "note": "..."}
    reason: str = ""
    effective_from: str | None = None
    effective_to: str | None = None


def _diff_row_to_dict(r: dict) -> dict:
    r = dict(r)
    r["diff_desc"] = parse_json(r.get("diff_desc"), {})
    return r


# ================= 基地档案 =================

@router.get("")
def list_bases(user=Depends(get_current_user)):
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute("SELECT * FROM bases ORDER BY id"))
    finally:
        conn.close()


@router.post("")
def create_base(body: BaseBody, request: Request,
                user=Depends(get_current_user)):
    require_role(user, "operator")
    if not body.code.strip() or not body.name.strip():
        raise HTTPException(status_code=400, detail="基地编码与名称必填")
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM bases WHERE code = ?",
                        (body.code.strip(),)).fetchone():
            raise HTTPException(status_code=400, detail="基地编码已存在")
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO bases (code, name, stack_type, status, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (body.code.strip(), body.name.strip(), body.stack_type,
             body.status, body.description, now_str()),
        )
        conn.commit()
        b = dict(conn.execute("SELECT * FROM bases WHERE id = ?",
                              (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "创建基地", f"创建基地档案 {body.code} {body.name}", request)
    return b


@router.get("/{code}")
def get_base(code: str, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        b = conn.execute("SELECT * FROM bases WHERE code = ?",
                         (code,)).fetchone()
        if b is None:
            raise HTTPException(status_code=404, detail="基地不存在")
        b = dict(b)
        b["std_diffs"] = [_diff_row_to_dict(r) for r in rows_to_dicts(
            conn.execute("""SELECT d.*, s.code AS std_code, s.name AS std_name
                            FROM std_base_diff d
                            LEFT JOIN standards s ON s.id = d.standard_id
                            WHERE d.base_code = ? ORDER BY d.id""", (code,)))]
        b["indicator_diffs"] = [_diff_row_to_dict(r) for r in rows_to_dicts(
            conn.execute("""SELECT d.*, i.code AS ind_code, i.name AS ind_name
                            FROM indicator_base_diff d
                            LEFT JOIN indicators i ON i.id = d.indicator_id
                            WHERE d.base_code = ? ORDER BY d.id""", (code,)))]
    finally:
        conn.close()
    return b


# ================= 标准基地差异 =================

@router.get("/diffs/standards")
def list_std_diffs(base_code: str | None = None,
                   standard_id: int | None = None,
                   user=Depends(get_current_user)):
    sql = """SELECT d.*, s.code AS std_code, s.name AS std_name, b.name AS base_name
             FROM std_base_diff d
             LEFT JOIN standards s ON s.id = d.standard_id
             LEFT JOIN bases b ON b.code = d.base_code WHERE 1=1"""
    params: list = []
    if base_code:
        sql += " AND d.base_code = ?"
        params.append(base_code)
    if standard_id:
        sql += " AND d.standard_id = ?"
        params.append(standard_id)
    sql += " ORDER BY d.id"
    conn = get_conn()
    try:
        return [_diff_row_to_dict(r)
                for r in rows_to_dicts(conn.execute(sql, params))]
    finally:
        conn.close()


@router.post("/diffs/standards")
def create_std_diff(standard_id: int, body: DiffBody, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM standards WHERE id = ?",
                        (standard_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="标准不存在")
        if conn.execute("SELECT 1 FROM bases WHERE code = ?",
                        (body.base_code,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="基地不存在")
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO std_base_diff
               (standard_id, base_code, diff_type, diff_desc, reason,
                effective_from, effective_to, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, '草稿', ?)""",
            (standard_id, body.base_code, body.diff_type or "允许值",
             json.dumps(body.diff_desc or {}, ensure_ascii=False),
             body.reason, body.effective_from, body.effective_to, now_str()),
        )
        conn.commit()
        d = _diff_row_to_dict(conn.execute(
            "SELECT * FROM std_base_diff WHERE id = ?",
            (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "登记标准基地差异",
              f"标准 {standard_id} 在基地 {body.base_code} 登记差异", request)
    return d


@router.post("/diffs/standards/{diff_id}/publish")
def publish_std_diff(diff_id: int, request: Request,
                     user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        d = conn.execute("SELECT * FROM std_base_diff WHERE id = ?",
                         (diff_id,)).fetchone()
        if d is None:
            raise HTTPException(status_code=404, detail="差异记录不存在")
        conn.execute("UPDATE std_base_diff SET status = '已发布' WHERE id = ?",
                     (diff_id,))
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "发布基地差异", f"标准基地差异 {diff_id} 已发布", request)
    return {"id": diff_id, "status": "已发布"}


# ================= 指标基地差异 =================

@router.get("/diffs/indicators")
def list_ind_diffs(base_code: str | None = None,
                   indicator_id: int | None = None,
                   user=Depends(get_current_user)):
    sql = """SELECT d.*, i.code AS ind_code, i.name AS ind_name, b.name AS base_name
             FROM indicator_base_diff d
             LEFT JOIN indicators i ON i.id = d.indicator_id
             LEFT JOIN bases b ON b.code = d.base_code WHERE 1=1"""
    params: list = []
    if base_code:
        sql += " AND d.base_code = ?"
        params.append(base_code)
    if indicator_id:
        sql += " AND d.indicator_id = ?"
        params.append(indicator_id)
    sql += " ORDER BY d.id"
    conn = get_conn()
    try:
        return [_diff_row_to_dict(r)
                for r in rows_to_dicts(conn.execute(sql, params))]
    finally:
        conn.close()


@router.post("/diffs/indicators")
def create_ind_diff(indicator_id: int, body: DiffBody, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM indicators WHERE id = ?",
                        (indicator_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="指标不存在")
        if conn.execute("SELECT 1 FROM bases WHERE code = ?",
                        (body.base_code,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="基地不存在")
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO indicator_base_diff
               (indicator_id, base_code, diff_type, diff_desc, reason,
                effective_from, effective_to, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, '草稿', ?)""",
            (indicator_id, body.base_code, body.diff_type or "口径",
             json.dumps(body.diff_desc or {}, ensure_ascii=False),
             body.reason, body.effective_from, body.effective_to, now_str()),
        )
        conn.commit()
        d = _diff_row_to_dict(conn.execute(
            "SELECT * FROM indicator_base_diff WHERE id = ?",
            (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "登记指标基地差异",
              f"指标 {indicator_id} 在基地 {body.base_code} 登记差异", request)
    return d


@router.post("/diffs/indicators/{diff_id}/publish")
def publish_ind_diff(diff_id: int, request: Request,
                     user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        d = conn.execute("SELECT * FROM indicator_base_diff WHERE id = ?",
                         (diff_id,)).fetchone()
        if d is None:
            raise HTTPException(status_code=404, detail="差异记录不存在")
        conn.execute(
            "UPDATE indicator_base_diff SET status = '已发布' WHERE id = ?",
            (diff_id,))
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "发布基地差异", f"指标基地差异 {diff_id} 已发布", request)
    return {"id": diff_id, "status": "已发布"}


# ================= 有效口径查询（供落标检查/问数/前端预览） =================

@router.get("/effective/standard/{standard_id}")
def effective_standard(standard_id: int, base_code: str | None = None,
                       user=Depends(get_current_user)):
    """合并基地差异后的标准有效视图。"""
    conn = get_conn()
    try:
        merged = qa.get_effective_allowed_values(conn, standard_id, base_code)
        s = conn.execute("SELECT code, name, version, status FROM standards "
                         "WHERE id = ?", (standard_id,)).fetchone()
        if s is None:
            raise HTTPException(status_code=404, detail="标准不存在")
        out = dict(s)
        out["effective_allowed_values"] = merged["allowed_values"]
        out["base_code"] = base_code
        out["base_note"] = merged["base_note"]
    finally:
        conn.close()
    return out


@router.get("/effective/indicator/{code}")
def effective_indicator(code: str, base_code: str | None = None,
                        user=Depends(get_current_user)):
    """合并基地差异后的指标有效口径（含声明文本）。"""
    conn = get_conn()
    try:
        merged = qa.get_effective_caliber(conn, code, base_code)
    finally:
        conn.close()
    return {"code": code, "base_code": base_code, **merged}
