"""指标标准管理：定义 / 版本 / 计算 / 趋势。原创实现。"""
import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..metrics_engine import MetricError, compute_metric
from ..permissions import require_role
from ..utils import parse_json

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

# 版本对比时逐项比对的定义字段
COMPARE_FIELDS = ("calc_rule", "scope_include", "scope_exclude",
                  "time_rule", "granularity", "biz_def")


class MetricBody(BaseModel):
    code: str = ""
    name: str = ""
    biz_def: str = ""
    calc_rule: dict = {}
    scope_include: str = ""
    scope_exclude: str = ""
    time_rule: str = ""
    granularity: str = ""
    dimensions: list = []
    data_sources: list = []
    owner_dept: str = ""
    owner_role: str = ""
    formula_desc: str = ""


class MetricUpdateBody(MetricBody):
    change_desc: str = ""


class ComputeBody(BaseModel):
    period_start: str
    period_end: str
    dimension: str | None = None
    dimension_value: str | None = None


def _parse_indicator(ind: dict) -> dict:
    ind = dict(ind)
    ind["calc_rule"] = parse_json(ind.get("calc_rule"), {})
    ind["dimensions"] = parse_json(ind.get("dimensions"), [])
    ind["data_sources"] = parse_json(ind.get("data_sources"), [])
    return ind


def _get_indicator(conn, code: str) -> dict:
    ind = conn.execute(
        "SELECT * FROM indicators WHERE code = ?", (code,)
    ).fetchone()
    if ind is None:
        raise HTTPException(status_code=404, detail=f"指标 {code} 不存在")
    return dict(ind)


def _snapshot_of(body: MetricBody, code: str) -> dict:
    return {
        "code": code,
        "name": body.name,
        "biz_def": body.biz_def,
        "calc_rule": body.calc_rule or {},
        "scope_include": body.scope_include,
        "scope_exclude": body.scope_exclude,
        "time_rule": body.time_rule,
        "granularity": body.granularity,
        "dimensions": body.dimensions or [],
        "data_sources": body.data_sources or [],
        "owner_dept": body.owner_dept,
        "owner_role": body.owner_role,
        "formula_desc": body.formula_desc,
    }


def _bump_version(version: str) -> str:
    """minor+1：v1.0 -> v2.0。"""
    m = re.match(r"v(\d+)\.(\d+)$", (version or "").strip())
    if not m:
        return "v1.0"
    return f"v{int(m.group(1)) + 1}.0"


# ---------- 列表 / 详情 ----------

@router.get("")
def list_metrics(user=Depends(get_current_user)):
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(
            """SELECT id, code, name, version, status, owner_dept
               FROM indicators WHERE code IS NOT NULL ORDER BY code"""))
    finally:
        conn.close()


@router.get("/{code}")
def get_metric(code: str, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        ind = _parse_indicator(_get_indicator(conn, code))
        ind["version_count"] = conn.execute(
            "SELECT COUNT(*) c FROM indicator_versions WHERE indicator_id = ?",
            (ind["id"],),
        ).fetchone()["c"]
        return ind
    finally:
        conn.close()


# ---------- 创建 / 更新 / 删除（admin+） ----------

@router.post("")
def create_metric(body: MetricBody, request: Request,
                  user=Depends(get_current_user)):
    require_role(user, "admin")
    code = (body.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="指标编码不能为空")
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="指标名称不能为空")
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT 1 FROM indicators WHERE code = ?", (code,)
        ).fetchone() is not None:
            raise HTTPException(status_code=400, detail=f"指标编码 {code} 已存在")
        snap = _snapshot_of(body, code)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO indicators
               (name, code, biz_def, calc_rule, scope_include, scope_exclude,
                time_rule, granularity, dimensions, data_sources,
                owner_dept, owner_role, formula_desc, version, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'v1.0', '已发布', ?)""",
            (body.name, code, body.biz_def,
             json.dumps(snap["calc_rule"], ensure_ascii=False),
             body.scope_include, body.scope_exclude, body.time_rule,
             body.granularity,
             json.dumps(snap["dimensions"], ensure_ascii=False),
             json.dumps(snap["data_sources"], ensure_ascii=False),
             body.owner_dept, body.owner_role, body.formula_desc, now_str()),
        )
        indicator_id = cur.lastrowid
        conn.execute(
            """INSERT INTO indicator_versions
               (indicator_id, version, snapshot, change_desc, created_at)
               VALUES (?, 'v1.0', ?, '初始版本', ?)""",
            (indicator_id, json.dumps(snap, ensure_ascii=False), now_str()),
        )
        conn.commit()
        ind = _parse_indicator(conn.execute(
            "SELECT * FROM indicators WHERE id = ?",
            (indicator_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, "创建指标", f"创建指标 {code}（v1.0，已发布）", request)
    return ind


@router.put("/{code}")
def update_metric(code: str, body: MetricUpdateBody, request: Request,
                  user=Depends(get_current_user)):
    require_role(user, "admin")
    if not (body.change_desc or "").strip():
        raise HTTPException(status_code=400, detail="change_desc 必填")
    conn = get_conn()
    try:
        ind = _get_indicator(conn, code)
        new_version = _bump_version(ind.get("version"))
        snap = _snapshot_of(body, code)
        # 空字段沿用旧值，保证快照完整
        old_snap_row = conn.execute(
            """SELECT snapshot FROM indicator_versions
               WHERE indicator_id = ? AND version = ?
               ORDER BY id DESC LIMIT 1""",
            (ind["id"], ind.get("version")),
        ).fetchone()
        old_snap = parse_json(
            old_snap_row["snapshot"] if old_snap_row else None, {})
        for k, v in snap.items():
            if k == "code":
                continue
            if (v == "" or v == {} or v == []) and k in old_snap:
                snap[k] = old_snap[k]
        conn.execute(
            """UPDATE indicators
               SET name = ?, biz_def = ?, calc_rule = ?, scope_include = ?,
                   scope_exclude = ?, time_rule = ?, granularity = ?,
                   dimensions = ?, data_sources = ?, owner_dept = ?,
                   owner_role = ?, formula_desc = ?, version = ?
               WHERE id = ?""",
            (snap["name"], snap["biz_def"],
             json.dumps(snap["calc_rule"], ensure_ascii=False),
             snap["scope_include"], snap["scope_exclude"], snap["time_rule"],
             snap["granularity"],
             json.dumps(snap["dimensions"], ensure_ascii=False),
             json.dumps(snap["data_sources"], ensure_ascii=False),
             snap["owner_dept"], snap["owner_role"], snap["formula_desc"],
             new_version, ind["id"]),
        )
        conn.execute(
            """INSERT INTO indicator_versions
               (indicator_id, version, snapshot, change_desc, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (ind["id"], new_version,
             json.dumps(snap, ensure_ascii=False),
             body.change_desc.strip(), now_str()),
        )
        conn.commit()
        ind = _parse_indicator(conn.execute(
            "SELECT * FROM indicators WHERE id = ?", (ind["id"],)).fetchone())
    finally:
        conn.close()
    log_audit(user, "更新指标",
              f"指标 {code} 更新至 {new_version}：{body.change_desc.strip()}",
              request)
    return ind


