"""三期统一数据服务：服务执行引擎。原创实现。

供服务路由（app/routers/services.py）与三期智能问数复用。
本模块只依赖 database / deps / utils / scope / config，
禁止循环 import：任何 router 都不得被本模块引用。
"""
import time
from datetime import datetime

from .config import settings
from .database import get_conn  # noqa: F401 供外部复用保持一致入口
from .deps import now_str
from .scope import apply_scope
from .utils import parse_json


class ServiceError(Exception):
    """服务调用业务异常：携带 HTTP 状态码。"""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# ================= 5 个种子服务的 handler =================

def _h_md_eq(conn, params: dict, user):
    """SVC-MD-EQ 主数据服务：查 md_records（JOIN 取模型名）。"""
    params = params or {}
    sql = (
        "SELECT r.id, r.master_code, r.attrs, r.source_system, r.source_code,"
        " r.status, r.version, r.effective_from, r.effective_to,"
        " m.code AS model_code, m.name AS model_name"
        " FROM md_records r JOIN md_models m ON m.id = r.model_id"
        " WHERE 1=1"
    )
    args: list = []
    if params.get("code"):
        sql += " AND r.master_code = ?"
        args.append(params["code"])
    if params.get("model_code"):
        sql += " AND m.code = ?"
        args.append(params["model_code"])
    sql += " ORDER BY r.id"
    out = []
    for r in conn.execute(sql, args).fetchall():
        d = dict(r)
        d["attrs"] = parse_json(d.get("attrs"), {})
        out.append(d)
    return out


def _h_rel_3code(conn, params: dict, user):
    """SVC-REL-3CODE 关系服务：按逻辑码查指定时点的三码对应关系。"""
    params = params or {}
    logic_code = params.get("logic_code")
    if not logic_code:
        raise ServiceError(400, "缺少参数 logic_code")
    at = params.get("at_date") or datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT * FROM device_links
           WHERE logic_code = ?
             AND effective_from <= ?
             AND (effective_to IS NULL OR effective_to >= ?)
           ORDER BY id""",
        (logic_code, at, at),
    ).fetchall()
    return [dict(r) for r in rows]


def _h_wo_detail(conn, params: dict, user):
    """SVC-WO-DETAIL 明细查询：工单明细（部门级行过滤）。"""
    params = params or {}
    sql = "SELECT * FROM work_orders WHERE 1=1 {dept_filter}"
    args: list = []
    if params.get("base"):
        sql += " AND base = ?"
        args.append(params["base"])
    if params.get("model_code"):
        sql += " AND model_code = ?"
        args.append(params["model_code"])
    if params.get("start"):
        sql += " AND plan_start >= ?"
        args.append(params["start"])
    if params.get("end"):
        sql += " AND plan_end <= ?"
        args.append(params["end"])
    sql += " ORDER BY id"
    sql, scope_args = apply_scope(sql, user)
    return [dict(r) for r in conn.execute(sql, scope_args + args).fetchall()]


def _h_mat_cost(conn, params: dict, user):
    """SVC-MAT-COST 组合分析：按设备型号汇总物料领用次数与金额。"""
    params = params or {}
    # 内层只取 code/model_code，避免与 material_issues 的 dept 列歧义
    sql = (
        "SELECT sub.model_code AS model, COUNT(*) AS issue_count,"
        " SUM(m.amount) AS total_amount"
        " FROM material_issues m"
        " JOIN (SELECT code, model_code FROM work_orders) sub"
        "   ON m.wo_code = sub.code"
        " WHERE 1=1 {dept_filter}"
    )
    args: list = []
    if params.get("model_code"):
        sql += " AND sub.model_code = ?"
        args.append(params["model_code"])
    if params.get("start"):
        sql += " AND m.issue_date >= ?"
        args.append(params["start"])
    if params.get("end"):
        sql += " AND m.issue_date <= ?"
        args.append(params["end"])
    sql += " GROUP BY sub.model_code ORDER BY total_amount DESC"
    sql, scope_args = apply_scope(sql, user)
    return [dict(r) for r in conn.execute(sql, scope_args + args).fetchall()]


def _h_code_validate(conn, params: dict, user):
    """SVC-CODE-VALIDATE 校验服务：按标准编码校验值是否在允许值域内。"""
    params = params or {}
    std_code = params.get("std_code")
    value = params.get("value")
    if not std_code:
        raise ServiceError(400, "缺少参数 std_code")
    std = conn.execute(
        "SELECT * FROM standards WHERE code = ?", (std_code,)
    ).fetchone()
    if std is None:
        raise ServiceError(404, f"标准 {std_code} 不存在")
    allowed = parse_json(std["allowed_values"], [])
    if not isinstance(allowed, list):
        allowed = [allowed]
    return {"valid": value in allowed, "allowed": allowed}


# 服务编码 → handler
HANDLERS = {
    "SVC-MD-EQ": _h_md_eq,
    "SVC-REL-3CODE": _h_rel_3code,
    "SVC-WO-DETAIL": _h_wo_detail,
    "SVC-MAT-COST": _h_mat_cost,
    "SVC-CODE-VALIDATE": _h_code_validate,
}

# 模块级限流桶：{(user_id, service_id): [调用时间戳]}
_RATE_BUCKETS: dict = {}


def _write_call(conn, service_id: int, code: str, user, status_code: int,
                error: str, elapsed_ms: int) -> None:
    conn.execute(
        """INSERT INTO service_calls
           (service_id, user_id, username, endpoint, elapsed_ms,
            status_code, error, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (service_id, user["id"] if user is not None else None,
         user["username"] if user is not None else "",
         f"/api/services/{code}/invoke", elapsed_ms,
         status_code, error or None, now_str()),
    )
    conn.commit()


