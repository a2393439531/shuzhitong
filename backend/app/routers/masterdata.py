"""主数据管理：模型 / 申请审核 / 记录 / 分发 / 编码映射 / 三码关系。原创实现。"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..permissions import require_role
from ..utils import parse_json

router = APIRouter(prefix="/api/masterdata", tags=["masterdata"])

APP_TYPES = {"新增", "变更", "停用", "合并"}


class ModelBody(BaseModel):
    code: str
    name: str
    object_id: int | None = None
    id_rule: str = ""
    key_fields: str = ""
    status: str = "草稿"
    version: str = "v1.0"


class ApplyBody(BaseModel):
    app_type: str
    payload: dict = {}
    master_code: str | None = None
    merge_to_code: str | None = None
    reason: str = ""


class ReviewBody(BaseModel):
    decision: str  # 通过 | 驳回
    comment: str = ""


class RecordUpdateBody(BaseModel):
    attrs: dict = {}


class DistributeBody(BaseModel):
    target_systems: list[str] = []


class CodeMapBody(BaseModel):
    model_id: int
    master_code: str
    source_system: str
    source_code: str


class DeviceLinkBody(BaseModel):
    logic_code: str
    model_code: str
    physical_code: str
    effective_from: str
    effective_to: str | None = None


def _get_model(conn, model_id: int):
    m = conn.execute("SELECT * FROM md_models WHERE id = ?", (model_id,)).fetchone()
    if m is None:
        raise HTTPException(status_code=404, detail="主数据模型不存在")
    return m


def _parse_record(r: dict) -> dict:
    r = dict(r)
    r["attrs"] = parse_json(r.get("attrs"), {})
    return r


def _parse_app(a: dict) -> dict:
    a = dict(a)
    a["payload"] = parse_json(a.get("payload"), {})
    return a


def _gen_master_code(conn, model) -> str:
    """按模型 id_rule 前缀 + 6 位序号生成统一编码，如 MAT-000001。"""
    prefix = model["id_rule"] or ""
    seq = conn.execute(
        "SELECT COUNT(*) AS c FROM md_records WHERE model_id = ?",
        (model["id"],),
    ).fetchone()["c"] + 1
    while True:
        code = f"{prefix}{seq:06d}"
        exists = conn.execute(
            "SELECT 1 FROM md_records WHERE master_code = ?", (code,)
        ).fetchone()
        if exists is None:
            return code
        seq += 1


def _find_duplicates(conn, model, payload: dict) -> list:
    """按模型 key_fields（逗号分隔）对 payload 做重复识别。"""
    keys = [k.strip() for k in (model["key_fields"] or "").split(",") if k.strip()]
    if not keys:
        return []
    dups = []
    rows = conn.execute(
        "SELECT * FROM md_records WHERE model_id = ?", (model["id"],)
    ).fetchall()
    for r in rows:
        attrs = parse_json(r["attrs"], {})
        hit = True
        for k in keys:
            pv = payload.get(k)
            if pv in (None, "") or attrs.get(k) != pv:
                hit = False
                break
        if hit:
            dups.append({"master_code": r["master_code"], "attrs": attrs})
    return dups


def _write_history(conn, record_id: int, version: int, attrs: dict,
                   change_desc: str, changed_by: str) -> None:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO md_history
           (record_id, version, attrs, change_desc, changed_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (record_id, version, json.dumps(attrs, ensure_ascii=False),
         change_desc, changed_by, now_str()),
    )


# ---------- 主数据模型 ----------

@router.get("/models")
def list_models(q: str | None = None, user=Depends(get_current_user)):
    sql = """SELECT m.*, o.code AS object_code, o.name AS object_name
             FROM md_models m LEFT JOIN biz_objects o ON o.id = m.object_id
             WHERE 1=1"""
    params: list = []
    if q:
        sql += " AND (m.code LIKE ? OR m.name LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY m.id"
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()


@router.post("/models")
def create_model(body: ModelBody, request: Request,
                 user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM md_models WHERE code = ?",
                        (body.code,)).fetchone() is not None:
            raise HTTPException(status_code=400, detail="模型编码已存在")
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO md_models
               (object_id, code, name, id_rule, key_fields, status, version, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (body.object_id, body.code, body.name, body.id_rule,
             body.key_fields, body.status, body.version, now_str()),
        )
        conn.commit()
        model = dict(conn.execute(
            "SELECT * FROM md_models WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "创建主数据模型", f"创建主数据模型「{body.code}」", request)
    return model


@router.get("/models/{model_id}")
def get_model(model_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        m = dict(_get_model(conn, model_id))
        m["record_count"] = conn.execute(
            "SELECT COUNT(*) AS c FROM md_records WHERE model_id = ?",
            (model_id,),
        ).fetchone()["c"]
        return m
    finally:
        conn.close()


# ---------- 申请与审核 ----------

@router.post("/models/{model_id}/apply")
def apply(model_id: int, body: ApplyBody, request: Request,
          user=Depends(get_current_user)):
    require_role(user, "operator")
    if body.app_type not in APP_TYPES:
        raise HTTPException(status_code=400, detail="非法申请类型")
    if body.app_type != "新增" and not body.master_code:
        raise HTTPException(status_code=400, detail="变更/停用/合并需指定 master_code")
    if body.app_type == "合并" and not body.merge_to_code:
        raise HTTPException(status_code=400, detail="合并需指定 merge_to_code")
    conn = get_conn()
    try:
        model = _get_model(conn, model_id)
        if body.app_type != "新增":
            rec = conn.execute(
                "SELECT 1 FROM md_records WHERE model_id = ? AND master_code = ?",
                (model_id, body.master_code),
            ).fetchone()
            if rec is None:
                raise HTTPException(status_code=404, detail="主数据记录不存在")
        duplicates = _find_duplicates(conn, model, body.payload) \
            if body.app_type == "新增" else []
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO md_applications
               (model_id, app_type, payload, master_code, merge_to_code, reason,
                status, applicant, created_at)
               VALUES (?, ?, ?, ?, ?, ?, '待审核', ?, ?)""",
            (model_id, body.app_type,
             json.dumps(body.payload, ensure_ascii=False),
             body.master_code, body.merge_to_code, body.reason,
             user["username"], now_str()),
        )
        conn.commit()
        app_id = cur.lastrowid
    finally:
        conn.close()
    log_audit(user, "提交主数据申请",
              f"提交{body.app_type}申请（模型 {model_id}）", request)
    return {"application_id": app_id, "status": "待审核", "duplicates": duplicates}


