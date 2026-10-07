"""三期智能问数引擎：意图识别 / 实体抽取 / 受控 SQL / 图表整形 / 结论组装。

原创实现。安全红线：
- 口径只来自本地固定定义或 indicators 表，绝不由 LLM 定义；
- 用户提问文本永不直接拼入 SQL（只走模板 + 参数化）；
- 结论只基于真实计算结果，不编造数字。
"""
import json
import re
from datetime import date

from .config import settings
from .deps import now_str
from .llm import LLMClient
from .scope import dept_filter_clause, is_super_admin
from .utils import parse_json


# ================= 跨模块复用契约 =================
# metrics_engine / services_engine 由并行 worker 提供；缺失时用本地 mock
# 兜底（签名与契约一致），真实模块一旦就位 import 即自动切换。

try:  # pragma: no cover - 真实模块就位时走此分支
    from .metrics_engine import MetricError, compute_metric
    _METRICS_REAL = True
except ImportError:
    _METRICS_REAL = False

    class MetricError(Exception):
        """指标计算失败（mock 版，与真实契约同名）"""

    def compute_metric(conn, code, period_start, period_end, dimension=None,
                       dimension_value=None, user=None):
        return _mock_compute_metric(conn, code, period_start, period_end,
                                    dimension, dimension_value, user)

try:  # pragma: no cover - 真实模块就位时走此分支
    from .services_engine import ServiceError, invoke_service
    _SERVICES_REAL = True
except ImportError:
    _SERVICES_REAL = False

    class ServiceError(Exception):
        """服务调用失败（mock 版，与真实契约同名）"""

    def invoke_service(conn, code, params, user):
        return _mock_invoke_service(conn, code, params, user)


# 供测试与报告查询：哪些引擎当前是 mock
MOCKED_ENGINES = {"metrics": not _METRICS_REAL, "services": not _SERVICES_REAL}


# ================= 问数 allowlist =================

# 智能问数允许触及的试点表（白名单）
QA_TABLES = {"work_orders", "material_issues", "device_links"}

# 其中带 dept 列、可做行级部门过滤的表
DEPT_TABLES = {"work_orders", "material_issues"}

# 表中文名（用于口径/来源展示）
TABLE_NAMES = {
    "work_orders": "维修工单台账",
    "material_issues": "备件领料台账",
    "device_links": "设备三码关系表",
}

# 危险关键字黑名单（单词级匹配）
_DANGEROUS_KW = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|"
    r"replace|pragma|attach|vacuum|exec|execute|copy|load)\b",
    re.IGNORECASE,
)


# ================= 受控 SQL 校验 =================

def validate_select_sql(sql: str, allowed_tables: set | None = None) -> tuple:
    """校验 SQL 是否为安全的单条只读查询。返回 (ok, reason)。"""
    allowed = QA_TABLES if allowed_tables is None else set(allowed_tables)
    if not sql or not str(sql).strip():
        return False, "SQL 为空"
    cleaned = re.sub(r"/\*.*?\*/", "", str(sql), flags=re.DOTALL)  # 块注释
    cleaned = re.sub(r"--[^\n]*", "", cleaned)  # 行注释
    if ";" in cleaned:
        return False, "只允许单条语句（检测到分号）"
    if not re.match(r"(?is)^\s*(select|with)\b", cleaned):
        return False, "只允许 SELECT/WITH 开头的只读查询"
    if _DANGEROUS_KW.search(cleaned):
        return False, "SQL 含有危险关键字，已拦截"
    # 提取 CTE 别名（WITH x AS (...)），不计入外部表
    cte_names = set(re.findall(r"(?i)\bwith\s+([a-zA-Z_]\w*)\s+as\b", cleaned))
    cte_names |= set(re.findall(r"(?i),\s*([a-zA-Z_]\w*)\s+as\s*\(", cleaned))
    tables = set(re.findall(r"(?i)\bfrom\s+([a-zA-Z_]\w*)", cleaned))
    tables |= set(re.findall(r"(?i)\bjoin\s+([a-zA-Z_]\w*)", cleaned))
    tables -= cte_names
    illegal = {t for t in tables if t not in allowed}
    if illegal:
        return False, f"表 {sorted(illegal)} 不在问数白名单内"
    if not tables:
        return False, "未识别到查询表"
    return True, "ok"


# ================= 意图识别 =================

