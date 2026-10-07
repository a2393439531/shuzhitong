"""数据质量问题：自动派发。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..permissions import require_role

router = APIRouter(prefix="/api/quality", tags=["quality"])

# 业务类问题派给数据管理责任人，同步失败派给技术责任人
BUSINESS_TYPES = {"业务内容错误", "缺码", "无法关联", "重复记录"}


class QualityBody(BaseModel):
    title: str
    issue_type: str = ""
    object_id: int | None = None
    resource_id: int | None = None


class QualityStatusBody(BaseModel):
    status: str


def auto_assign(conn, issue_type: str, object_id: int | None) -> str | None:
    if object_id is None:
        return None
    obj = conn.execute(
        "SELECT * FROM biz_objects WHERE id = ?", (object_id,)
    ).fetchone()
    if obj is None:
        return None
    resp = conn.execute(
        "SELECT * FROM responsibilities WHERE object_id = ? ORDER BY id LIMIT 1",
        (object_id,),
    ).fetchone()
    if issue_type in BUSINESS_TYPES:
        if resp and resp["data_steward"]:
            return resp["data_steward"]
        return obj["owner_dept"]
    if issue_type == "同步失败":
        if resp and resp["tech_owner"]:
            return resp["tech_owner"]
        return obj["owner_dept"]
    return None


@router.get("")
def list_issues(status: str | None = None, object_id: int | None = None,
                user=Depends(get_current_user)):
    sql = "SELECT * FROM quality_issues WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if object_id is not None:
        sql += " AND object_id = ?"
        params.append(object_id)
    sql += " ORDER BY id"
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()


@router.post("")
def create_issue(body: QualityBody, request: Request,
                 user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        assignee = auto_assign(conn, body.issue_type, body.object_id)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO quality_issues
               (title, issue_type, object_id, resource_id, assignee, status, created_at)
               VALUES (?, ?, ?, ?, ?, '待确认', ?)""",
            (body.title, body.issue_type, body.object_id, body.resource_id,
             assignee, now_str()),
        )
        conn.commit()
        issue = dict(conn.execute(
            "SELECT * FROM quality_issues WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "创建质量问题",
              f"创建质量问题「{body.title}」派发给 {assignee}", request)
    return issue


@router.put("/{issue_id}")
def update_issue_status(issue_id: int, body: QualityStatusBody, request: Request,
                        user=Depends(get_current_user)):
    require_role(user, "operator")
    if body.status not in ("待确认", "整改中", "已关闭"):
        raise HTTPException(status_code=400, detail="非法状态")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM quality_issues WHERE id = ?", (issue_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="质量问题不存在")
        conn.execute("UPDATE quality_issues SET status = ? WHERE id = ?",
                     (body.status, issue_id))
        conn.commit()
        issue = dict(conn.execute(
            "SELECT * FROM quality_issues WHERE id = ?", (issue_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "更新质量问题状态",
              f"质量问题 {issue_id} 状态更新为 {body.status}", request)
    return issue


# ================= 数据质量规则引擎（二期） =================
import json
from datetime import datetime, timedelta

from ..utils import parse_json

RULE_TYPES = {"完整性", "唯一性", "有效性", "一致性", "及时性", "关联完整性"}
# 演示目标表白名单（防止规则被用作任意 SQL）
ALLOWED_TABLES = {"demo_device_ledger"}
LEDGER_COLS = {"id", "device_code", "device_name", "model_code",
               "safety_class", "source_system", "updated_at"}


class RuleBody(BaseModel):
    name: str
    object_id: int | None = None
    target_table: str
    target_field: str
    rule_type: str
    params: dict = {}
    severity: str = "中"
    assignee_type: str = "业务"


class RuleUpdateBody(RuleBody):
    pass


class ScheduleBody(BaseModel):
    rule_id: int
    cron_expr: str = ""
    is_enabled: int = 1


class IssueConfirmBody(BaseModel):
    lead_assignee: str = ""


class IssueFixBody(BaseModel):
    fix_desc: str
    root_cause: str = ""


class IssueCloseBody(BaseModel):
    review_comment: str = ""


# 规则类型 → 问题类型映射（用于自动派发沿用一期 BUSINESS_TYPES）
RULE_ISSUE_TYPE = {
    "完整性": "缺码",
    "唯一性": "重复记录",
    "有效性": "业务内容错误",
    "一致性": "业务内容错误",
    "及时性": "业务内容错误",
    "关联完整性": "无法关联",
}


def _validate_rule(conn, rule) -> None:
    if rule["target_table"] not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail="目标表不在演示白名单内")
    if rule["target_field"] not in LEDGER_COLS:
        raise HTTPException(status_code=400, detail="目标字段非法")


def _open_issue_exists(conn, rule_id: int, record_ref: str) -> bool:
    row = conn.execute(
        """SELECT 1 FROM quality_issues
           WHERE rule_id = ? AND record_ref = ? AND status != '已关闭'""",
        (rule_id, record_ref),
    ).fetchone()
    return row is not None


def _detect(conn, rule) -> list:
    """执行规则检测逻辑，返回 [{record_ref, value, detail}]（不落库）。"""
    target_table = rule["target_table"]
    field = rule["target_field"]
    rtype = rule["rule_type"]
    params = parse_json(rule.get("params"), {})
    rows = conn.execute(f"SELECT * FROM {target_table}").fetchall()
    found: list = []
    if rtype == "完整性":
        for r in rows:
            v = r[field]
            if v is None or str(v).strip() == "":
                found.append({"record_ref": f"台账ID:{r['id']}",
                              "value": "", "detail": f"{field} 为空"})
    elif rtype == "唯一性":
        groups: dict = {}
        for r in rows:
            v = r[field]
            if v is None or str(v).strip() == "":
                continue
            groups.setdefault(str(v), []).append(r)
        for v, grp in groups.items():
            if len(grp) > 1:
                for r in grp:
                    found.append({"record_ref": f"台账ID:{r['id']}",
                                  "value": v,
                                  "detail": f"{field}={v} 重复出现 {len(grp)} 次"})
    elif rtype == "有效性":
        allowed = params.get("allowed_values")
        if allowed is None and params.get("standard_id"):
            std = conn.execute(
                "SELECT allowed_values FROM standards WHERE id = ?",
                (params["standard_id"],)).fetchone()
            if std:
                allowed = parse_json(std["allowed_values"], [])
        allowed = allowed or []
        for r in rows:
            v = r[field]
            if v not in allowed:
                found.append({"record_ref": f"台账ID:{r['id']}",
                              "value": v, "detail": f"{field}={v} 不在允许值域内"})
    elif rtype == "一致性":
        field2 = params.get("field2")
        op = params.get("operator", "=")
        if not field2 or field2 not in LEDGER_COLS:
            return []
        ops = {
            "=": lambda a, b: str(a) == str(b),
            "!=": lambda a, b: str(a) != str(b),
            ">": lambda a, b: str(a) > str(b),
            "<": lambda a, b: str(a) < str(b),
            ">=": lambda a, b: str(a) >= str(b),
            "<=": lambda a, b: str(a) <= str(b),
        }
        cmp_fn = ops.get(op, ops["="])
        for r in rows:
            if not cmp_fn(r[field], r[field2]):
                found.append({"record_ref": f"台账ID:{r['id']}",
                              "value": f"{r[field]} vs {r[field2]}",
                              "detail": f"{field} 与 {field2} 不满足 {op}"})
    elif rtype == "及时性":
        hours = params.get("hours", 24)
        try:
            threshold = datetime.now() - timedelta(hours=int(hours))
        except (TypeError, ValueError):
            return []
        for r in rows:
            raw = r[field]
            try:
                ts = datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                continue
            if ts < threshold:
                found.append({"record_ref": f"台账ID:{r['id']}",
                              "value": raw,
                              "detail": f"{field} 早于 {hours} 小时阈值"})
    elif rtype == "关联完整性":
        ref_table = params.get("ref_table")
        ref_field = params.get("ref_field")
        if ref_table not in ALLOWED_TABLES or ref_field not in LEDGER_COLS:
            return []
        refs = {str(r[ref_field]) for r in
                conn.execute(f"SELECT * FROM {ref_table}").fetchall()}
        for r in rows:
            v = r[field]
            if str(v) not in refs:
                found.append({"record_ref": f"台账ID:{r['id']}",
                              "value": v,
                              "detail": f"{field}={v} 在 {ref_table} 中无关联"})
    return found


def _dispatch_assignee(conn, rule) -> tuple:
    """按认责矩阵自动派发：object_id 匹配、field_name 优先匹配 target_field。
    业务→data_steward，技术→tech_owner。返回 (assignee, assignee_type)。"""
    rows = rows_to_dicts(conn.execute(
        "SELECT * FROM responsibilities WHERE object_id = ? ORDER BY id",
        (rule["object_id"],)))
    resp = None
    for r in rows:
        if r["field_name"] == rule["target_field"]:
            resp = r
            break
    if resp is None and rows:
        resp = rows[0]
    assignee_type = rule.get("assignee_type") or "业务"
    if resp:
        if assignee_type == "技术":
            return resp["tech_owner"], assignee_type
        return resp["data_steward"], assignee_type
    return None, assignee_type


def _create_issues(conn, rule, detected, triggered_by: str) -> list:
    created = []
    issue_type = RULE_ISSUE_TYPE.get(rule["rule_type"], "业务内容错误")
    for d in detected:
        if _open_issue_exists(conn, rule["id"], d["record_ref"]):
            continue
        assignee, assignee_type = _dispatch_assignee(conn, rule)
        title = f"[{rule['name']}] {d['record_ref']} {d['detail']}"
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO quality_issues
               (title, issue_type, object_id, resource_id, assignee, status,
                created_at, assignee_type, rule_id, record_ref)
               VALUES (?, ?, ?, ?, ?, '待确认', ?, ?, ?, ?)""",
            (title, issue_type, rule["object_id"], None, assignee,
             now_str(), assignee_type, rule["id"], d["record_ref"]),
        )
        created.append({"id": cur.lastrowid, "title": title,
                        "record_ref": d["record_ref"], "assignee": assignee})
    return created


def _run_rule(conn, rule_id: int, triggered_by: str,
              create_issues: bool = True) -> dict:
    rule = conn.execute(
        "SELECT * FROM quality_rules WHERE id = ?", (rule_id,)
    ).fetchone()
    if rule is None:
        raise HTTPException(status_code=404, detail="质量规则不存在")
    _validate_rule(conn, dict(rule))
    now = now_str()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO quality_runs
           (rule_id, status, issue_count, triggered_by, message, started_at)
           VALUES (?, '运行中', 0, ?, '', ?)""",
        (rule_id, triggered_by, now),
    )
    run_id = cur.lastrowid
    try:
        detected = _detect(conn, dict(rule))
        created = _create_issues(conn, dict(rule), detected,
                                 triggered_by) if create_issues else []
        conn.execute(
            """UPDATE quality_runs
               SET status = '完成', issue_count = ?,
                   message = ?, finished_at = ?
               WHERE id = ?""",
            (len(created), f"检出 {len(detected)} 条，其中新建 {len(created)} 条",
             now_str(), run_id),
        )
        conn.commit()
    except Exception as e:
        conn.execute(
            "UPDATE quality_runs SET status = '失败', message = ? WHERE id = ?",
            (str(e), run_id),
        )
        conn.commit()
        raise
    return {"run_id": run_id, "issue_count": len(created), "issues": created}


# ---------- 规则 CRUD ----------

@router.get("/rules")
def list_rules(is_enabled: int | None = None, user=Depends(get_current_user)):
    sql = ("SELECT r.*, o.name AS object_name FROM quality_rules r "
           "LEFT JOIN biz_objects o ON o.id = r.object_id WHERE 1=1")
    params: list = []
    if is_enabled is not None:
        sql += " AND r.is_enabled = ?"
        params.append(is_enabled)
    sql += " ORDER BY r.id"
    conn = get_conn()
    try:
        out = []
        for r in rows_to_dicts(conn.execute(sql, params)):
            r["params"] = parse_json(r.get("params"), {})
            out.append(r)
        return out
    finally:
        conn.close()


@router.post("/rules")
def create_rule(body: RuleBody, request: Request,
                user=Depends(get_current_user)):
    require_role(user, "admin")
    if body.rule_type not in RULE_TYPES:
        raise HTTPException(status_code=400, detail="非法规则类型")
    if body.target_table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail="目标表不在演示白名单内")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO quality_rules
               (name, object_id, target_table, target_field, rule_type, params,
                severity, is_enabled, assignee_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (body.name, body.object_id, body.target_table, body.target_field,
             body.rule_type, json.dumps(body.params, ensure_ascii=False),
             body.severity, body.assignee_type, now_str()),
        )
        conn.commit()
        rule = dict(conn.execute(
            "SELECT * FROM quality_rules WHERE id = ?",
            (cur.lastrowid,)).fetchone())
        rule["params"] = parse_json(rule.get("params"), {})
    finally:
        conn.close()
    log_audit(user, "创建质量规则", f"创建质量规则「{body.name}」", request)
    return rule


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdateBody, request: Request,
                user=Depends(get_current_user)):
    require_role(user, "admin")
    if body.rule_type not in RULE_TYPES:
        raise HTTPException(status_code=400, detail="非法规则类型")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM quality_rules WHERE id = ?", (rule_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="质量规则不存在")
        conn.execute(
            """UPDATE quality_rules
               SET name = ?, object_id = ?, target_table = ?, target_field = ?,
                   rule_type = ?, params = ?, severity = ?, assignee_type = ?
               WHERE id = ?""",
            (body.name, body.object_id, body.target_table, body.target_field,
             body.rule_type, json.dumps(body.params, ensure_ascii=False),
             body.severity, body.assignee_type, rule_id),
        )
        conn.commit()
        rule = dict(conn.execute(
            "SELECT * FROM quality_rules WHERE id = ?", (rule_id,)).fetchone())
        rule["params"] = parse_json(rule.get("params"), {})
    finally:
        conn.close()
    log_audit(user, "更新质量规则", f"质量规则 {rule_id} 已更新", request)
    return rule


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, request: Request,
                user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM quality_rules WHERE id = ?", (rule_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="质量规则不存在")
        conn.execute("DELETE FROM quality_rules WHERE id = ?", (rule_id,))
        conn.execute("DELETE FROM rule_schedules WHERE rule_id = ?", (rule_id,))
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "删除质量规则", f"质量规则 {rule_id} 已删除", request)
    return {"deleted": rule_id}


