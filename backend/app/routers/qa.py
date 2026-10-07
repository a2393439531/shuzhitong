"""三期智能问数：中文问数 → 统一口径 → 图表 + 五要素回答。原创实现。"""
import json
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from .. import qa_engine as qa
from ..config import settings
from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..llm import LLMClient
from ..scope import is_super_admin
from ..utils import parse_json

router = APIRouter(prefix="/api/qa", tags=["qa"])

# 输入安全门：分号 / 危险关键字直接拦截（用户文本永不进 SQL）
_INJECT_GUARD = re.compile(r";|--|/\*", re.IGNORECASE)

REFUSE_ERROR = ("该问题超出口径范围，智能问数仅支持维修工单、设备三码、"
                "备件领料三类数据的指标 / 明细查询。")

FOLLOW_UPS = {
    "metric": ["查看指标口径", "换个时间范围再问", "按型号对比看看"],
    "service": ["查询设备三码关系", "校验设备编码", "查询工单明细"],
    "sql": ["换个条件再查", "查询设备三码关系", "查看指标口径"],
    "refuse": ["查看指标口径", "查询设备三码关系"],
}


class _NeedClarify(Exception):
    """执行中发现缺关键输入，转 need_clarify 而非 error。"""

    def __init__(self, questions: list):
        super().__init__("; ".join(questions))
        self.questions = questions


class AskBody(BaseModel):
    question: str
    chart: str = "auto"  # auto / line / bar / pie / stat / table
    base_code: str | None = None  # 四期：基地上下文，按基地差异口径计算并声明


# ================= 内部：ask 主流程 =================

def _llm_client() -> LLMClient:
    try:
        return LLMClient.from_settings()
    except Exception:
        return LLMClient(provider="disabled")


def _history_row_to_dict(r: dict) -> dict:
    r = dict(r)
    r["understanding"] = parse_json(r.get("understanding"), {})
    r["is_favorite"] = bool(r.get("is_favorite"))
    # 全量回答（ask 时存的 response JSON）合并进来，供前端直接渲染
    resp = parse_json(r.pop("response", None), {})
    if isinstance(resp, dict):
        for k in ("scope", "chart", "sources", "follow_ups", "clarify_questions",
                  "columns", "rows"):
            if k in resp and k not in r:
                r[k] = resp[k]
    return r


def _save_history(conn, user, question, status, *, understanding=None,
                  sql=None, via=None, chart_type=None, row_count=0,
                  interpretation=None, quality_note=None, error=None) -> int:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO qa_history
           (user_id, question, understanding, sql, via, chart_type, row_count,
            interpretation, quality_note, is_favorite, status, error, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
        (user["id"], question,
         json.dumps(understanding or {}, ensure_ascii=False), sql, via,
         chart_type, row_count, interpretation, quality_note, status,
         error, now_str()),
    )
    conn.commit()
    return cur.lastrowid


def _org_label(user, entities: dict) -> str:
    if entities.get("base"):
        return entities["base"]
    if is_super_admin(user):
        return "全范围"
    return user["dept"] or "本部门"


def _understanding_text(intent: dict, entities: dict) -> str:
    kind = intent["kind"]
    tl = entities.get("time_label", "")
    if kind == "metric":
        dim = ""
        if entities.get("model_code"):
            dim = f"（型号 {entities['model_code']}）"
        return f"查询{tl}{intent.get('name', '')}{dim}（指标 {intent.get('code')}）"
    if kind == "service":
        return f"{intent.get('name', '')}（服务 {intent.get('code')}）"
    if kind == "sql":
        target_name = qa.TABLE_NAMES.get(intent.get("target", ""), "")
        return f"查询{tl}{target_name}明细（受控 SQL）"
    return "未能识别问题意图"