def detect_intent(question: str) -> dict:
    """识别问数意图。返回 {"kind": metric/service/sql/refuse, ...}。"""
    q = (question or "").strip()
    if "完成率" in q:
        return {"kind": "metric", "code": "WO_ON_TIME_RATE",
                "name": "维修工单按期完成率"}
    if "完好率" in q:
        return {"kind": "metric", "code": "EQ_INTACT_RATE", "name": "设备完好率"}
    if any(k in q for k in ("三码", "关系")):
        return {"kind": "service", "code": "SVC-REL-3CODE", "name": "设备三码关系查询"}
    if "校验" in q:
        return {"kind": "service", "code": "SVC-CODE-VALIDATE", "name": "设备编码校验"}
    if any(k in q for k in ("工单明细", "工单列表")):
        return {"kind": "service", "code": "SVC-WO-DETAIL", "name": "工单明细查询"}
    detail_word = any(k in q for k in ("明细", "列表", "查询"))
    if any(k in q for k in ("备件", "费用", "金额", "消耗")) and not detail_word:
        return {"kind": "metric", "code": "MAT_COST_BY_MODEL", "name": "备件消耗金额"}
    if any(k in q for k in ("工单", "设备", "备件", "领料", "明细", "列表", "查询")):
        target = "work_orders"
        if any(k in q for k in ("备件", "领料")):
            target = "material_issues"
        elif "设备" in q and "工单" not in q:
            target = "device_links"
        return {"kind": "sql", "target": target}
    return {"kind": "refuse"}


# ================= 实体抽取 =================

def _month_add(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def extract_entities(question: str) -> dict:
    """抽取时间范围 / 型号 / 逻辑编码 / 基地。"""
    q = (question or "").strip()
    ent: dict = {}
    today = date.today()
    this_month = today.strftime("%Y-%m")

    # ---- 时间 ----
    m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月", q) or \
        re.search(r"\b(20\d{2})-(\d{1,2})\b", q)
    if m:
        ym = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
        ent["period_start"] = ym
        ent["period_end"] = ym
        ent["time_label"] = ym
    elif re.search(r"近\s*12\s*个月|近一年", q):
        start = _month_add(this_month, -11)
        ent["period_start"] = start
        ent["period_end"] = this_month
        ent["time_label"] = f"近一年（{start}~{this_month}）"
    elif re.search(r"近\s*(一|1)\s*个月|近一月|本月", q):
        ent["period_start"] = this_month
        ent["period_end"] = this_month
        ent["time_label"] = f"本月（{this_month}）"

    # ---- 型号：AFW-1000 ----
    m = re.search(r"[A-Z]+-\d+[A-Z]*", q)
    if m:
        ent["model_code"] = m.group(0)

    # ---- 逻辑编码：L-AFW-001 ----
    m = re.search(r"\b[A-Z]-[A-Z]+-\d+\b", q)
    if m:
        ent["logic_code"] = m.group(0)

    # ---- 基地 ----
    m = re.search(r"(一号基地|二号基地)", q)
    if m:
        ent["base"] = m.group(1)

    return ent


def default_period() -> dict:
    """缺省时间范围：近一年。"""
    ent = extract_entities("近一年")
    return {"period_start": ent["period_start"], "period_end": ent["period_end"],
            "time_label": ent["time_label"]}


# ================= 模板 SQL =================

_SQL_TEMPLATES = {
    "work_orders": (
        "SELECT code, device_code, model_code, base, plan_end, actual_end, status "
        "FROM work_orders WHERE 1=1 {dept_filter} {entity_filter} "
        "ORDER BY plan_end DESC LIMIT {limit}"
    ),
    "material_issues": (
        "SELECT wo_code, material_code, material_name, qty, amount, issue_date "
        "FROM material_issues WHERE 1=1 {dept_filter} {entity_filter} "
        "ORDER BY issue_date DESC LIMIT {limit}"
    ),
    "device_links": (
        "SELECT logic_code, model_code, physical_code, status, effective_from "
        "FROM device_links WHERE 1=1 {dept_filter} {entity_filter} "
        "ORDER BY id DESC LIMIT {limit}"
    ),
}

# 实体 → 各表过滤条件
_ENTITY_FILTERS = {
    "work_orders": {
        "model_code": "AND model_code = ?",
        "base": "AND base = ?",
    },
    "material_issues": {},
    "device_links": {
        "model_code": "AND model_code = ?",
    },
}


def entity_filter_clause(target: str, entities: dict) -> tuple:
    """实体过滤子句。返回 (子句片段, 参数列表)。"""
    parts, params = [], []
    mapping = _ENTITY_FILTERS.get(target, {})
    for key, frag in mapping.items():
        if entities.get(key):
            parts.append(frag)
            params.append(entities[key])
    # 时间范围：工单按 plan_end，领料按 issue_date 归属
    if entities.get("period_start"):
        date_col = {"work_orders": "plan_end",
                    "material_issues": "issue_date"}.get(target)
        if date_col:
            parts.append(f"AND {date_col} >= ? AND {date_col} < ?")
            params.append(entities["period_start"])
            params.append(_month_add(entities["period_end"], 1))
    clause = " ".join(parts)
    return clause, params


def build_template_sql(intent: dict, entities: dict) -> str:
    """按意图/实体生成受控 SQL 模板（含 {dept_filter}/{entity_filter} 占位）。"""
    target = (intent or {}).get("target") or "work_orders"
    if target not in _SQL_TEMPLATES:
        target = "work_orders"
    # 注意：模板内 {dept_filter}/{entity_filter} 须原样保留，故不用 str.format
    return _SQL_TEMPLATES[target].replace(
        "{limit}", str(settings.SZT_QA_SQL_LIMIT))


def build_sql_via_llm(intent: dict, entities: dict,
                      llm_client: LLMClient | None) -> str | None:
    """LLM 生成 SQL（仅在 LLM 已配置时尝试）；失败返回 None 走模板。"""
    if llm_client is None or not llm_client.configured():
        return None
    target = (intent or {}).get("target") or "work_orders"
    question = (intent or {}).get("question") or ""
    tables = ", ".join(sorted(QA_TABLES))
    system = (
        "你是数治通智能问数 SQL 生成器。严格遵守：\n"
        "1. 只输出单条 SELECT 语句，不输出解释文字、前后代码块标记；\n"
        f"2. 只能使用以下表：{tables}；\n"
        "3. 必须包含 WHERE 1=1 {dept_filter} {entity_filter} 占位符；\n"
        f"4. 末尾必须有 LIMIT {settings.SZT_QA_SQL_LIMIT}；\n"
        "5. 禁止任何 DDL/DML、子查询注入、多语句。"
    )
    res = llm_client.chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": f"表：{target}；实体：{json.dumps(entities, ensure_ascii=False)}；问题：{question}"}],
        temperature=0.0,
    )
    if not res.ok:
        return None
    sql = res.content.strip()
    sql = re.sub(r"^```\w*\s*|\s*```$", "", sql).strip()
    ok, _ = validate_select_sql(sql)
    return sql if ok else None


