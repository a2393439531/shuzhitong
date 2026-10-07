"""四期：运营评价 —— 运营大盘 / 审计聚合。原创实现。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from ..config import settings
from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user
from ..permissions import require_role

router = APIRouter(prefix="/api/ops", tags=["ops"])


def _day_series(n: int) -> list:
    today = datetime.now().date()
    return [(today - timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(n - 1, -1, -1)]


def _count_by_day(conn, table: str, date_col: str, days: list,
                  extra_where: str = "", params: tuple = ()) -> dict:
    out = {d: 0 for d in days}
    start = days[0] + " 00:00:00"
    rows = rows_to_dicts(conn.execute(
        "SELECT substr(%s, 1, 10) AS d, COUNT(*) AS c FROM %s "
        "WHERE %s >= ? %s GROUP BY d" % (date_col, table, date_col,
                                        (" AND " + extra_where) if extra_where
                                        else ""),
        (start,) + tuple(params)))
    for r in rows:
        if r["d"] in out:
            out[r["d"]] = r["c"]
    return out


@router.get("/overview")
def ops_overview(user=Depends(get_current_user)):
    """运营大盘：治理进展 / 质量趋势 / 服务使用 / 问数使用 / 变更统计。"""
    require_role(user, "operator")
    days = _day_series(settings.SZT_OPS_TREND_DAYS)
    conn = get_conn()
    try:
        governance = {
            "objects": conn.execute(
                "SELECT COUNT(*) AS c FROM biz_objects").fetchone()["c"],
            "resources_published": conn.execute(
                "SELECT COUNT(*) AS c FROM resources "
                "WHERE status = '已发布'").fetchone()["c"],
            "standards_published": conn.execute(
                "SELECT COUNT(*) AS c FROM standards "
                "WHERE status = '已发布'").fetchone()["c"],
            "md_records": conn.execute(
                "SELECT COUNT(*) AS c FROM md_records "
                "WHERE status = '已发布'").fetchone()["c"],
            "indicators": conn.execute(
                "SELECT COUNT(*) AS c FROM indicators").fetchone()["c"],
            "services": conn.execute(
                "SELECT COUNT(*) AS c FROM services").fetchone()["c"],
            "bases": conn.execute(
                "SELECT COUNT(*) AS c FROM bases").fetchone()["c"],
        }
        quality_trend = {
            "days": days,
            "detected": [ _count_by_day(
                conn, "quality_issues", "created_at", days)[d] for d in days],
            "closed": [],
        }
        closed_map = {}
        for r in rows_to_dicts(conn.execute(
                "SELECT substr(closed_at, 1, 10) AS d, COUNT(*) AS c "
                "FROM quality_issues WHERE closed_at IS NOT NULL "
                "AND closed_at >= ? GROUP BY d",
                (days[0] + " 00:00:00",))):
            closed_map[r["d"]] = r["c"]
        quality_trend["closed"] = [closed_map.get(d, 0) for d in days]
        quality_trend["open"] = conn.execute(
            "SELECT COUNT(*) AS c FROM quality_issues "
            "WHERE status != '已关闭'").fetchone()["c"]

        svc_rows = rows_to_dicts(conn.execute(
            "SELECT s.name, COUNT(c.id) AS calls, "
            "SUM(CASE WHEN c.status_code >= 400 THEN 1 ELSE 0 END) AS errors "
            "FROM services s LEFT JOIN service_calls c "
            "ON c.service_id = s.id GROUP BY s.id, s.name "
            "ORDER BY calls DESC LIMIT 5"))
        for r in svc_rows:
            r["error_rate"] = (round(r["errors"] / r["calls"] * 100, 1)
                               if r["calls"] else 0.0)
        qa_total = conn.execute(
            "SELECT COUNT(*) AS c FROM qa_history").fetchone()["c"]
        qa_ok = conn.execute(
            "SELECT COUNT(*) AS c FROM qa_history "
            "WHERE status = 'success'").fetchone()["c"]
        qa_trend_map = _count_by_day(conn, "qa_history", "created_at", days)
        changes = rows_to_dicts(conn.execute(
            "SELECT status, COUNT(*) AS c FROM change_requests GROUP BY status"))
        notices = conn.execute(
            "SELECT COUNT(*) AS c FROM change_notices").fetchone()["c"]
    finally:
        conn.close()
    return {
        "governance": governance,
        "quality_trend": quality_trend,
        "service_usage": {"top": svc_rows},
        "qa_usage": {
            "total": qa_total,
            "success_rate": round(qa_ok / qa_total * 100, 1) if qa_total else 0,
            "trend": [{"day": d, "count": qa_trend_map[d]} for d in days],
        },
        "change_stats": {
            "by_status": changes,
            "notices_sent": notices,
        },
        "trend_days": len(days),
    }


@router.get("/audit-trend")
def audit_trend(action: str = Query(""), days: int = Query(14, le=90),
                user=Depends(get_current_user)):
    """审计聚合：按天/动作统计审计日志。"""
    require_role(user, "admin")
    day_list = _day_series(max(1, days))
    conn = get_conn()
    try:
        sql = ("SELECT substr(created_at, 1, 10) AS d, action, COUNT(*) AS c "
               "FROM audit_log WHERE created_at >= ?")
        params = [day_list[0] + " 00:00:00"]
        if action:
            sql += " AND action = ?"
            params.append(action)
        sql += " GROUP BY d, action ORDER BY d"
        rows = rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()
    by_day = {}
    for r in rows:
        by_day.setdefault(r["d"], {})[r["action"]] = r["c"]
    return {
        "days": day_list,
        "series": [{"day": d, "actions": by_day.get(d, {})} for d in day_list],
    }
