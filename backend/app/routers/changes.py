"""四期：变更中心 —— 变更申请 / 自动影响分析 / 责任人确认 / 生效通知 / 回退。

状态机：草稿 ->(提交)-> 影响分析中 ->(自动分析完成)-> 待确认
       ->(全部确认)->(生效)-> 已生效 ->(回退)-> 已回退
       待确认 ->(驳回)-> 已驳回
控制规则：关联资产未完成必要确认时，阻止生效（400 返回缺失清单）。
原创实现。
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..permissions import require_role, ROLE_LEVEL
from ..utils import parse_json

router = APIRouter(prefix="/api/changes", tags=["changes"])

CHANGE_TYPES = {
    "标准版本": "standard",
    "指标口径": "indicator",
    "服务接口": "service",
    "主数据模型": "md_model",
}

TARGET_TABLE = {
    "standard": "standards",
    "indicator": "indicators",
    "service": "services",
    "md_model": "md_models",
}


class ChangeBody(BaseModel):
    change_type: str
    target_id: int
    title: str
    change_desc: str = ""
    version_to: str = ""


class ConfirmBody(BaseModel):
    comment: str = ""


def _target_or_404(conn, target_type, target_id):
    table = TARGET_TABLE[target_type]
    row = conn.execute(
        "SELECT * FROM %s WHERE id = ?" % table, (target_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="变更目标不存在")
    return dict(row)


def _resolve_confirmer(conn, owner_text):
    """把资产责任人文字解析为可确认的用户名。返回 (username, 说明)。"""
    if owner_text:
        u = conn.execute(
            "SELECT username FROM users WHERE username = ? AND is_active = 1",
            (owner_text,)).fetchone()
        if u:
            return u["username"], "资产责任人 " + owner_text
        u = conn.execute(
            "SELECT username FROM users WHERE dept = ? AND is_active = 1 "
            "AND role IN ('admin', 'operator') "
            "ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END LIMIT 1",
            (owner_text,)).fetchone()
        if u:
            return u["username"], "%s代表 %s" % (owner_text, u["username"])
    return "admin", "系统管理员（默认确认人）"


def _analyze_impact(conn, change):
    """自动影响分析。返回 impact 字典列表，每项含 confirmer / confirm_role。"""
    ctype = change["change_type"]
    tid = change["target_id"]
    impacts = []

    def _add(category, ref_type, ref_id, ref_desc, action, confirmer,
             confirm_role):
        impacts.append({
            "category": category, "ref_type": ref_type, "ref_id": ref_id,
            "ref_desc": ref_desc, "action_needed": action,
            "confirmer": confirmer, "confirm_role": confirm_role,
        })

    if ctype == "标准版本":
        target = _target_or_404(conn, "standard", tid)
        code = target.get("code", "")
        confirmer, crole = _resolve_confirmer(
            conn, target.get("owner_role") or target.get("owner_dept"))
        for fm in rows_to_dicts(conn.execute(
                "SELECT id, source_system, source_table, source_field "
                "FROM field_mappings WHERE standard_id = ?",
                (tid,))):
            _add("字段映射", "field_mapping", fm["id"],
                 "%s.%s.%s" % (fm["source_system"], fm["source_table"],
                                fm["source_field"]),
                 "确认映射字段是否受新版本影响，必要时更新映射",
                 confirmer, crole)
            for qr in rows_to_dicts(conn.execute(
                    "SELECT id, name FROM quality_rules "
                    "WHERE target_table = ? AND target_field = ?",
                    (fm["source_table"], fm["source_field"]))):
                _add("质量规则", "quality_rule", qr["id"], qr["name"],
                     "评估规则阈值/值域是否需随标准版本调整",
                     confirmer, crole)
        for cc in rows_to_dicts(conn.execute(
                "SELECT id, target_desc FROM compliance_checks "
                "WHERE standard_id = ?", (tid,))):
            _add("落标检查", "compliance_check", cc["id"],
                 cc["target_desc"] or ("检查#%s" % cc["id"]),
                 "使用新版本重新执行落标检查", confirmer, crole)
        for r in rows_to_dicts(conn.execute(
                "SELECT id, res_code, name FROM resources "
                "WHERE related_standards LIKE ?", ("%" + code + "%",))):
            _add("数据目录", "resource", r["id"],
                 "%s %s" % (r["res_code"], r["name"]),
                 "确认目录资源关联的标准版本标注", confirmer, crole)
        for s in rows_to_dicts(conn.execute(
                "SELECT id, name FROM services WHERE standard_version LIKE ?",
                ("%" + code + "%",))):
            _add("数据服务", "service", s["id"], s["name"],
                 "确认服务输出是否符合新版本，必要时升级服务版本",
                 confirmer, crole)
        _add("责任人", "user", None,
             "%s/%s" % (target.get("owner_dept", ""),
                        target.get("owner_role", "")),
             "标准版本生效前完成业务确认", confirmer, crole)

    elif ctype == "指标口径":
        target = _target_or_404(conn, "indicator", tid)
        confirmer, crole = _resolve_confirmer(
            conn, target.get("owner_role") or target.get("owner_dept"))
        for s in rows_to_dicts(conn.execute(
                "SELECT id, name FROM services WHERE svc_type = 'metric'")):
            _add("数据服务", "service", s["id"], s["name"],
                 "确认指标服务计算逻辑是否同步新口径", confirmer, crole)
        _add("责任人", "user", None,
             "%s/%s" % (target.get("owner_dept", ""),
                        target.get("owner_role", "")),
             "指标口径生效前完成业务确认", confirmer, crole)

    elif ctype == "服务接口":
        target = _target_or_404(conn, "service", tid)
        confirmer, crole = _resolve_confirmer(conn, target.get("owner"))
        for sub in rows_to_dicts(conn.execute(
                "SELECT username FROM service_subscriptions "
                "WHERE service_id = ? AND status = '已授权'", (tid,))):
            _add("调用方", "subscription", None,
                 "已授权调用方 %s" % sub["username"],
                 "接口变更生效后通知调用方联调", confirmer, crole)
        _add("责任人", "user", None, target.get("owner") or "",
             "服务接口生效前完成业务确认", confirmer, crole)

    elif ctype == "主数据模型":
        target = _target_or_404(conn, "md_model", tid)
        obj = conn.execute(
            "SELECT owner_dept FROM biz_objects WHERE id = ?",
            (target.get("object_id"),)).fetchone()
        confirmer, crole = _resolve_confirmer(
            conn, obj["owner_dept"] if obj else None)
        for fm in rows_to_dicts(conn.execute(
                "SELECT id, source_system, source_table, source_field "
                "FROM field_mappings WHERE md_model_id = ?", (tid,))):
            _add("字段映射", "field_mapping", fm["id"],
                 "%s.%s.%s" % (fm["source_system"], fm["source_table"],
                                fm["source_field"]),
                 "确认映射是否受模型变更影响", confirmer, crole)
        for d in rows_to_dicts(conn.execute(
                "SELECT DISTINCT target_system FROM md_distributions "
                "WHERE record_id IN (SELECT id FROM md_records "
                "WHERE model_id = ?)", (tid,))):
            _add("分发目标", "distribution", None, d["target_system"],
                 "模型变更后重新分发并确认", confirmer, crole)
        _add("责任人", "user", None, obj["owner_dept"] if obj else "",
             "模型变更生效前完成业务确认", confirmer, crole)

    return impacts


def _get_change_or_404(conn, change_id):
    c = conn.execute("SELECT * FROM change_requests WHERE id = ?",
                     (change_id,)).fetchone()
    if c is None:
        raise HTTPException(status_code=404, detail="变更申请不存在")
    return dict(c)


def _detail(conn, change):
    change = dict(change)
    change["snapshot"] = parse_json(change.get("snapshot"), {})
    change["impacts"] = rows_to_dicts(conn.execute(
        "SELECT * FROM change_impacts WHERE change_id = ? ORDER BY id",
        (change["id"],)))
    change["confirmations"] = rows_to_dicts(conn.execute(
        "SELECT * FROM change_confirmations WHERE change_id = ? ORDER BY id",
        (change["id"],)))
    change["notices"] = rows_to_dicts(conn.execute(
        "SELECT * FROM change_notices WHERE change_id = ? ORDER BY id",
        (change["id"],)))
    return change


@router.get("")
def list_changes(status=None, user=Depends(get_current_user)):
    sql = "SELECT * FROM change_requests WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if ROLE_LEVEL.get(user["role"], 0) < ROLE_LEVEL["admin"]:
        sql += " AND applicant = ?"
        params.append(user["username"])
    sql += " ORDER BY id DESC"
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()


@router.post("")
def create_change(body: ChangeBody, request: Request,
                  user=Depends(get_current_user)):
    require_role(user, "operator")
    if body.change_type not in CHANGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="change_type 只能是 %s" % list(CHANGE_TYPES.keys()))
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="标题必填")
    target_type = CHANGE_TYPES[body.change_type]
    conn = get_conn()
    try:
        target = _target_or_404(conn, target_type, body.target_id)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO change_requests "
            "(change_type, target_type, target_id, target_code, title, "
            "change_desc, version_from, version_to, snapshot, "
            "status, applicant, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '草稿', ?, ?)",
            (body.change_type, target_type, body.target_id,
             target.get("code", ""), body.title.strip(), body.change_desc,
             target.get("version", ""),
             body.version_to,
             json.dumps(target, ensure_ascii=False, default=str),
             user["username"], now_str()),
        )
        conn.commit()
        c = _detail(conn, _get_change_or_404(conn, cur.lastrowid))
    finally:
        conn.close()
    log_audit(user, "创建变更申请",
              "创建%s变更：%s" % (body.change_type, body.title), request)
    return c


@router.get("/{change_id}")
def get_change(change_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        c = _get_change_or_404(conn, change_id)
        if (ROLE_LEVEL.get(user["role"], 0) < ROLE_LEVEL["admin"]
                and c["applicant"] != user["username"]):
            raise HTTPException(status_code=403, detail="无权查看该变更申请")
        return _detail(conn, c)
    finally:
        conn.close()


@router.post("/{change_id}/submit")
def submit_change(change_id: int, request: Request,
                  user=Depends(get_current_user)):
    """提交 -> 自动影响分析 -> 待确认。"""
    require_role(user, "operator")
    conn = get_conn()
    try:
        c = _get_change_or_404(conn, change_id)
        if c["status"] != "草稿":
            raise HTTPException(status_code=400, detail="仅草稿可提交")
        conn.execute("UPDATE change_requests SET status = '影响分析中' "
                     "WHERE id = ?", (change_id,))
        conn.commit()
        impacts = _analyze_impact(conn, c)
        now = now_str()
        cur = conn.cursor()
        for im in impacts:
            cur.execute(
                "INSERT INTO change_impacts "
                "(change_id, category, ref_type, ref_id, ref_desc, "
                "action_needed, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (change_id, im["category"], im["ref_type"], im["ref_id"],
                 im["ref_desc"], im["action_needed"], now),
            )
        seen = {}
        for im in impacts:
            if im["confirmer"] not in seen:
                seen[im["confirmer"]] = im["confirm_role"]
        for confirmer, crole in seen.items():
            cur.execute(
                "INSERT INTO change_confirmations "
                "(change_id, confirmer, confirm_role, status, created_at) "
                "VALUES (?, ?, ?, '待确认', ?)",
                (change_id, confirmer, crole, now),
            )
        conn.execute("UPDATE change_requests SET status = '待确认' "
                     "WHERE id = ?", (change_id,))
        conn.commit()
        c = _detail(conn, _get_change_or_404(conn, change_id))
    finally:
        conn.close()
    log_audit(user, "提交变更分析",
              "变更 %s 影响分析完成：%s 项影响，%s 人待确认"
              % (change_id, len(c["impacts"]), len(c["confirmations"])),
              request)
    return c


@router.post("/{change_id}/confirm")
def confirm_change(change_id: int, body: ConfirmBody, request: Request,
                   user=Depends(get_current_user)):
    """责任人确认：本人确认自己名下的待确认项；admin 可代确认。"""
    is_admin = ROLE_LEVEL.get(user["role"], 0) >= ROLE_LEVEL["admin"]
    conn = get_conn()
    try:
        c = _get_change_or_404(conn, change_id)
        if c["status"] != "待确认":
            raise HTTPException(status_code=400, detail="变更不在待确认状态")
        pend = rows_to_dicts(conn.execute(
            "SELECT * FROM change_confirmations "
            "WHERE change_id = ? AND status = '待确认' ORDER BY id",
            (change_id,)))
        if not pend:
            raise HTTPException(status_code=400, detail="没有待确认项")
        item = next((p for p in pend if p["confirmer"] == user["username"]),
                    None)
        if item is None:
            if not is_admin:
                raise HTTPException(status_code=403,
                                    detail="没有属于你的待确认项")
            item = pend[0]
        is_proxy = item["confirmer"] != user["username"]
        conn.execute(
            "UPDATE change_confirmations "
            "SET status = '已确认', comment = ?, acted_at = ? WHERE id = ?",
            (body.comment or ("代确认" if is_proxy else ""),
             now_str(), item["id"]),
        )
        conn.commit()
        item = dict(conn.execute(
            "SELECT * FROM change_confirmations WHERE id = ?",
            (item["id"],)).fetchone())
    finally:
        conn.close()
    log_audit(user, "变更确认",
              "变更 %s 确认项 %s（%s）已确认"
              % (change_id, item["id"], item["confirmer"]), request)
    return item


@router.post("/{change_id}/effect")
def effect_change(change_id: int, request: Request,
                  user=Depends(get_current_user)):
    """生效：全部确认完成后才能生效，否则 400 返回缺失清单。"""
    require_role(user, "admin")
    conn = get_conn()
    try:
        c = _get_change_or_404(conn, change_id)
        if c["status"] != "待确认":
            raise HTTPException(status_code=400, detail="变更不在待确认状态")
        pend = rows_to_dicts(conn.execute(
            "SELECT confirmer, confirm_role FROM change_confirmations "
            "WHERE change_id = ? AND status = '待确认'", (change_id,)))
        if pend:
            missing = "、".join(
                "%s（%s）" % (p["confirmer"], p["confirm_role"] or "责任人")
                for p in pend)
            raise HTTPException(
                status_code=400,
                detail="关联资产未完成必要确认，变更不能生效；缺失确认：%s"
                       % missing,
            )
        now = now_str()
        table = TARGET_TABLE[c["target_type"]]
        if c["version_to"]:
            if c["target_type"] == "standard":
                conn.execute(
                    "INSERT INTO std_versions "
                    "(standard_id, version, change_desc, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (c["target_id"], c["version_to"], c["change_desc"], now))
                conn.execute("UPDATE standards SET version = ? WHERE id = ?",
                             (c["version_to"], c["target_id"]))
            elif c["target_type"] == "indicator":
                conn.execute(
                    "INSERT INTO indicator_versions "
                    "(indicator_id, version, snapshot, change_desc, "
                    "created_at) VALUES (?, ?, ?, ?, ?)",
                    (c["target_id"], c["version_to"],
                     json.dumps(c, ensure_ascii=False, default=str),
                     c["change_desc"], now))
                conn.execute("UPDATE indicators SET version = ? WHERE id = ?",
                             (c["version_to"], c["target_id"]))
            elif c["target_type"] == "service":
                conn.execute(
                    "INSERT INTO service_versions "
                    "(service_id, version, change_desc, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (c["target_id"], c["version_to"], c["change_desc"], now))
                conn.execute("UPDATE services SET version = ? WHERE id = ?",
                             (c["version_to"], c["target_id"]))
            elif c["target_type"] == "md_model":
                conn.execute("UPDATE md_models SET version = ? WHERE id = ?",
                             (c["version_to"], c["target_id"]))
        conn.execute(
            "UPDATE change_requests SET status = '已生效', effective_at = ? "
            "WHERE id = ?", (now, change_id))
        recipients = set()
        for cf in rows_to_dicts(conn.execute(
                "SELECT confirmer FROM change_confirmations "
                "WHERE change_id = ?", (change_id,))):
            recipients.add(("责任人", cf["confirmer"]))
        recipients.add(("申请人", c["applicant"]))
        if c["target_type"] == "service":
            for sub in rows_to_dicts(conn.execute(
                    "SELECT username FROM service_subscriptions "
                    "WHERE service_id = ? AND status = '已授权'",
                    (c["target_id"],))):
                recipients.add(("调用方", sub["username"]))
        content = "变更【%s】已于 %s 生效（%s → %s）" % (
            c["title"], now, c["version_from"] or "-", c["version_to"] or "-")
        for audience, who in sorted(recipients):
            conn.execute(
                "INSERT INTO change_notices "
                "(change_id, audience, recipient, channel, content, "
                "status, sent_at) "
                "VALUES (?, ?, ?, '站内', ?, '已发送', ?)",
                (change_id, audience, who, content, now))
        conn.commit()
        c = _detail(conn, _get_change_or_404(conn, change_id))
    finally:
        conn.close()
    log_audit(user, "变更生效",
              "变更 %s 已生效，通知 %s 条" % (change_id, len(c["notices"])),
              request)
    return c


@router.post("/{change_id}/reject")
def reject_change(change_id: int, body: ConfirmBody, request: Request,
                  user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        c = _get_change_or_404(conn, change_id)
        if c["status"] not in ("草稿", "待确认"):
            raise HTTPException(status_code=400, detail="当前状态不可驳回")
        conn.execute("UPDATE change_requests SET status = '已驳回' "
                     "WHERE id = ?", (change_id,))
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "变更驳回",
              "变更 %s 已驳回：%s" % (change_id, body.comment), request)
    return {"id": change_id, "status": "已驳回"}


@router.post("/{change_id}/rollback")
def rollback_change(change_id: int, request: Request,
                    user=Depends(get_current_user)):
    """一键回退：用变更前快照恢复目标行，状态 -> 已回退。"""
    require_role(user, "admin")
    conn = get_conn()
    try:
        c = _get_change_or_404(conn, change_id)
        if c["status"] != "已生效":
            raise HTTPException(status_code=400, detail="仅已生效的变更可回退")
        snapshot = parse_json(c.get("snapshot"), {})
        if not snapshot:
            raise HTTPException(status_code=400, detail="无变更前快照，无法回退")
        table = TARGET_TABLE[c["target_type"]]
        cols = [k for k in snapshot.keys() if k != "id"]
        cols = [k for k in cols if isinstance(snapshot[k], (str, int, float))
                or snapshot[k] is None]
        if cols:
            conn.execute(
                "UPDATE %s SET %s WHERE id = ?" % (
                    table, ", ".join("%s = ?" % k for k in cols)),
                [snapshot[k] for k in cols] + [c["target_id"]],
            )
        now = now_str()
        conn.execute("UPDATE change_requests SET status = '已回退' "
                     "WHERE id = ?", (change_id,))
        conn.execute(
            "INSERT INTO change_notices "
            "(change_id, audience, recipient, channel, content, "
            "status, sent_at) "
            "VALUES (?, '申请人', ?, '站内', ?, '已发送', ?)",
            (change_id, c["applicant"],
             "变更【%s】已回退到变更前版本" % c["title"], now))
        conn.commit()
        c = _detail(conn, _get_change_or_404(conn, change_id))
    finally:
        conn.close()
    log_audit(user, "变更回退", "变更 %s 已回退到变更前版本" % change_id,
              request)
    return c