@router.delete("/{code}")
def delete_metric(code: str, request: Request,
                  user=Depends(get_current_user)):
    require_role(user, "admin")
    conn = get_conn()
    try:
        ind = _get_indicator(conn, code)
        conn.execute("DELETE FROM indicator_results WHERE indicator_id = ?",
                     (ind["id"],))
        conn.execute("DELETE FROM indicator_versions WHERE indicator_id = ?",
                     (ind["id"],))
        conn.execute("DELETE FROM indicators WHERE id = ?", (ind["id"],))
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "删除指标", f"指标 {code} 已删除", request)
    return {"deleted": code}


# ---------- 版本 ----------

@router.get("/{code}/versions")
def list_versions(code: str, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        ind = _get_indicator(conn, code)
        return rows_to_dicts(conn.execute(
            """SELECT version, change_desc, created_at
               FROM indicator_versions
               WHERE indicator_id = ? ORDER BY id""",
            (ind["id"],)))
    finally:
        conn.close()


def _norm_field(field: str, value):
    if field == "calc_rule":
        return json.dumps(parse_json(value, {}), ensure_ascii=False,
                          sort_keys=True)
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


@router.get("/{code}/compare")
def compare_versions(code: str, from_: str = Query(alias="from"), to: str = "",
                     user=Depends(get_current_user)):
    conn = get_conn()
    try:
        ind = _get_indicator(conn, code)
        snaps = {}
        for v in (from_, to):
            row = conn.execute(
                """SELECT snapshot FROM indicator_versions
                   WHERE indicator_id = ? AND version = ?
                   ORDER BY id DESC LIMIT 1""",
                (ind["id"], v),
            ).fetchone()
            if row is None:
                raise HTTPException(
                    status_code=404, detail=f"指标 {code} 无版本 {v}")
            snaps[v] = parse_json(row["snapshot"], {})
        diff = []
        for f in COMPARE_FIELDS:
            a, b = _norm_field(f, snaps[from_].get(f)), _norm_field(f, snaps[to].get(f))
            if a != b:
                diff.append({"field": f,
                             "from": snaps[from_].get(f),
                             "to": snaps[to].get(f)})
        return {"diff": diff,
                "has_caliber_diff": any(d["field"] == "calc_rule" for d in diff)}
    finally:
        conn.close()


# ---------- 计算 / 趋势（登录即可） ----------

def _compute_or_400(conn, code: str, body: ComputeBody, user) -> dict:
    try:
        return compute_metric(conn, code, body.period_start, body.period_end,
                              body.dimension, body.dimension_value, user)
    except MetricError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/{code}/compute")
def compute(code: str, body: ComputeBody, request: Request,
            user=Depends(get_current_user)):
    conn = get_conn()
    try:
        try:
            result = _compute_or_400(conn, code, body, user)
        except HTTPException as e:
            log_audit(user, "metric_compute",
                      f"指标 {code} 计算失败：{e.detail}", request,
                      result="失败")
            raise
    finally:
        conn.close()
    log_audit(user, "metric_compute",
              f"指标 {code} 计算 {result['period']} → {result['value']}"
              f"（{'缓存' if result['cached'] else '实时'}）", request)
    return result


@router.get("/{code}/trend")
def trend(code: str, months: int = 12, dimension: str | None = None,
          dimension_value: str | None = None,
          user=Depends(get_current_user)):
    months = max(1, min(int(months or 12), 36))
    now = datetime.now()
    yms = []
    y, m = now.year, now.month
    for _ in range(months):
        yms.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    yms.reverse()
    conn = get_conn()
    try:
        out = []
        for ym in yms:
            try:
                r = compute_metric(conn, code, ym, ym, dimension,
                                   dimension_value, user)
            except MetricError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            out.append({"period": ym, "value": r["value"]})
        return out
    finally:
        conn.close()