@router.patch("/rules/{rule_id}/toggle")
def toggle_rule(rule_id: int, request: Request,
                user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT * FROM quality_rules WHERE id = ?", (rule_id,)
        ).fetchone()
        if r is None:
            raise HTTPException(status_code=404, detail="质量规则不存在")
        new_val = 0 if r["is_enabled"] else 1
        conn.execute("UPDATE quality_rules SET is_enabled = ? WHERE id = ?",
                     (new_val, rule_id))
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "启停质量规则",
              f"质量规则 {rule_id} {'启用' if new_val else '停用'}", request)
    return {"id": rule_id, "is_enabled": new_val}


# ---------- 规则执行 ----------

@router.post("/rules/{rule_id}/run")
def run_rule(rule_id: int, request: Request,
             user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        result = _run_rule(conn, rule_id, user["username"])
    finally:
        conn.close()
    log_audit(user, "执行质量规则",
              f"执行质量规则 {rule_id}，新建问题 {result['issue_count']} 个", request)
    return result


@router.post("/rules/run-all")
def run_all_rules(request: Request, user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        rules = conn.execute(
            "SELECT * FROM quality_rules WHERE is_enabled = 1 ORDER BY id"
        ).fetchall()
        results = []
        for r in rules:
            try:
                res = _run_rule(conn, r["id"], user["username"])
                results.append({"rule_id": r["id"], "name": r["name"],
                                "ok": True, **res})
            except HTTPException as e:
                results.append({"rule_id": r["id"], "name": r["name"],
                                "ok": False, "error": e.detail})
    finally:
        conn.close()
    log_audit(user, "批量执行质量规则",
              f"批量执行 {len(results)} 条启用规则", request)
    return {"runs": results}


@router.get("/runs")
def list_runs(rule_id: int | None = None, user=Depends(get_current_user)):
    sql = """SELECT r.*, q.name AS rule_name
             FROM quality_runs r LEFT JOIN quality_rules q ON q.id = r.rule_id
             WHERE 1=1"""
    params: list = []
    if rule_id is not None:
        sql += " AND r.rule_id = ?"
        params.append(rule_id)
    sql += " ORDER BY r.id DESC"
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()


@router.get("/runs/{run_id}")
def get_run(run_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        r = conn.execute(
            """SELECT r.*, q.name AS rule_name
               FROM quality_runs r LEFT JOIN quality_rules q ON q.id = r.rule_id
               WHERE r.id = ?""", (run_id,)
        ).fetchone()
        if r is None:
            raise HTTPException(status_code=404, detail="执行记录不存在")
        return dict(r)
    finally:
        conn.close()


# ---------- 定时调度 ----------

@router.post("/schedule")
def upsert_schedule(body: ScheduleBody, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM quality_rules WHERE id = ?", (body.rule_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="质量规则不存在")
        exists = conn.execute(
            "SELECT 1 FROM rule_schedules WHERE rule_id = ?", (body.rule_id,)
        ).fetchone()
        if exists:
            conn.execute(
                """UPDATE rule_schedules SET cron_expr = ?, is_enabled = ?
                   WHERE rule_id = ?""",
                (body.cron_expr, body.is_enabled, body.rule_id),
            )
        else:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO rule_schedules
                   (rule_id, cron_expr, is_enabled, last_run)
                   VALUES (?, ?, ?, NULL)""",
                (body.rule_id, body.cron_expr, body.is_enabled),
            )
        conn.commit()
        sch = dict(conn.execute(
            "SELECT * FROM rule_schedules WHERE rule_id = ?",
            (body.rule_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "配置规则调度", f"规则 {body.rule_id} 调度配置已保存", request)
    return sch


@router.get("/schedule")
def list_schedules(user=Depends(get_current_user)):
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(
            """SELECT s.*, q.name AS rule_name
               FROM rule_schedules s LEFT JOIN quality_rules q ON q.id = s.rule_id
               ORDER BY s.id"""))
    finally:
        conn.close()


@router.post("/schedule/trigger-due")
def trigger_due(request: Request, user=Depends(get_current_user)):
    require_role(user, "operator")
    cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    now = now_str()
    conn = get_conn()
    try:
        due = conn.execute(
            """SELECT s.rule_id FROM rule_schedules s
               JOIN quality_rules q ON q.id = s.rule_id
               WHERE s.is_enabled = 1 AND q.is_enabled = 1
                 AND (s.last_run IS NULL OR s.last_run < ?)""",
            (cutoff,),
        ).fetchall()
        results = []
        for d in due:
            res = _run_rule(conn, d["rule_id"], user["username"] + "(定时)")
            conn.execute(
                "UPDATE rule_schedules SET last_run = ? WHERE rule_id = ?",
                (now, d["rule_id"]),
            )
            conn.commit()
            results.append({"rule_id": d["rule_id"], **res})
    finally:
        conn.close()
    log_audit(user, "触发到期调度", f"触发 {len(results)} 条到期规则", request)
    return {"triggered": results}


# ---------- 整改闭环：待确认→已确认→整改中→待复核→已关闭 ----------

def _get_issue(conn, issue_id: int) -> dict:
    issue = conn.execute(
        "SELECT * FROM quality_issues WHERE id = ?", (issue_id,)
    ).fetchone()
    if issue is None:
        raise HTTPException(status_code=404, detail="质量问题不存在")
    return dict(issue)


@router.post("/issues/{issue_id}/confirm")
def confirm_issue(issue_id: int, body: IssueConfirmBody, request: Request,
                  user=Depends(get_current_user)):
    require_role(user, "operator")
    now = now_str()
    conn = get_conn()
    try:
        issue = _get_issue(conn, issue_id)
        if issue["status"] != "待确认":
            raise HTTPException(status_code=400, detail="仅待确认的问题可确认")
        assignee = body.lead_assignee or issue["assignee"]
        conn.execute(
            """UPDATE quality_issues
               SET status = '已确认', lead_assignee = ?, assignee = ?,
                   confirmed_at = ?
               WHERE id = ?""",
            (body.lead_assignee or None, assignee, now, issue_id),
        )
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "确认质量问题", f"质量问题 {issue_id} 已确认", request)
    return _issue_after(issue_id)


def _issue_after(issue_id: int) -> dict:
    conn = get_conn()
    try:
        return dict(conn.execute(
            "SELECT * FROM quality_issues WHERE id = ?",
            (issue_id,)).fetchone())
    finally:
        conn.close()


@router.post("/issues/{issue_id}/fix")
def fix_issue(issue_id: int, body: IssueFixBody, request: Request,
              user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        issue = _get_issue(conn, issue_id)
        if issue["status"] != "已确认":
            raise HTTPException(status_code=400, detail="仅已确认的问题可进入整改")
        conn.execute(
            """UPDATE quality_issues
               SET status = '整改中', fix_desc = ?, root_cause = ?
               WHERE id = ?""",
            (body.fix_desc, body.root_cause or None, issue_id),
        )
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "质量问题整改", f"质量问题 {issue_id} 进入整改", request)
    return _issue_after(issue_id)


@router.post("/issues/{issue_id}/recheck")
def recheck_issue(issue_id: int, request: Request,
                  user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        issue = _get_issue(conn, issue_id)
        if issue["status"] != "整改中":
            raise HTTPException(status_code=400, detail="仅整改中的问题可复核")
        still_bad = False
        if issue["rule_id"]:
            rule = conn.execute(
                "SELECT * FROM quality_rules WHERE id = ?",
                (issue["rule_id"],)).fetchone()
            if rule is not None:
                detected = _detect(conn, dict(rule))
                still_bad = any(d["record_ref"] == issue["record_ref"]
                                for d in detected)
        if still_bad:
            result = "仍有问题，保持整改中"
        else:
            conn.execute(
                "UPDATE quality_issues SET status = '待复核' WHERE id = ?",
                (issue_id,),
            )
            conn.commit()
            result = "复核通过，进入待复核"
    finally:
        conn.close()
    log_audit(user, "质量问题复核", f"质量问题 {issue_id} 复核：{result}", request)
    return {"issue": _issue_after(issue_id), "recheck_result": result}


@router.post("/issues/{issue_id}/close")
def close_issue(issue_id: int, body: IssueCloseBody, request: Request,
                user=Depends(get_current_user)):
    require_role(user, "admin")
    now = now_str()
    conn = get_conn()
    try:
        issue = _get_issue(conn, issue_id)
        if issue["status"] != "待复核":
            raise HTTPException(status_code=400, detail="仅待复核的问题可关闭")
        fix_desc = (issue["fix_desc"] or "")
        if body.review_comment:
            fix_desc = (fix_desc + "\n" if fix_desc else "") + \
                f"复核意见：{body.review_comment}"
        conn.execute(
            """UPDATE quality_issues
               SET status = '已关闭', fix_desc = ?, closed_at = ?
               WHERE id = ?""",
            (fix_desc, now, issue_id),
        )
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "关闭质量问题", f"质量问题 {issue_id} 已关闭", request)
    return _issue_after(issue_id)