def apply_qa_scope(sql: str, user, tables: set, dept_qualifier: str = "") -> tuple:
    """问数行级过滤：只有带 dept 列的表才注入部门条件。返回 (sql, params)。

    dept_qualifier：多表 JOIN 时给 dept 列加表别名前缀，如 "m."。
    """
    if is_super_admin(user) or not (set(tables) & DEPT_TABLES):
        return sql.replace("{dept_filter}", ""), []
    col = f"{dept_qualifier}dept" if dept_qualifier else "dept"
    return sql.replace("{dept_filter}", f"AND {col} = ?"), [user["dept"]]


# ================= 图表类型与整形 =================

def detect_chart_type(question: str, columns: list, dimension_kind: str | None) -> str:
    """问题关键词 + 维度类型 → 图表类型。"""
    q = (question or "")
    if any(k in q for k in ("趋势", "每月", "变化")) or dimension_kind == "time":
        return "line"
    if any(k in q for k in ("占比", "构成")):
        return "pie"
    if any(k in q for k in ("对比", "型号", "基地")) or dimension_kind == "category":
        return "bar"
    if dimension_kind == "stat":
        return "stat"
    return "table"


def rows_hint(columns: list) -> list:
    return columns  # 保留：供外部按需取列信息


def build_chart(chart_type: str, columns: list, rows: list,
                x_field: str | None = None, y_field: str | None = None) -> dict:
    """把 rows+columns 整形成 echarts 友好结构；table 则原样透出。"""
    chart = {"chart_type": chart_type, "x": [], "series": []}
    if chart_type == "table" or not rows or not columns:
        return chart
    if chart_type == "stat":
        label = columns[0] if columns else "指标"
        chart["x"] = [label]
        chart["series"] = [{"name": label, "data": [rows[0].get(columns[1]) if len(columns) > 1 else rows[0].get(label)]}]
        return chart
    x_field = x_field or columns[0]
    chart["x"] = [r.get(x_field) for r in rows]
    if chart_type in ("line", "bar"):
        # 折线/柱状：除 x 轴外的所有数值列都作为 series
        for c in columns:
            if c == x_field:
                continue
            vals = [r.get(c) for r in rows]
            if all(isinstance(v, (int, float)) or v is None for v in vals):
                chart["series"].append({"name": str(c), "data": vals})
        if not chart["series"]:  # 无数值列时回退首列
            y_candidates = [c for c in columns if c != x_field]
            yf = y_field or (y_candidates[0] if y_candidates else x_field)
            chart["series"] = [{"name": str(yf),
                                "data": [r.get(yf) for r in rows]}]
        return chart
    y_candidates = [c for c in columns if c != x_field]
    y_field = y_field or (y_candidates[0] if y_candidates else x_field)
    chart["series"] = [{"name": str(y_field), "data": [r.get(y_field) for r in rows]}]
    return chart


