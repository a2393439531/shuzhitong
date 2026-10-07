"""三期统一数据服务：服务目录 / 发布 / 订阅 / 调用。原创实现。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..permissions import require_role
from ..services_engine import ServiceError, invoke_service

router = APIRouter(prefix="/api/services", tags=["services"])

# svc_type 中文映射
SVC_TYPE_LABEL = {
    "master": "主数据服务",
    "relation": "关系服务",
    "detail": "明细查询服务",
    "metric": "指标服务",
    "combo": "组合分析服务",
    "validate": "校验服务",
}


class ServiceBody(BaseModel):
    code: str
    name: str
    svc_type: str = "detail"
    description: str = ""
    object_id: int | None = None
    data_source: str = ""
    standard_version: str = ""
    owner: str = ""
    permission_req: str = "公开"
    quality_status: str = ""
    update_freq: str = ""
    api_version: str = ""
    endpoint_path: str = ""


class ServiceUpdateBody(BaseModel):
    name: str | None = None
    svc_type: str | None = None
    description: str | None = None
    object_id: int | None = None
    data_source: str | None = None
    standard_version: str | None = None
    owner: str | None = None
    permission_req: str | None = None
    quality_status: str | None = None
    update_freq: str | None = None
    api_version: str | None = None
    endpoint_path: str | None = None


class ReviewBody(BaseModel):
    approve: bool
    note: str = ""


class InvokeBody(BaseModel):
    params: dict = {}


SERVICE_COLS = ("code, name, svc_type, description, object_id, data_source,"
                " standard_version, owner, permission_req, quality_status,"
                " update_freq, api_version, endpoint_path")


def _label(row: dict) -> dict:
    row["svc_type_label"] = SVC_TYPE_LABEL.get(row.get("svc_type"), "")
    return row


def _get_service(conn, sid: int) -> dict:
    svc = conn.execute(
        "SELECT * FROM services WHERE id = ?", (sid,)
    ).fetchone()
    if svc is None:
        raise HTTPException(status_code=404, detail="数据服务不存在")
    return dict(svc)


# ---------- 列表 / 通知 / 我的订阅（静态路径先声明） ----------

@router.get("")
def list_services(user=Depends(get_current_user)):
    conn = get_conn()
    try:
        rows = rows_to_dicts(conn.execute(
            "SELECT id, code, name, svc_type, status, api_version,"
            " quality_status, owner FROM services ORDER BY id"))
        return [_label(r) for r in rows]
    finally:
        conn.close()


@router.get("/notices")
def list_notices(user=Depends(get_current_user)):
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(
            """SELECT n.*, s.name AS service_name, s.code AS service_code
               FROM service_notices n JOIN services s ON s.id = n.service_id
               ORDER BY n.id DESC LIMIT 20"""))
    finally:
        conn.close()


@router.get("/subscriptions/mine")
def my_subscriptions(user=Depends(get_current_user)):
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(
            """SELECT sub.*, s.name AS service_name, s.code AS service_code
               FROM service_subscriptions sub
               JOIN services s ON s.id = sub.service_id
               WHERE sub.user_id = ? ORDER BY sub.id DESC""",
            (user["id"],)))
    finally:
        conn.close()


@router.get("/subscriptions")
def list_subscriptions(status: str | None = None,
                       user=Depends(get_current_user)):
    """全部订阅申请（admin+；供审核）。"""
    require_role(user, "admin")
    conn = get_conn()
    try:
        sql = """SELECT sub.*, s.name AS service_name, s.code AS service_code
                 FROM service_subscriptions sub
                 JOIN services s ON s.id = sub.service_id WHERE 1=1"""
        params: list = []
        if status:
            sql += " AND sub.status = ?"
            params.append(status)
        sql += " ORDER BY sub.id DESC"
        return rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()


@router.post("")
def create_service(body: ServiceBody, request: Request,
                   user=Depends(get_current_user)):
    require_role(user, "admin")
    if body.svc_type not in SVC_TYPE_LABEL:
        raise HTTPException(status_code=400, detail="非法服务类型")
    if body.permission_req not in ("公开", "授权"):
        raise HTTPException(status_code=400, detail="权限要求只能是 公开/授权")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM services WHERE code = ?", (body.code,)
        ).fetchone() is not None:
            raise HTTPException(status_code=400, detail="服务编码已存在")
        cur = conn.cursor()
        cur.execute(
            f"""INSERT INTO services
               ({SERVICE_COLS}, version, status, created_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '草稿', ?, ?)""",
            (body.code, body.name, body.svc_type, body.description,
             body.object_id, body.data_source, body.standard_version,
             body.owner, body.permission_req, body.quality_status,
             body.update_freq, body.api_version, body.endpoint_path,
             body.api_version or "", user["username"], now_str()),
        )
        conn.commit()
        svc = _get_service(conn, cur.lastrowid)
    finally:
        conn.close()
    log_audit(user, "创建数据服务",
              f"创建数据服务「{body.name}」({body.code})", request)
    return _label(svc)


@router.post("/subscriptions/{sub_id}/review")
def review_subscription(sub_id: int, body: ReviewBody, request: Request,
                        user=Depends(get_current_user)):
    require_role(user, "admin")
    now = now_str()
    conn = get_conn()
    try:
        sub = conn.execute(
            "SELECT * FROM service_subscriptions WHERE id = ?", (sub_id,)
        ).fetchone()
        if sub is None:
            raise HTTPException(status_code=404, detail="订阅申请不存在")
        sub = dict(sub)
        if sub["status"] != "待审核":
            raise HTTPException(status_code=400, detail="订阅申请已处理")
        new_status = "已授权" if body.approve else "已拒绝"
        conn.execute(
            """UPDATE service_subscriptions
               SET status = ?, reviewed_at = ?, review_note = ?
               WHERE id = ?""",
            (new_status, now, body.note or None, sub_id),
        )
        conn.commit()
        sub = dict(conn.execute(
            "SELECT * FROM service_subscriptions WHERE id = ?",
            (sub_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "审核服务订阅",
              f"订阅申请 {sub_id} {'通过' if body.approve else '拒绝'}", request)
    return sub


# ---------- 详情 / 更新 / 发布 / 下架 / 订阅 / 调用 / 统计 ----------

@router.get("/{sid}")
def get_service(sid: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        svc = _label(_get_service(conn, sid))
        svc["versions"] = rows_to_dicts(conn.execute(
            "SELECT * FROM service_versions WHERE service_id = ?"
            " ORDER BY id DESC", (sid,)))
        svc["notices"] = rows_to_dicts(conn.execute(
            "SELECT * FROM service_notices WHERE service_id = ?"
            " ORDER BY id DESC LIMIT 5", (sid,)))
        return svc
    finally:
        conn.close()


@router.put("/{sid}")
def update_service(sid: int, body: ServiceUpdateBody, request: Request,
                   user=Depends(get_current_user)):
    require_role(user, "admin")
    data = body.model_dump(exclude_unset=True)
    if "svc_type" in data and data["svc_type"] not in SVC_TYPE_LABEL:
        raise HTTPException(status_code=400, detail="非法服务类型")
    if "permission_req" in data and data["permission_req"] not in ("公开", "授权"):
        raise HTTPException(status_code=400, detail="权限要求只能是 公开/授权")
    conn = get_conn()
    try:
        _get_service(conn, sid)
        if data:
            sets = ", ".join(f"{k} = ?" for k in data)
            conn.execute(f"UPDATE services SET {sets} WHERE id = ?",
                         (*data.values(), sid))
            conn.commit()
        svc = _get_service(conn, sid)
    finally:
        conn.close()
    log_audit(user, "更新数据服务", f"数据服务 {sid} 已更新", request)
    return _label(svc)


@router.post("/{sid}/publish")
def publish_service(sid: int, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "admin")
    now = now_str()
    conn = get_conn()
    try:
        svc = _get_service(conn, sid)
        old_status = svc.get("status")
        ver_count = conn.execute(
            "SELECT COUNT(*) c FROM service_versions WHERE service_id = ?",
            (sid,)).fetchone()["c"]
        version = svc.get("api_version") or f"v1.{ver_count + 1}"
        conn.execute("UPDATE services SET status = '已发布' WHERE id = ?",
                     (sid,))
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO service_versions
               (service_id, version, change_desc, created_at)
               VALUES (?, ?, ?, ?)""",
            (sid, version, "发布", now),
        )
        if old_status == "已发布":
            content = f"服务「{svc['name']}」版本更新：{version}"
        else:
            content = f"服务「{svc['name']}」已发布，版本 {version}"
        cur.execute(
            """INSERT INTO service_notices
               (service_id, version, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (sid, version, content, now),
        )
        conn.commit()
        svc = _get_service(conn, sid)
    finally:
        conn.close()
    log_audit(user, "发布数据服务",
              f"数据服务「{svc['name']}」已发布（{version}）", request)
    return _label(svc)


@router.post("/{sid}/offline")
def offline_service(sid: int, request: Request,
                    user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        svc = _get_service(conn, sid)
        subs = conn.execute(
            """SELECT COUNT(*) c FROM service_subscriptions
               WHERE service_id = ? AND status = '已授权'""",
            (sid,)).fetchone()["c"]
        cutoff = (datetime.now() - timedelta(days=30)
                  ).strftime("%Y-%m-%d %H:%M:%S")
        calls = conn.execute(
            """SELECT COUNT(*) c FROM service_calls
               WHERE service_id = ? AND created_at >= ?""",
            (sid, cutoff)).fetchone()["c"]
        if subs or calls:
            return JSONResponse(
                status_code=400,
                content={"detail": "存在依赖，无法下架",
                         "dependencies": {"subscriptions": subs,
                                          "recent_calls": calls}},
            )
        conn.execute("UPDATE services SET status = '已下架' WHERE id = ?",
                     (sid,))
        conn.commit()
        svc = _get_service(conn, sid)
    finally:
        conn.close()
    log_audit(user, "下架数据服务", f"数据服务「{svc['name']}」已下架", request)
    return _label(svc)


@router.post("/{sid}/subscribe")
def subscribe_service(sid: int, request: Request,
                      user=Depends(get_current_user)):
    now = now_str()
    conn = get_conn()
    try:
        svc = _get_service(conn, sid)
        exist = conn.execute(
            """SELECT * FROM service_subscriptions
               WHERE service_id = ? AND user_id = ?
                 AND status IN ('待审核', '已授权')
               ORDER BY id DESC LIMIT 1""",
            (sid, user["id"]),
        ).fetchone()
        if exist is not None:
            return dict(exist)  # 幂等：已有申请直接返回
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO service_subscriptions
               (service_id, user_id, username, status, applied_at)
               VALUES (?, ?, ?, '待审核', ?)""",
            (sid, user["id"], user["username"], now),
        )
        conn.commit()
        sub = dict(conn.execute(
            "SELECT * FROM service_subscriptions WHERE id = ?",
            (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "申请服务订阅",
              f"申请订阅数据服务「{svc['name']}」", request)
    return sub


@router.post("/{code}/invoke")
def invoke(code: str, body: InvokeBody, request: Request,
            user=Depends(get_current_user)):
    conn = get_conn()
    try:
        try:
            result = invoke_service(conn, code, body.params or {}, user)
        except ServiceError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)
    finally:
        conn.close()
    log_audit(user, "service_invoke",
              f"调用数据服务 {code}，耗时 {result['elapsed_ms']}ms", request,
              elapsed_ms=result["elapsed_ms"])
    return result


@router.get("/{sid}/stats")
def service_stats(sid: int, user=Depends(get_current_user)):
    require_role(user, "admin")
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    try:
        _get_service(conn, sid)
        row = conn.execute(
            """SELECT COUNT(*) AS c,
                      COALESCE(AVG(elapsed_ms), 0) AS avg_ms,
                      COALESCE(SUM(CASE WHEN status_code != 200
                                       THEN 1 ELSE 0 END), 0) AS err
               FROM service_calls
               WHERE service_id = ? AND created_at >= ?""",
            (sid, cutoff)).fetchone()
        total = row["c"]
        return {"calls_7d": total,
                "avg_ms": round(float(row["avg_ms"]), 2),
                "error_rate": round(row["err"] / total, 4) if total else 0.0}
    finally:
        conn.close()