def _run_ask(conn, user, question: str, chart_mode: str,
             request: Request | None, base_code: str | None = None) -> dict:
    t0 = time.perf_counter()
    question = (question or "").strip()
    llm = _llm_client()

    def _finish(payload: dict, status: str, audit_result: str = "成功") -> dict:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        payload["elapsed_ms"] = elapsed_ms
        # 存全量回答 JSON，供历史载入时完整渲染五要素
        try:
            conn.execute(
                "UPDATE qa_history SET response = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False, default=str),
                 payload.get("id")),
            )
            conn.commit()
        except Exception:
            pass
        log_audit(user, "qa_ask", question[:200], request,
                  elapsed_ms=elapsed_ms, result=audit_result)
        return payload

    # ---- 安全门：注入拦截 ----
    if _INJECT_GUARD.search(question) or qa._DANGEROUS_KW.search(question):
        hid = _save_history(conn, user, question, "refused",
                            understanding={"intent": "blocked",
                                           "text": "输入含有非法字符或关键字"},
                            error="检测到非法字符或关键字，请求已被拦截。")
        return _finish({
            "id": hid, "question": question, "status": "refused",
            "understanding": {"intent": "blocked", "text": "输入含有非法字符或关键字"},
            "error": "检测到非法字符或关键字，请求已被拦截。",
            "follow_ups": FOLLOW_UPS["refuse"],
        }, "refused", audit_result="拦截")

    # ---- 1. 意图识别 ----
    intent = qa.detect_intent(question)
    if intent["kind"] == "refuse":
        understanding = {"intent": "refuse", "entities": {},
                         "text": _understanding_text(intent, {})}
        hid = _save_history(conn, user, question, "refused",
                            understanding=understanding, error=REFUSE_ERROR)
        return _finish({
            "id": hid, "question": question, "status": "refused",
            "understanding": understanding, "error": REFUSE_ERROR,
            "follow_ups": FOLLOW_UPS["refuse"],
        }, "refused", audit_result="口径外拒绝")

    # ---- 2. 实体抽取 ----
    entities = qa.extract_entities(question)
    if intent["kind"] == "metric" and not entities.get("period_start"):
        understanding = {"intent": "metric",
                         "target": intent.get("code"),
                         "entities": entities,
                         "text": _understanding_text(intent, entities)}
        hid = _save_history(conn, user, question, "need_clarify",
                            understanding=understanding, via="metric")
        return _finish({
            "id": hid, "question": question, "status": "need_clarify",
            "understanding": understanding,
            "clarify_questions": ["请补充统计时间范围，例如：近一年 / 2026年1月"],
            "follow_ups": FOLLOW_UPS["metric"],
        }, "need_clarify", audit_result="需澄清")

    # ---- 3. 执行 ----
    try:
        if intent["kind"] == "metric":
            payload = _exec_metric(conn, user, intent, entities, question,
                                   chart_mode, llm, base_code)
        elif intent["kind"] == "service":
            payload = _exec_service(conn, user, intent, entities, question,
                                    chart_mode, llm)
        else:
            payload = _exec_sql(conn, user, intent, entities, question,
                                chart_mode, llm)
    except _NeedClarify as e:
        understanding = {"intent": intent["kind"],
                         "target": intent.get("code") or intent.get("target"),
                         "entities": entities,
                         "text": _understanding_text(intent, entities)}
        hid = _save_history(conn, user, question, "need_clarify",
                            understanding=understanding,
                            via=intent["kind"])
        return _finish({
            "id": hid, "question": question, "status": "need_clarify",
            "understanding": understanding,
            "clarify_questions": e.questions,
            "follow_ups": FOLLOW_UPS.get(intent["kind"], FOLLOW_UPS["refuse"]),
        }, "need_clarify", audit_result="需澄清")
    except (qa.MetricError, qa.ServiceError) as e:
        err_msg = getattr(e, "message", None) or str(e)
        understanding = {"intent": intent["kind"],
                         "target": intent.get("code") or intent.get("target"),
                         "entities": entities,
                         "text": _understanding_text(intent, entities)}
        hid = _save_history(conn, user, question, "error",
                            understanding=understanding,
                            via=intent["kind"], error=err_msg)
        return _finish({
            "id": hid, "question": question, "status": "error",
            "understanding": understanding, "error": err_msg,
            "follow_ups": FOLLOW_UPS.get(intent["kind"], FOLLOW_UPS["refuse"]),
        }, "error", audit_result="失败")
    except Exception as e:  # noqa: BLE001 - 统一转 error 状态
        understanding = {"intent": intent["kind"],
                         "target": intent.get("code") or intent.get("target"),
                         "entities": entities,
                         "text": _understanding_text(intent, entities)}
        hid = _save_history(conn, user, question, "error",
                            understanding=understanding,
                            via=intent["kind"], error=f"执行失败：{e}")
        return _finish({
            "id": hid, "question": question, "status": "error",
            "understanding": understanding, "error": f"执行失败：{e}",
            "follow_ups": FOLLOW_UPS.get(intent["kind"], FOLLOW_UPS["refuse"]),
        }, "error", audit_result="失败")

    hid = _save_history(conn, user, question, "success",
                        understanding=payload["understanding"],
                        sql=payload.get("sql"), via=payload["via"],
                        chart_type=payload["chart"]["chart_type"],
                        row_count=payload["row_count"],
                        interpretation=payload["interpretation"],
                        quality_note=payload.get("quality_note"))
    payload["id"] = hid
    payload["is_favorite"] = False
    return _finish(payload, "success")


