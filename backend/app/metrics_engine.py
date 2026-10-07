"""指标计算引擎：SQL 模板渲染 + 安全校验 + 结果缓存。

供指标路由（app/routers/metrics.py）与三期智能问数复用。
仅依赖 scope / utils / 标准库，不反向引用任何路由，避免循环 import。
原创实现。
"""
import hashlib
import re
from datetime import datetime

from .scope import is_super_admin
from .utils import parse_json


class MetricError(Exception):
    """指标计算错误，携带 HTTP 状态码。"""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# ---------- 安全校验（原创实现） ----------

# FROM / JOIN 之后允许出现的表（白名单）
_METRIC_TABLES = {
    "work_orders",
    "material_issues",
    "device_links",
    "md_records",
    "demo_device_ledger",
}

# 危险关键字（按词匹配，大小写不敏感）
_DANGEROUS_WORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "GRANT", "REPLACE", "PRAGMA", "ATTACH",
}


def _strip_sql_comments(sql: str) -> str:
    """去掉 SQL 中的行注释(-- ...) 与块注释(/* ... */)，防止校验被注释绕过。"""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n\r]*", " ", sql)
    return sql


def _validate_metric_sql(sql: str) -> None:
    """校验渲染后的指标 SQL。失败抛 MetricError(400)。"""
    s = _strip_sql_comments(sql).strip()
    if not s:
        raise MetricError(400, "SQL 为空")
    # 允许末尾恰好一个分号；其余位置出现分号视为多语句
    body = s[:-1].strip() if s.endswith(";") else s
    if ";" in body:
        raise MetricError(400, "只允许单条 SQL 语句")
    first = re.match(r"[A-Za-z]+", body)
    if first is None or first.group(0).upper() not in ("SELECT", "WITH"):
        raise MetricError(400, "只允许 SELECT / WITH 开头的查询语句")
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", body.upper()))
    hit = sorted(words & _DANGEROUS_WORDS)
    if hit:
        raise MetricError(400, "SQL 含危险关键字: " + ", ".join(hit))
    tables = {
        m.lower()
        for m in re.findall(
            r"(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", body, flags=re.IGNORECASE
        )
    }
    unknown = sorted(tables - _METRIC_TABLES)
    if unknown:
        raise MetricError(400, "FROM/JOIN 表不在白名单内: " + ", ".join(unknown))


# ---------- 模板渲染 ----------

# 占位符：带引号的日期占位符先匹配，避免把引号留在 SQL 里。
# {dept_filter} 支持可选别名后缀 {dept_filter:m}（JOIN 查询中消除歧义用）；
# 无后缀时行为与 scope.apply_scope 完全一致。
_PLACEHOLDER_RE = re.compile(
    r"'\{period_start\}'|'\{period_end\}'"
    r"|\{period_start\}|\{period_end\}"
    r"|\{dept_filter(?::[A-Za-z_][A-Za-z0-9_]*)?\}|\{dimension_filter\}"
)

_DEPT_FILTER_RE = re.compile(r"\{dept_filter(?::([A-Za-z_][A-Za-z0-9_]*))?\}")


def _render_template(template: str, indicator: dict, user,
                     period_start: str, period_end: str,
                     dimension, dimension_value) -> tuple:
    """按出现顺序替换占位符，返回 (sql, params)。

    - {period_start}/{period_end}（含引号形式）→ ? 参数
    - {dept_filter} → 与 scope.apply_scope 同语义：super_admin 替换为空，
      否则替换为 "AND dept = ?" 并追加 user["dept"]；
      另支持 {dept_filter:别名} 形式（如 {dept_filter:m} → "AND m.dept = ?"），
      供 JOIN 多表（两表都有 dept 列）时消除歧义
    - {dimension_filter} → dimension 与 dimension_value 均给出时替换为
      "AND <expr> = ?"（expr 取自 indicators.dimensions 按 name 匹配），否则为空
    """
    dims = parse_json(indicator.get("dimensions"), [])
    dim_expr = None
    if dimension and dimension_value:
        for d in dims:
            if isinstance(d, dict) and d.get("name") == dimension:
                dim_expr = d.get("expr")
                break
        if not dim_expr:
            raise MetricError(400, f"维度 {dimension} 未在指标中定义")

    params: list = []
    out: list = []
    pos = 0
    for m in _PLACEHOLDER_RE.finditer(template):
        out.append(template[pos:m.start()])
        tok = m.group(0)
        if tok in ("'{period_start}'", "{period_start}"):
            out.append("?")
            params.append(period_start)
        elif tok in ("'{period_end}'", "{period_end}"):
            out.append("?")
            params.append(period_end)
        elif _DEPT_FILTER_RE.fullmatch(tok):
            alias = _DEPT_FILTER_RE.fullmatch(tok).group(1)
            col = f"{alias}.dept" if alias else "dept"
            if user is None or is_super_admin(user):
                out.append("")
            else:
                out.append(f"AND {col} = ?")
                params.append(user["dept"])
        elif tok == "{dimension_filter}":
            if dim_expr:
                out.append(f"AND {dim_expr} = ?")
                params.append(dimension_value)
            else:
                out.append("")
        pos = m.end()
    out.append(template[pos:])
    return "".join(out), params