# ================= 口径（绝不由 LLM 定义） =================

# 本地固定口径（indicators 表未维护 code 时的兜底，与种子公式一致）
_LOCAL_CALIBERS = {
    "WO_ON_TIME_RATE": {
        "caliber": "维修工单按期完成率 = 按期完工工单数 ÷ 计划完成工单总数；"
                   "取消单不纳入统计；延期审批通过的工单按审批后日期考核；"
                   "时间口径：按计划完成日期归属统计期",
        "target": "work_orders",
    },
    "EQ_INTACT_RATE": {
        "caliber": "设备完好率 = 完好设备数 ÷ 设备总数；"
                   "以设备三码关系表中状态为“有效”的物理设备为完好",
        "target": "device_links",
    },
    "MAT_COST_BY_MODEL": {
        "caliber": "备件消耗金额 = 备件领料金额合计（退料金额为负数冲减）；"
                   "时间口径：按领料日期归属统计期",
        "target": "material_issues",
    },
}


def get_caliber(conn, code: str) -> dict:
    """口径来源：优先 indicators 表（code 匹配），否则本地固定定义。"""
    local = _LOCAL_CALIBERS.get(code, {})
    try:
        row = conn.execute(
            "SELECT biz_def, time_rule FROM indicators WHERE code = ?",
            (code,)).fetchone()
    except Exception:
        row = None
    if row and row["biz_def"]:
        caliber = row["biz_def"]
        if row["time_rule"]:
            caliber += f"；时间口径：{row['time_rule']}"
        return {"caliber": caliber, "target": local.get("target", "")}
    return {"caliber": local.get("caliber", "口径未定义"),
            "target": local.get("target", "")}


# ================= 结论组装（只陈述真实数字） =================

def _fmt_num(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        if v.is_integer():
            return f"{int(v):,}"
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,}" if isinstance(v, int) else str(v)


def _fmt_int(v) -> str:
    """计数类数字：去掉 .0 后缀。"""
    try:
        f = float(v)
        return f"{int(f):,}" if f.is_integer() else _fmt_num(v)
    except (TypeError, ValueError):
        return str(v)


def build_interpretation(base: str, llm_client: LLMClient | None = None) -> str:
    """本地模板结论；LLM 仅做措辞润色（不得改数字、不得新增口径）。"""
    base = (base or "").strip()
    if llm_client is None or not llm_client.configured():
        return base
    res = llm_client.chat(
        [{"role": "system",
          "content": "你是措辞润色助手。把用户给出的结论改写得更通顺，"
                     "严格禁止：修改任何数字、新增任何口径说明、添加原文没有的结论。"
                     "只返回改写后的结论文本。"},
         {"role": "user", "content": base}],
        temperature=0.2,
    )
    if not res.ok or not res.content:
        return base
    # 兜底：润色结果丢失数字则回退本地版
    nums = set(re.findall(r"\d[\d,.]*%?", base))
    if nums and not all(n in res.content for n in nums):
        return base
    return res.content.strip()


