"""落标检查：标准值域符合性检查与系统落标状态。原创实现。"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..permissions import require_role
from ..utils import parse_json

router = APIRouter(prefix="/api/compliance", tags=["compliance"])

DIFF_TYPES = {"值域不符", "编码不一致", "必填缺失", "格式不符", "未接入"}


class RunBody(BaseModel):
    standard_id: int
    systems: list[str] = []


def _check_ledger_against_standard(conn, standard, check_id: int) -> list:
    """演示逻辑：取标准 allowed_values，对 demo_device_ledger 相关字段做值域检查。"""
    allowed = parse_json(standard.get("allowed_values"), [])
    diffs = []
    rows = conn.execute("SELECT * FROM demo_device_ledger").fetchall()
    for r in rows:
        ref = f"台账ID:{r['id']}"
        # 值域不符：核安全分级
        sc = r["safety_class"]
        if sc is not None and str(sc).strip() != "" and sc not in allowed:
            diffs.append({
                "system_name": r["source_system"], "field_name": "safety_class",
                "diff_type": "值域不符",
                "expected": "、".join(allowed) or "标准值域",
                "actual": sc, "record_ref": ref})
        # 必填缺失：设备编码
        dc = r["device_code"]
        if dc is None or str(dc).strip() == "":
            diffs.append({
                "system_name": r["source_system"], "field_name": "device_code",
                "diff_type": "必填缺失",
                "expected": "设备编码必填", "actual": "",
                "record_ref": ref})
    return diffs


@router.post("/run")
def run_check(body: RunBody, request: Request,
              user=Depends(get_current_user)):
    require_role(user, "operator")
    now = now_str()
    conn = get_conn()
    try:
        standard = conn.execute(
            "SELECT * FROM standards WHERE id = ?", (body.standard_id,)
        ).fetchone()
        if standard is None:
            raise HTTPException(status_code=404, detail="标准不存在")
        standard = dict(standard)
        diffs = _check_ledger_against_standard(conn, standard, 0)
        # 未在 systems/台账中出现的系统记"未接入"
        present_systems = {d["system_name"] for d in diffs}
        present_systems |= {r["source_system"]
                            for r in conn.execute(
                                "SELECT DISTINCT source_system FROM demo_device_ledger"
                            ).fetchall()}
        for sys in body.systems:
            if sys not in present_systems:
                diffs.append({"system_name": sys, "field_name": "",
                              "diff_type": "未接入",
                              "expected": "已接入", "actual": "无台账记录",
                              "record_ref": ""})
        target_desc = (f"标准 {standard['code']} 在 "
                       f"{','.join(body.systems) if body.systems else '演示台账'} 的落标检查")
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO compliance_checks
               (standard_id, target_desc, status, diff_count, result_summary, created_at)
               VALUES (?, ?, '完成', ?, ?, ?)""",
            (body.standard_id, target_desc, len(diffs),
             f"检查演示台账，检出差异 {len(diffs)} 条", now),
        )
        check_id = cur.lastrowid
        for d in diffs:
            cur.execute(
                """INSERT INTO compliance_diffs
                   (check_id, system_name, field_name, diff_type,
                    expected, actual, record_ref)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (check_id, d["system_name"], d["field_name"], d["diff_type"],
                 d["expected"], d["actual"], d["record_ref"]),
            )
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "执行落标检查",
              f"标准 {standard['code']} 落标检查完成，差异 {len(diffs)} 条", request)
    return {"check_id": check_id, "diff_count": len(diffs)}


@router.get("/checks")
def list_checks(standard_id: int | None = None,
                user=Depends(get_current_user)):
    sql = """SELECT c.*, s.code AS standard_code, s.name AS standard_name
             FROM compliance_checks c
             LEFT JOIN standards s ON s.id = c.standard_id
             WHERE 1=1"""
    params: list = []
    if standard_id is not None:
        sql += " AND c.standard_id = ?"
        params.append(standard_id)
    sql += " ORDER BY c.id DESC"
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()


@router.get("/checks/{check_id}")
def get_check(check_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        c = conn.execute(
            "SELECT * FROM compliance_checks WHERE id = ?", (check_id,)
        ).fetchone()
        if c is None:
            raise HTTPException(status_code=404, detail="检查记录不存在")
        check = dict(c)
        check["diffs"] = rows_to_dicts(conn.execute(
            "SELECT * FROM compliance_diffs WHERE check_id = ? ORDER BY id",
            (check_id,)))
        return check
    finally:
        conn.close()


@router.get("/system-status")
def system_status(standard_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        adoption = rows_to_dicts(conn.execute(
            "SELECT * FROM std_adoption WHERE standard_id = ?",
            (standard_id,)))
        latest = conn.execute(
            """SELECT id FROM compliance_checks
               WHERE standard_id = ? ORDER BY id DESC LIMIT 1""",
            (standard_id,)).fetchone()
        latest_diffs: dict = {}
        if latest:
            for d in rows_to_dicts(conn.execute(
                    "SELECT system_name, COUNT(*) AS c FROM compliance_diffs "
                    "WHERE check_id = ? GROUP BY system_name",
                    (latest["id"],))):
                latest_diffs[d["system_name"]] = d["c"]
        systems: dict = {}
        for a in adoption:
            systems[a["system_name"]] = {"status": a["status"], "diff_count": 0}
        for sys_name, c in latest_diffs.items():
            systems.setdefault(sys_name, {"status": "已落标", "diff_count": 0})
            systems[sys_name]["diff_count"] = c
        out = []
        for sys_name in sorted(systems):
            info = systems[sys_name]
            status = "有差异" if info["diff_count"] > 0 else info["status"]
            out.append({"system_name": sys_name, "status": status,
                        "diff_count": info["diff_count"]})
        return out
    finally:
        conn.close()