def _scalar(conn, sql: str, params: list):
    """执行 SQL 取第一行第一列，转 float（NULL 保持 None）。"""
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    # _Row 按值迭代，第一列即第一个值
    v = next(iter(row))
    return None if v is None else float(v)


def _params_hash(code, version, period_start, period_end, dimension,
                dimension_value, dept_scope="") -> str:
    # 注意：缓存键在任务规格的公式基础上追加了 dept_scope。
    # 规格原公式不含数据范围，会导致不同部门命中同一缓存行、
    # 把甲部门的聚合结果返回给乙部门（数据范围泄漏），故修正。
    raw = (f"{code}|{version}|{period_start}|{period_end}|"
           f"{dimension}|{dimension_value}|{dept_scope}")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ---------- 主入口 ----------

def compute_metric(conn, code: str, period_start: str, period_end: str,
                   dimension=None, dimension_value=None, user=None) -> dict:
    """计算指标。

    流程：查指标（须已发布）→ 渲染 numerator/denominator 模板 → 安全校验 →
    执行取数 → 查 indicator_results 缓存（命中直接返回）→ 未命中则写入缓存。
    失败抛 MetricError。
    """
    ind = conn.execute(
        "SELECT * FROM indicators WHERE code = ?", (code,)
    ).fetchone()
    if ind is None:
        raise MetricError(404, f"指标 {code} 不存在")
    ind = dict(ind)
    if ind.get("status") != "已发布":
        raise MetricError(400, f"指标 {code} 未发布（当前状态：{ind.get('status')}）")

    rule = parse_json(ind.get("calc_rule"), {})
    num_tpl = (rule.get("numerator_sql") or "").strip()
    den_tpl = (rule.get("denominator_sql") or "").strip()
    if not num_tpl or not den_tpl:
        raise MetricError(400, "calc_rule 缺少 numerator_sql/denominator_sql")

    num_sql, num_params = _render_template(
        num_tpl, ind, user, period_start, period_end, dimension, dimension_value)
    den_sql, den_params = _render_template(
        den_tpl, ind, user, period_start, period_end, dimension, dimension_value)
    _validate_metric_sql(num_sql)
    _validate_metric_sql(den_sql)

    numerator = _scalar(conn, num_sql, num_params)
    denominator = _scalar(conn, den_sql, den_params)
    if denominator is None or denominator == 0:
        value = None
    elif numerator is None:
        value = None
    else:
        value = numerator / denominator

    version = ind.get("version") or ""
    period = f"{period_start}~{period_end}"
    # 数据范围纳入缓存键：super_admin/未登录用户用空范围
    dept_scope = ""
    if user is not None and not is_super_admin(user):
        dept_scope = user["dept"] or ""
    phash = _params_hash(code, version, period_start, period_end,
                         dimension, dimension_value, dept_scope)

    hit = conn.execute(
        """SELECT * FROM indicator_results
           WHERE indicator_id = ? AND version = ? AND params_hash = ?""",
        (ind["id"], version, phash),
    ).fetchone()
    if hit is not None:
        hit = dict(hit)
        return {
            "value": hit["value"],
            "numerator": hit["numerator"],
            "denominator": hit["denominator"],
            "version": hit["version"],
            "period": hit["period"],
            "cached": True,
            "computed_at": hit["computed_at"],
        }

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO indicator_results
           (indicator_id, version, params_hash, dimension, period,
            value, numerator, denominator, computed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ind["id"], version, phash, dimension, period,
         value, numerator, denominator, now),
    )
    conn.commit()
    return {
        "value": value,
        "numerator": numerator,
        "denominator": denominator,
        "version": version,
        "period": period,
        "cached": False,
        "computed_at": now,
    }