def build_quality_note(conn, tables: list, user, period: dict | None = None) -> str:
    """数据质量说明：数据来源 + 取消单排除数。"""
    parts = []
    for t in tables:
        if t in TABLE_NAMES:
            updated = _table_updated_at(conn, t)
            parts.append(f"{TABLE_NAMES[t]}（{t}，数据更新至 {updated}）")
    note = "数据来源：" + "、".join(parts) + "。" if parts else ""
    if "work_orders" in tables:
        sql, params = apply_qa_scope(
            "SELECT COUNT(*) AS c FROM work_orders WHERE cancel_flag = 1 {dept_filter}",
            user, {"work_orders"})
        try:
            n = conn.execute(sql, params).fetchone()["c"] or 0
        except Exception:
            n = 0
        if n:
            note += f"已排除 {n} 条取消单（不纳入统计）。"
    return note


def _table_updated_at(conn, table: str) -> str:
    col = {"work_orders": "plan_end", "material_issues": "issue_date",
           "device_links": "created_at"}.get(table, "created_at")
    try:
        v = conn.execute(f"SELECT MAX({col}) AS m FROM {table}").fetchone()["m"]
        return str(v)[:10] if v else now_str()[:10]
    except Exception:
        return now_str()[:10]


# 公开别名（供 router 调用）
table_updated_at = _table_updated_at


# ================= mock 引擎（真实模块缺失时的兜底） =================

def _scoped(sql: str, user, tables: set, dept_qualifier: str = "") -> tuple:
    return apply_qa_scope(sql, user, tables, dept_qualifier)


def _mock_compute_metric(conn, code, period_start, period_end, dimension=None,
                         dimension_value=None, user=None) -> dict:
    """与真实契约同签名的本地 mock：直接对试点表做口径计算。"""
    start, end = period_start, _month_add(period_end, 1)
    period = f"{period_start}~{period_end}"
    dim_filter, dim_params = "", []
    if dimension == "model_code" and dimension_value:
        dim_filter, dim_params = "AND model_code = ?", [dimension_value]

    if code == "WO_ON_TIME_RATE":
        sql, params = _scoped(
            "SELECT COUNT(*) AS d, "
            "SUM(CASE WHEN actual_end IS NOT NULL AND actual_end <= plan_end "
            "THEN 1 ELSE 0 END) AS n FROM work_orders "
            "WHERE cancel_flag = 0 AND plan_end >= ? AND plan_end < ? "
            f"{dim_filter} {{dept_filter}}",
            user, {"work_orders"})
        r = conn.execute(sql, [start, end] + dim_params + params).fetchone()
        d, n = r["d"] or 0, r["n"] or 0
        value = round(n / d, 4) if d else None
        return {"value": value, "numerator": n, "denominator": d,
                "version": "mock-v1", "period": period,
                "cached": False, "computed_at": now_str()}

    if code == "EQ_INTACT_RATE":
        r = conn.execute(
            "SELECT COUNT(DISTINCT physical_code) AS d, "
            "COUNT(DISTINCT CASE WHEN status = '有效' THEN physical_code END) AS n "
            "FROM device_links").fetchone()
        d, n = r["d"] or 0, r["n"] or 0
        value = round(n / d, 4) if d else None
        return {"value": value, "numerator": n, "denominator": d,
                "version": "mock-v1", "period": period,
                "cached": False, "computed_at": now_str()}

    if code == "MAT_COST_BY_MODEL":
        sql, params = _scoped(
            "SELECT COUNT(*) AS d, COALESCE(SUM(amount), 0) AS n "
            "FROM material_issues WHERE issue_date >= ? AND issue_date < ? "
            "{dept_filter}",
            user, {"material_issues"})
        r = conn.execute(sql, [start, end] + params).fetchone()
        d, n = r["d"] or 0, r["n"] or 0
        return {"value": round(n, 2), "numerator": round(n, 2),
                "denominator": d, "version": "mock-v1", "period": period,
                "cached": False, "computed_at": now_str()}

    raise MetricError(f"未知指标编码：{code}")