@router.get("/applications")
def list_applications(status: str | None = None, model_id: int | None = None,
                      user=Depends(get_current_user)):
    sql = """SELECT a.*, m.code AS model_code, m.name AS model_name
             FROM md_applications a LEFT JOIN md_models m ON m.id = a.model_id
             WHERE 1=1"""
    params: list = []
    if status:
        sql += " AND a.status = ?"
        params.append(status)
    if model_id is not None:
        sql += " AND a.model_id = ?"
        params.append(model_id)
    sql += " ORDER BY a.id"
    conn = get_conn()
    try:
        return [_parse_app(a) for a in rows_to_dicts(conn.execute(sql, params))]
    finally:
        conn.close()


@router.post("/applications/{app_id}/review")
def review_application(app_id: int, body: ReviewBody, request: Request,
                       user=Depends(get_current_user)):
    require_role(user, "admin")
    if body.decision not in ("通过", "驳回"):
        raise HTTPException(status_code=400, detail="非法审核决定")
    now = now_str()
    conn = get_conn()
    try:
        app = conn.execute(
            "SELECT * FROM md_applications WHERE id = ?", (app_id,)
        ).fetchone()
        if app is None:
            raise HTTPException(status_code=404, detail="申请不存在")
        if app["status"] != "待审核":
            raise HTTPException(status_code=400, detail="申请已审核，不能重复处理")
        model = _get_model(conn, app["model_id"])
        payload = parse_json(app["payload"], {})
        record = None
        if body.decision == "通过":
            if app["app_type"] == "新增":
                master_code = _gen_master_code(conn, model)
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO md_records
                       (model_id, master_code, attrs, source_system, source_code,
                        status, version, effective_from, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, '已发布', 1, ?, ?, ?)""",
                    (app["model_id"], master_code,
                     json.dumps(payload, ensure_ascii=False), "", "", now[:10],
                     now, now),
                )
                record = _parse_record(dict(conn.execute(
                    "SELECT * FROM md_records WHERE id = ?",
                    (cur.lastrowid,)).fetchone()))
                _write_history(conn, record["id"], 1, payload,
                               f"新增申请通过：{app['reason']}", user["username"])
            else:
                rec = conn.execute(
                    "SELECT * FROM md_records WHERE model_id = ? AND master_code = ?",
                    (app["model_id"], app["master_code"]),
                ).fetchone()
                if rec is None:
                    raise HTTPException(status_code=404, detail="主数据记录不存在")
                attrs = parse_json(rec["attrs"], {})
                if app["app_type"] == "变更":
                    attrs = {**attrs, **payload}
                    new_version = (rec["version"] or 1) + 1
                    conn.execute(
                        """UPDATE md_records SET attrs = ?, version = ?, updated_at = ?
                           WHERE id = ?""",
                        (json.dumps(attrs, ensure_ascii=False), new_version,
                         now, rec["id"]),
                    )
                    _write_history(conn, rec["id"], new_version, attrs,
                                   f"变更申请通过：{app['reason']}",
                                   user["username"])
                    record = _parse_record(dict(conn.execute(
                        "SELECT * FROM md_records WHERE id = ?",
                        (rec["id"],)).fetchone()))
                elif app["app_type"] == "停用":
                    conn.execute(
                        "UPDATE md_records SET status = '已停用', updated_at = ? WHERE id = ?",
                        (now, rec["id"]),
                    )
                    _write_history(conn, rec["id"], rec["version"], attrs,
                                   f"停用申请通过：{app['reason']}",
                                   user["username"])
                    record = _parse_record(dict(conn.execute(
                        "SELECT * FROM md_records WHERE id = ?",
                        (rec["id"],)).fetchone()))
                elif app["app_type"] == "合并":
                    conn.execute(
                        """UPDATE md_records SET status = '已合并', updated_at = ?
                           WHERE id = ?""",
                        (now, rec["id"]),
                    )
                    _write_history(conn, rec["id"], rec["version"], attrs,
                                   f"合并至 {app['merge_to_code']}：{app['reason']}",
                                   user["username"])
                    record = _parse_record(dict(conn.execute(
                        "SELECT * FROM md_records WHERE id = ?",
                        (rec["id"],)).fetchone()))
            new_status = "已通过"
        else:
            new_status = "已驳回"
        conn.execute(
            """UPDATE md_applications
               SET status = ?, reviewer = ?, review_comment = ?, reviewed_at = ?
               WHERE id = ?""",
            (new_status, user["username"], body.comment, now, app_id),
        )
        conn.commit()
        application = _parse_app(dict(conn.execute(
            "SELECT * FROM md_applications WHERE id = ?", (app_id,)).fetchone()))
    finally:
        conn.close()
    log_audit(user, "审核主数据申请",
              f"申请 {app_id}：{body.decision}", request)
    return {"application_id": app_id, "status": new_status,
            "record": record}


# ---------- 主数据记录 ----------

@router.get("/records")
def list_records(model_id: int | None = None, status: str | None = None,
                 q: str | None = None, user=Depends(get_current_user)):
    sql = """SELECT r.*, m.code AS model_code, m.name AS model_name
             FROM md_records r LEFT JOIN md_models m ON m.id = r.model_id
             WHERE 1=1"""
    params: list = []
    if model_id is not None:
        sql += " AND r.model_id = ?"
        params.append(model_id)
    if status:
        sql += " AND r.status = ?"
        params.append(status)
    if q:
        sql += " AND (r.master_code LIKE ? OR r.attrs LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY r.id"
    conn = get_conn()
    try:
        return [_parse_record(r) for r in rows_to_dicts(conn.execute(sql, params))]
    finally:
        conn.close()


@router.get("/records/{record_id}")
def get_record(record_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT * FROM md_records WHERE id = ?", (record_id,)
        ).fetchone()
        if r is None:
            raise HTTPException(status_code=404, detail="主数据记录不存在")
        record = _parse_record(dict(r))
        record["history"] = rows_to_dicts(conn.execute(
            "SELECT * FROM md_history WHERE record_id = ? ORDER BY version",
            (record_id,)))
        for h in record["history"]:
            h["attrs"] = parse_json(h.get("attrs"), {})
        record["distributions"] = rows_to_dicts(conn.execute(
            "SELECT * FROM md_distributions WHERE record_id = ? ORDER BY id",
            (record_id,)))
        record["code_maps"] = rows_to_dicts(conn.execute(
            "SELECT * FROM md_code_map WHERE master_code = ? ORDER BY id",
            (record["master_code"],)))
        return record
    finally:
        conn.close()


@router.put("/records/{record_id}")
def update_record(record_id: int, body: RecordUpdateBody, request: Request,
                  user=Depends(get_current_user)):
    require_role(user, "operator")
    now = now_str()
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT * FROM md_records WHERE id = ?", (record_id,)
        ).fetchone()
        if r is None:
            raise HTTPException(status_code=404, detail="主数据记录不存在")
        attrs = parse_json(r["attrs"], {})
        attrs = {**attrs, **body.attrs}
        new_version = (r["version"] or 1) + 1
        conn.execute(
            """UPDATE md_records SET attrs = ?, version = ?, updated_at = ?
               WHERE id = ?""",
            (json.dumps(attrs, ensure_ascii=False), new_version, now, record_id),
        )
        _write_history(conn, record_id, new_version, attrs,
                       "直接变更", user["username"])
        conn.commit()
        record = _parse_record(dict(conn.execute(
            "SELECT * FROM md_records WHERE id = ?", (record_id,)).fetchone()))
    finally:
        conn.close()
    log_audit(user, "直接变更主数据记录",
              f"主数据记录 {record_id} 直接变更（版本 {new_version}）", request)
    return record


@router.post("/records/{record_id}/distribute")
def distribute_record(record_id: int, body: DistributeBody, request: Request,
                      user=Depends(get_current_user)):
    require_role(user, "operator")
    now = now_str()
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT * FROM md_records WHERE id = ?", (record_id,)
        ).fetchone()
        if r is None:
            raise HTTPException(status_code=404, detail="主数据记录不存在")
        done = []
        for sys in body.target_systems:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO md_distributions
                   (record_id, target_system, status, result_msg, distributed_at)
                   VALUES (?, ?, '成功', '演示分发成功', ?)""",
                (record_id, sys, now),
            )
            done.append(sys)
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "主数据分发",
              f"主数据记录 {record_id} 分发至 {','.join(done)}", request)
    return {"record_id": record_id, "distributed": done}