def invoke_service(conn, code: str, params: dict, user) -> dict:
    """统一服务调用入口：状态校验 → 限流 → 权限 → 执行 → 写调用日志。"""
    svc_row = conn.execute(
        "SELECT * FROM services WHERE code = ?", (code,)
    ).fetchone()
    if svc_row is None:
        raise ServiceError(404, f"服务 {code} 不存在")
    svc = dict(svc_row)
    if svc.get("status") != "已发布":
        raise ServiceError(400, f"服务 {code} 未发布，无法调用")

    # 限流：同一用户同一服务 60 秒窗口内至多 SZT_SVC_RATE_LIMIT 次
    key = (user["id"], svc["id"])
    now_ts = time.time()
    bucket = [t for t in _RATE_BUCKETS.get(key, []) if now_ts - t < 60]
    if len(bucket) >= settings.SZT_SVC_RATE_LIMIT:
        _write_call(conn, svc["id"], code, user, 429,
                    "调用过于频繁，请稍后再试", 0)
        raise ServiceError(429, "调用过于频繁，请稍后再试")
    bucket.append(now_ts)
    _RATE_BUCKETS[key] = bucket

    # 权限：super_admin/admin 直接过；公开服务过；其余须已授权订阅
    role = user.get("role")
    if role not in ("super_admin", "admin") \
            and (svc.get("permission_req") or "") != "公开":
        sub = conn.execute(
            """SELECT 1 FROM service_subscriptions
               WHERE service_id = ? AND user_id = ? AND status = '已授权'""",
            (svc["id"], user["id"]),
        ).fetchone()
        if sub is None:
            _write_call(conn, svc["id"], code, user, 403, "未授权，请先申请", 0)
            raise ServiceError(403, "未授权，请先申请")

    handler = HANDLERS.get(code)
    if handler is None:
        _write_call(conn, svc["id"], code, user, 400,
                    f"服务 {code} 尚未接入执行引擎", 0)
        raise ServiceError(400, f"服务 {code} 尚未接入执行引擎")

    start = time.perf_counter()
    try:
        data = handler(conn, params or {}, user)
    except ServiceError as e:
        elapsed = int((time.perf_counter() - start) * 1000)
        _write_call(conn, svc["id"], code, user, e.status_code, e.message,
                    elapsed)
        raise
    except Exception as e:  # handler 内部未预期异常统一转为 500
        elapsed = int((time.perf_counter() - start) * 1000)
        _write_call(conn, svc["id"], code, user, 500, str(e), elapsed)
        raise ServiceError(500, f"服务执行失败：{e}")
    elapsed = int((time.perf_counter() - start) * 1000)
    _write_call(conn, svc["id"], code, user, 200, "", elapsed)
    return {"ok": True, "data": data, "elapsed_ms": elapsed}