# ================= 三类执行分支 =================

def _metric_dimension(question: str, entities: dict, code: str) -> str:
    if any(k in question for k in ("趋势", "每月", "变化")):
        return "time"
    if any(k in question for k in ("对比", "型号", "基地")):
        return "category"
    if code == "MAT_COST_BY_MODEL" and not entities.get("model_code"):
        return "category"
    return "stat"


def _exec_metric(conn, user, intent, entities, question, chart_mode, llm,
                 base_code: str | None = None) -> dict:
    code = intent["code"]
    start, end = entities["period_start"], entities["period_end"]
    dim = ("model_code", entities["model_code"]) if entities.get("model_code") \
        else (None, None)
    res = qa.compute_metric(conn, code, start, end,
                            dimension=dim[0], dimension_value=dim[1], user=user)

    eff = qa.get_effective_caliber(conn, code, base_code)
    caliber = {"caliber": eff["caliber"], "target": eff["target"]}
    base_note = eff["base_note"]
    dimension_kind = _metric_dimension(question, entities, code)
    columns, rows, dimension_kind = qa.metric_chart_rows(
        conn, code, entities, user, dimension_kind)

    # 数值格式化与结论
    if code == "WO_ON_TIME_RATE":
        name = "维修工单按期完成率"
        if res["denominator"]:
            pct = f"{res['value'] * 100:.1f}%"
            base = (f"{entities['time_label']}{name}为 {pct}"
                    f"（按期完工 {qa._fmt_int(res['numerator'])} 单 / "
                    f"计划完成 {qa._fmt_int(res['denominator'])} 单）")
        else:
            pct, base = "—", f"{entities['time_label']}无纳入统计的维修工单"
        head_rows = [{"指标": name, "数值": pct}]
        stat_val = round(res["value"] * 100, 1) if res["value"] is not None else 0
    elif code == "EQ_INTACT_RATE":
        name = "设备完好率"
        if res["denominator"]:
            pct = f"{res['value'] * 100:.1f}%"
            base = (f"{name}为 {pct}"
                    f"（完好 {qa._fmt_int(res['numerator'])} 台 / "
                    f"共 {qa._fmt_int(res['denominator'])} 台）")
        else:
            pct, base = "—", "暂无设备三码数据"
        head_rows = [{"指标": name, "数值": pct}]
        stat_val = round(res["value"] * 100, 1) if res["value"] is not None else 0
    else:
        name = "备件消耗金额"
        csql, cparams = qa.apply_qa_scope(
            "SELECT COUNT(*) AS c FROM material_issues "
            "WHERE substr(issue_date, 1, 7) >= ? "
            "AND substr(issue_date, 1, 7) <= ? {dept_filter}",
            user, {"material_issues"})
        cnt = conn.execute(csql, [start, end] + cparams).fetchone()["c"] or 0
        base = (f"{entities['time_label']}{name}合计 "
                f"{qa._fmt_num(res['value'])} 元（共 {qa._fmt_int(cnt)} 笔领料）")
        head_rows = [{"指标": name, "数值": f"{qa._fmt_num(res['value'])} 元"}]
        stat_val = res["value"]

    if dimension_kind == "stat" or not rows:
        columns, rows = ["指标", "数值"], head_rows
        dimension_kind = "stat"
        chart_data = qa.build_chart("stat", columns, rows)
        chart_data["series"] = [{"name": name, "data": [stat_val]}]
    else:
        chart_data = qa.build_chart(dimension_kind, columns, rows)

    ctype = chart_mode if chart_mode in (
        "line", "bar", "pie", "stat", "table") else \
        qa.detect_chart_type(question, columns, dimension_kind)
    if ctype != chart_data["chart_type"]:
        chart_data = qa.build_chart(ctype, columns, rows)

    interpretation = qa.build_interpretation(base, llm)
    if base_note:
        interpretation += "\n【口径声明】" + base_note
    tables = [caliber.get("target") or "work_orders"]
    return {
        "question": question, "status": "success",
        "understanding": {"intent": "metric", "target": code,
                          "entities": entities,
                          "text": _understanding_text(intent, entities)},
        "scope": {"caliber": caliber["caliber"],
                   "time": f"{start}~{end}",
                   "org": _org_label(user, entities),
                   "base": {"code": base_code, "note": base_note}},
        "sql": None, "via": "metric",
        "columns": columns, "rows": rows, "row_count": len(rows),
        "chart": chart_data,
        "interpretation": interpretation,
        "quality_note": qa.build_quality_note(conn, tables, user),
        "sources": [{"name": qa.TABLE_NAMES.get(t, t),
                     "updated_at": qa.table_updated_at(conn, t)}
                    for t in tables],
        "follow_ups": FOLLOW_UPS["metric"],
    }