def _mock_invoke_service(conn, code, params, user) -> dict:
    """与真实契约同签名的本地 mock：直接读试点表。"""
    params = params or {}
    if code == "SVC-REL-3CODE":
        logic_code = params.get("logic_code") or "L-AFW-001"
        rows = conn.execute(
            "SELECT logic_code, model_code, physical_code, status, "
            "effective_from, effective_to FROM device_links "
            "WHERE logic_code = ? ORDER BY id",
            (logic_code,)).fetchall()
        return {"ok": True,
                "data": {"logic_code": logic_code,
                         "records": [dict(r) for r in rows],
                         "count": len(rows)},
                "elapsed_ms": 0}
    if code == "SVC-CODE-VALIDATE":
        code_v = (params.get("code") or "").strip()
        found = []
        if code_v:
            for col in ("logic_code", "model_code", "physical_code"):
                hit = conn.execute(
                    f"SELECT 1 FROM device_links WHERE {col} = ? LIMIT 1",
                    (code_v,)).fetchone()
                if hit:
                    found.append(col)
        return {"ok": True,
                "data": {"code": code_v, "valid": bool(found),
                         "found_in": found},
                "elapsed_ms": 0}
    if code == "SVC-WO-DETAIL":
        ent = {"model_code": params.get("model_code"),
               "base": params.get("base"),
               "period_start": params.get("period_start"),
               "period_end": params.get("period_end")}
        ent = {k: v for k, v in ent.items() if v}
        clause, fparams = entity_filter_clause("work_orders", ent)
        sql, sparams = _scoped(
            "SELECT code, device_code, model_code, base, plan_end, actual_end, "
            "status FROM work_orders WHERE 1=1 {dept_filter} " + clause +
            " ORDER BY plan_end DESC LIMIT 200",
            user, {"work_orders"})
        rows = [dict(r) for r in
                conn.execute(sql, sparams + fparams).fetchall()]
        return {"ok": True, "data": {"records": rows, "count": len(rows)},
                "elapsed_ms": 0}
    raise ServiceError(f"未知服务编码：{code}")


# ================= 指标图表数据（固定模板，非 LLM 生成） =================

def metric_chart_rows(conn, code: str, entities: dict, user,
                      dimension_kind: str | None) -> tuple:
    """返回 (columns, rows, dimension_kind)。固定聚合模板 + 行级过滤。"""
    start = entities.get("period_start")
    end = entities.get("period_end")
    if code == "WO_ON_TIME_RATE" and start and dimension_kind == "time":
        sql, params = _scoped(
            "SELECT substr(plan_end, 1, 7) AS 月份, COUNT(*) AS 工单数, "
            "SUM(CASE WHEN actual_end IS NOT NULL AND actual_end <= plan_end "
            "THEN 1 ELSE 0 END) AS 按期数 "
            "FROM work_orders WHERE cancel_flag = 0 "
            "AND plan_end >= ? AND plan_end < ? {dept_filter} "
            "GROUP BY substr(plan_end, 1, 7) ORDER BY 月份",
            user, {"work_orders"})
        rows = [dict(r) for r in
                conn.execute(sql, [start, _month_add(end, 1)] + params).fetchall()]
        for r in rows:
            r["按期完成率%"] = round(r["按期数"] / r["工单数"] * 100, 1) if r["工单数"] else 0
        return ["月份", "工单数", "按期数", "按期完成率%"], rows, "time"
    if code == "WO_ON_TIME_RATE" and dimension_kind == "category":
        sql, params = _scoped(
            "SELECT base AS 基地, COUNT(*) AS 工单数, "
            "SUM(CASE WHEN actual_end IS NOT NULL AND actual_end <= plan_end "
            "THEN 1 ELSE 0 END) AS 按期数 "
            "FROM work_orders WHERE cancel_flag = 0 "
            "AND plan_end >= ? AND plan_end < ? {dept_filter} "
            "GROUP BY base ORDER BY 基地",
            user, {"work_orders"})
        rows = [dict(r) for r in
                conn.execute(sql, [start, _month_add(end, 1)] + params).fetchall()]
        for r in rows:
            r["按期完成率%"] = round(r["按期数"] / r["工单数"] * 100, 1) if r["工单数"] else 0
        return ["基地", "工单数", "按期数", "按期完成率%"], rows, "category"
    if code == "MAT_COST_BY_MODEL" and start:
        sql, params = _scoped(
            "SELECT w.model_code AS 型号, COUNT(*) AS 领料笔数, "
            "ROUND(COALESCE(SUM(m.amount), 0), 2) AS 消耗金额 "
            "FROM material_issues m LEFT JOIN work_orders w "
            "ON w.code = m.wo_code "
            "WHERE m.issue_date >= ? AND m.issue_date < ? {dept_filter} "
            "GROUP BY w.model_code ORDER BY 消耗金额 DESC",
            user, {"material_issues", "work_orders"}, "m.")
        rows = [dict(r) for r in
                conn.execute(sql, [start, _month_add(end, 1)] + params).fetchall()]
        return ["型号", "领料笔数", "消耗金额"], rows, "category"
    return [], [], dimension_kind