# ---------- 编码映射 ----------

@router.post("/code-map")
def create_code_map(body: CodeMapBody, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "operator")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO md_code_map
               (model_id, master_code, source_system, source_code)
               VALUES (?, ?, ?, ?)""",
            (body.model_id, body.master_code, body.source_system,
             body.source_code),
        )
        conn.commit()
        cm = dict(conn.execute(
            "SELECT * FROM md_code_map WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "创建编码映射",
              f"{body.source_system}:{body.source_code} → {body.master_code}", request)
    return cm


@router.get("/code-map")
def list_code_map(model_id: int | None = None, source_system: str | None = None,
                  user=Depends(get_current_user)):
    sql = "SELECT * FROM md_code_map WHERE 1=1"
    params: list = []
    if model_id is not None:
        sql += " AND model_id = ?"
        params.append(model_id)
    if source_system:
        sql += " AND source_system = ?"
        params.append(source_system)
    sql += " ORDER BY id"
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()


# ---------- 三码关系（带有效时间） ----------

@router.post("/device-links")
def create_device_link(body: DeviceLinkBody, request: Request,
                      user=Depends(get_current_user)):
    require_role(user, "operator")
    now = now_str()
    conn = get_conn()
    try:
        # 同一逻辑码已有未到期关系时，自动截断旧 effective_to
        open_rows = conn.execute(
            """SELECT * FROM device_links
               WHERE logic_code = ?
                 AND (effective_to IS NULL OR effective_to > ?)""",
            (body.logic_code, body.effective_from),
        ).fetchall()
        truncated = 0
        for o in open_rows:
            conn.execute(
                "UPDATE device_links SET effective_to = ? WHERE id = ?",
                (body.effective_from, o["id"]),
            )
            truncated += 1
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO device_links
               (logic_code, model_code, physical_code, effective_from,
                effective_to, status, created_at)
               VALUES (?, ?, ?, ?, ?, '有效', ?)""",
            (body.logic_code, body.model_code, body.physical_code,
             body.effective_from, body.effective_to, now),
        )
        conn.commit()
        link = dict(conn.execute(
            "SELECT * FROM device_links WHERE id = ?",
            (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "创建三码关系",
              f"三码关系 {body.logic_code}→{body.physical_code}（截断旧关系 {truncated} 条）",
              request)
    return {"link": link, "truncated": truncated}


@router.get("/device-links")
def list_device_links(physical_code: str | None = None,
                      logic_code: str | None = None,
                      at: str | None = None,
                      user=Depends(get_current_user)):
    at = at or now_str()[:10]
    sql = """SELECT * FROM device_links
             WHERE effective_from <= ?
               AND (effective_to IS NULL OR effective_to >= ?)"""
    params: list = [at, at]
    if physical_code:
        sql += " AND physical_code = ?"
        params.append(physical_code)
    if logic_code:
        sql += " AND logic_code = ?"
        params.append(logic_code)
    sql += " ORDER BY id"
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()