def _exec_service(conn, user, intent, entities, question, chart_mode, llm) -> dict:
    code = intent["code"]
    params: dict = {}
    understanding_extra: dict = {}
    if code == "SVC-REL-3CODE":
        params["logic_code"] = entities.get("logic_code") or "L-AFW-001"
        if not entities.get("logic_code"):
            understanding_extra["assumption"] = \
                "问题中未指定逻辑设备编码，默认按 L-AFW-001 查询"
    elif code == "SVC-CODE-VALIDATE":
        m = re.search(r"STD-\d+", question)
        std_code = m.group(0) if m else None
        if not std_code:
            raise _NeedClarify(["请指定校验依据的标准编码，例如：按 STD-002 校验 P-AFW-001"])
        value = entities.get("logic_code")
        if not value or value == std_code:
            mc = entities.get("model_code")
            value = mc if mc and mc != std_code else None
        if not value:
            raise _NeedClarify(["请提供要校验的编码值，例如：按 STD-002 校验 P-AFW-001"])
        params["std_code"] = std_code
        params["value"] = value
    elif code == "SVC-WO-DETAIL":
        for k in ("model_code", "base"):
            if entities.get(k):
                params[k] = entities[k]

    res = qa.invoke_service(conn, code, params, user)
    data = res.get("data")
    # 真实引擎：明细类服务返回 list，校验类返回 dict
    records = data if isinstance(data, list) else (data or {}).get("records", [])
    columns = list(records[0].keys()) if records else []
    rows = records

    ctype = chart_mode if chart_mode in (
        "line", "bar", "pie", "stat", "table") else \
        qa.detect_chart_type(question, columns, None)
    chart_data = qa.build_chart(ctype, columns, rows)

    if code == "SVC-REL-3CODE":
        base = (f"逻辑设备 {params['logic_code']} 共关联 {len(rows)} 条三码记录"
                if rows else f"未查到逻辑设备 {params['logic_code']} 的三码记录")
        tables = ["device_links"]
        caliber = "设备三码关系：逻辑编码—型号编码—物理编码对应，取当前有效版本"
    elif code == "SVC-CODE-VALIDATE":
        v = (data or {}).get("valid")
        std_name = ""
        try:
            srow = conn.execute("SELECT name FROM standards WHERE code = ?",
                                (params["std_code"],)).fetchone()
            std_name = f"（{srow['name']}）" if srow else ""
        except Exception:
            pass
        base = (f"编码 {params['value']} 按标准 {params['std_code']}{std_name}"
                f"校验{'通过' if v else '不通过'}")
        tables = ["device_links"]
        caliber = "编码校验：在标准允许值域中精确匹配待校验编码"
    else:
        base = f"共查到 {len(rows)} 条工单记录"
        tables = ["work_orders"]
        caliber = qa.get_caliber(conn, "WO_ON_TIME_RATE")["caliber"]

    interpretation = qa.build_interpretation(base, llm)
    understanding = {"intent": "service", "target": code,
                     "entities": entities,
                     "text": _understanding_text(intent, entities),
                     **understanding_extra}
    return {
        "question": question, "status": "success",
        "understanding": understanding,
        "scope": {"caliber": caliber,
                   "time": entities.get("time_label", "全部"),
                   "org": _org_label(user, entities)},
        "sql": None, "via": "service",
        "columns": columns, "rows": rows, "row_count": len(rows),
        "chart": chart_data,
        "interpretation": interpretation,
        "quality_note": qa.build_quality_note(conn, tables, user),
        "sources": [{"name": qa.TABLE_NAMES.get(t, t),
                     "updated_at": qa.table_updated_at(conn, t)}
                    for t in tables],
        "follow_ups": FOLLOW_UPS["service"],
    }


def _exec_sql(conn, user, intent, entities, question, chart_mode, llm) -> dict:
    target = intent.get("target") or "work_orders"
    llm_client = _llm_client()
    sql = qa.build_sql_via_llm({**intent, "question": question}, entities,
                               llm_client)
    if sql is None:
        sql = qa.build_template_sql(intent, entities)
    ok, reason = qa.validate_select_sql(sql)
    if not ok:
        raise qa.MetricError(f"生成的 SQL 未通过安全校验：{reason}")

    # 注入行级过滤 + 实体过滤
    scoped_sql, scope_params = qa.apply_qa_scope(sql, user, {target})
    ent_clause, ent_params = qa.entity_filter_clause(target, entities)
    final_sql = scoped_sql.replace("{entity_filter}", ent_clause)
    if "{entity_filter}" in final_sql:  # 模板外 SQL 缺占位时直接追加
        final_sql = final_sql.replace("{entity_filter}", "")
    rows = [dict(r) for r in conn.execute(
        final_sql, scope_params + ent_params).fetchall()]
    columns = list(rows[0].keys()) if rows else []

    ctype = chart_mode if chart_mode in (
        "line", "bar", "pie", "stat", "table") else \
        qa.detect_chart_type(question, columns, None)
    chart_data = qa.build_chart(ctype, columns, rows)

    base = (f"共查到 {len(rows)} 条{qa.TABLE_NAMES.get(target, '')}记录"
            f"（上限 {settings.SZT_QA_SQL_LIMIT}）")
    interpretation = qa.build_interpretation(base, llm)
    return {
        "question": question, "status": "success",
        "understanding": {"intent": "sql", "target": target,
                          "entities": entities,
                          "text": _understanding_text(intent, entities)},
        "scope": {"caliber": f"明细查询：{qa.TABLE_NAMES.get(target, target)}全部字段（受控只读）",
                   "time": entities.get("time_label", "全部"),
                   "org": _org_label(user, entities)},
        "sql": final_sql, "via": "sql",
        "columns": columns, "rows": rows, "row_count": len(rows),
        "chart": chart_data,
        "interpretation": interpretation,
        "quality_note": qa.build_quality_note(conn, [target], user),
        "sources": [{"name": qa.TABLE_NAMES.get(target, target),
                     "updated_at": qa.table_updated_at(conn, target)}],
        "follow_ups": FOLLOW_UPS["sql"],
    }


# ================= 路由 =================

@router.post("/ask")
def ask(body: AskBody, request: Request, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        return _run_ask(conn, user, body.question, body.chart, request,
                        body.base_code)
    finally:
        conn.close()


@router.get("/history")
def list_history(
    favorite_only: int = 0,
    show_all: int = Query(0, alias="all"),
    user=Depends(get_current_user),
):
    sql = "SELECT * FROM qa_history WHERE 1=1"
    params: list = []
    if not (show_all and user["role"] in ("super_admin", "admin")):
        sql += " AND user_id = ?"
        params.append(user["id"])
    if favorite_only:
        sql += " AND is_favorite = 1"
    sql += " ORDER BY id DESC"
    conn = get_conn()
    try:
        return [_history_row_to_dict(r)
                for r in rows_to_dicts(conn.execute(sql, params))]
    finally:
        conn.close()


def _own_record(conn, hid: int, user) -> dict:
    r = conn.execute(
        "SELECT * FROM qa_history WHERE id = ? AND user_id = ?",
        (hid, user["id"])).fetchone()
    if r is None:
        raise HTTPException(status_code=404, detail="问数记录不存在")
    return dict(r)


@router.patch("/history/{hid}/favorite")
def toggle_favorite(hid: int, request: Request,
                    user=Depends(get_current_user)):
    conn = get_conn()
    try:
        rec = _own_record(conn, hid, user)
        new_val = 0 if rec["is_favorite"] else 1
        conn.execute("UPDATE qa_history SET is_favorite = ? WHERE id = ?",
                     (new_val, hid))
        conn.commit()
        rec["is_favorite"] = new_val
    finally:
        conn.close()
    log_audit(user, "收藏问数记录", f"问数记录 {hid} 收藏={'是' if new_val else '否'}",
              request)
    return _history_row_to_dict(rec)


@router.post("/history/{hid}/rerun")
def rerun(hid: int, request: Request, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        rec = _own_record(conn, hid, user)
        result = _run_ask(conn, user, rec["question"], "auto", request)
    finally:
        conn.close()
    return result


@router.delete("/history/{hid}")
def delete_history(hid: int, request: Request,
                   user=Depends(get_current_user)):
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT * FROM qa_history WHERE id = ?", (hid,)).fetchone()
        if r is None:
            raise HTTPException(status_code=404, detail="问数记录不存在")
        if r["user_id"] != user["id"] and \
                user["role"] not in ("super_admin", "admin"):
            raise HTTPException(status_code=403, detail="无权删除他人记录")
        conn.execute("DELETE FROM qa_history WHERE id = ?", (hid,))
        conn.commit()
    finally:
        conn.close()
    log_audit(user, "删除问数记录", f"问数记录 {hid} 已删除", request)
    return {"deleted": hid}
