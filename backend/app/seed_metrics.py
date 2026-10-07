"""数治通三期试点数据 + 种子指标：核电设备维修场景。

- 幂等：work_orders 已有数据则跳过试点数据（工单/领料）；指标按 code upsert。
- 试点数据覆盖 2025-11 ~ 2026-10 近一年。
原创实现。
"""
import json
from datetime import datetime

from .database import get_conn

MONTHS = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13)
          if not (y == 2025 and m < 11) and not (y == 2026 and m > 10)]

TITLES = ["辅助给水泵定期检修", "辅助给水泵月度点检",
          "辅助给水泵润滑保养", "辅助给水泵振动检测"]

DEVICES = ["P-AFW-001A", "P-AFW-001B"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _build_work_orders() -> list:
    rows = []
    for mi, m in enumerate(MONTHS):
        for seq, dev in enumerate(DEVICES, start=1):
            rows.append({
                "code": f"WO-{m}-0{seq}",
                "device_code": dev,
                "model_code": "AFW-1000",
                "base": "一号基地",
                "dept": "设备部",
                "title": TITLES[(mi + seq) % len(TITLES)],
                "plan_start": f"{m}-05",
                "plan_end": f"{m}-20",
                "actual_end": f"{m}-18",
                "delay_approved": 0,
                "cancel_flag": 0,
                "status": "已完成",
            })
    # 特殊行覆盖
    overrides = {
        "WO-2026-03-01": {"actual_end": "2026-03-25"},              # 超期5天
        "WO-2026-06-02": {"actual_end": "2026-07-10"},              # 超期20天
        "WO-2026-08-01": {"delay_approved": 1,                      # 超期8天+审批通过
                          "actual_end": "2026-08-28"},
        "WO-2026-04-01": {"cancel_flag": 1, "status": "已取消",
                          "actual_end": None},                       # 取消
        "WO-2026-09-02": {"cancel_flag": 1, "status": "已取消",
                          "actual_end": None},                       # 取消
        "WO-2026-09-01": {"status": "进行中", "actual_end": None,
                          "plan_end": "2026-09-25"},                 # 进行中
        "WO-2026-10-02": {"status": "进行中", "actual_end": None,
                          "plan_end": "2026-10-25"},                 # 进行中
        "WO-2026-01-01": {"base": "二号基地"},
        "WO-2026-07-02": {"base": "二号基地"},
        "WO-2026-02-01": {"dept": "维修处"},                        # 数据范围测试
        "WO-2026-05-02": {"dept": "维修处"},                        # 数据范围测试
    }
    for r in rows:
        if r["code"] in overrides:
            r.update(overrides[r["code"]])
    # 额外 2 行，凑 26 行
    rows.append({
        "code": "WO-2026-05-03", "device_code": "P-AFW-001A",
        "model_code": "AFW-1000", "base": "一号基地", "dept": "设备部",
        "title": "辅助给水泵密封更换", "plan_start": "2026-05-05",
        "plan_end": "2026-05-20", "actual_end": "2026-05-17",
        "delay_approved": 0, "cancel_flag": 0, "status": "已完成",
    })
    rows.append({
        "code": "WO-2026-10-03", "device_code": "P-AFW-001B",
        "model_code": "AFW-1000", "base": "一号基地", "dept": "设备部",
        "title": "辅助给水泵年度大修", "plan_start": "2026-10-05",
        "plan_end": "2026-10-20", "actual_end": "2026-10-18",
        "delay_approved": 0, "cancel_flag": 0, "status": "已完成",
    })
    return rows


def _build_material_issues(work_orders: list) -> list:
    rows = []
    for wo in work_orders:
        if wo["cancel_flag"] or not wo["actual_end"]:
            continue
        m = wo["actual_end"][:7]
        base = {"wo_code": wo["code"], "dept": wo["dept"]}
        rows.append({**base, "material_code": "MAT-SEAL-001",
                     "material_name": "机械密封", "qty": 2,
                     "amount": 1700.0, "issue_date": f"{m}-12"})
        rows.append({**base, "material_code": "MAT-BRG-002",
                     "material_name": "轴承", "qty": 1,
                     "amount": 1200.0, "issue_date": f"{m}-16"})
    # 2 行退料（负金额）：给 MAT_COST v2 口径差异用
    for r in rows:
        if r["wo_code"] == "WO-2026-06-01" and r["material_code"] == "MAT-SEAL-001":
            r.update({"qty": -2, "amount": -1700.0,
                      "material_name": "机械密封（退料）"})
        if r["wo_code"] == "WO-2026-03-02" and r["material_code"] == "MAT-BRG-002":
            r.update({"qty": -1, "amount": -1200.0,
                      "material_name": "轴承（退料）"})
    return rows


def _seed_pilot_data(conn) -> None:
    if conn.execute("SELECT COUNT(*) c FROM work_orders").fetchone()["c"] > 0:
        return  # 幂等：已有工单数据则跳过试点数据
    now = _now()
    wos = _build_work_orders()
    cur = conn.cursor()
    for w in wos:
        cur.execute(
            """INSERT INTO work_orders
               (code, device_code, model_code, base, dept, title,
                plan_start, plan_end, actual_end,
                delay_approved, cancel_flag, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (w["code"], w["device_code"], w["model_code"], w["base"], w["dept"],
             w["title"], w["plan_start"], w["plan_end"], w["actual_end"],
             w["delay_approved"], w["cancel_flag"], w["status"], now),
        )
    for mi in _build_material_issues(wos):
        cur.execute(
            """INSERT INTO material_issues
               (wo_code, material_code, material_name, qty, amount,
                issue_date, dept)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (mi["wo_code"], mi["material_code"], mi["material_name"],
             mi["qty"], mi["amount"], mi["issue_date"], mi["dept"]),
        )
    conn.commit()


def _seed_device_links(conn) -> None:
    for i, phys in enumerate(["P-AFW-001A", "P-AFW-001B", "P-AFW-002A"], start=1):
        if conn.execute(
            "SELECT 1 FROM device_links WHERE physical_code = ?", (phys,)
        ).fetchone() is None:
            conn.execute(
                """INSERT INTO device_links
                   (logic_code, model_code, physical_code,
                    effective_from, effective_to, status, created_at)
                   VALUES (?, ?, ?, ?, NULL, '有效', ?)""",
                (f"L-AFW-{i:03d}", "AFW-1000", phys, "2025-01-01", _now()),
            )
    conn.commit()


# ---------- 种子指标定义 ----------

_WO_V1_NUM = (
    "SELECT COUNT(*) FROM work_orders WHERE 1=1 {dept_filter} "
    "AND cancel_flag=0 AND actual_end IS NOT NULL "
    "AND substr(actual_end,1,7)>='{period_start}' "
    "AND substr(actual_end,1,7)<='{period_end}' AND actual_end<=plan_end"
)
_WO_V1_DEN = (
    "SELECT COUNT(*) FROM work_orders WHERE 1=1 {dept_filter} "
    "AND cancel_flag=0 AND actual_end IS NOT NULL "
    "AND substr(actual_end,1,7)>='{period_start}' "
    "AND substr(actual_end,1,7)<='{period_end}'"
)
_WO_V2_NUM = (
    "SELECT COUNT(*) FROM work_orders WHERE 1=1 {dept_filter} "
    "AND cancel_flag=0 AND actual_end IS NOT NULL "
    "AND substr(actual_end,1,7)>='{period_start}' "
    "AND substr(actual_end,1,7)<='{period_end}' "
    "AND (actual_end<=plan_end OR delay_approved=1)"
)

_MAT_V1_NUM = (
    "SELECT COALESCE(SUM(m.amount),0) FROM material_issues m "
    "JOIN work_orders w ON m.wo_code=w.code WHERE 1=1 {dept_filter:m} "
    "{dimension_filter} "
    "AND substr(m.issue_date,1,7)>='{period_start}' "
    "AND substr(m.issue_date,1,7)<='{period_end}'"
)
_MAT_V2_NUM = (
    "SELECT COALESCE(SUM(m.amount),0) FROM material_issues m "
    "JOIN work_orders w ON m.wo_code=w.code WHERE 1=1 {dept_filter:m} "
    "{dimension_filter} AND m.amount>=0 "
    "AND substr(m.issue_date,1,7)>='{period_start}' "
    "AND substr(m.issue_date,1,7)<='{period_end}'"
)

_EQ_NUM = (
    "SELECT COUNT(*) FROM (SELECT DISTINCT physical_code FROM device_links "
    "WHERE status='有效' AND physical_code NOT IN "
    "(SELECT DISTINCT device_code FROM work_orders WHERE 1=1 {dept_filter} "
    "AND cancel_flag=0 "
    "AND substr(COALESCE(actual_end,plan_end),1,7)>='{period_start}' "
    "AND substr(COALESCE(actual_end,plan_end),1,7)<='{period_end}'))"
)
_EQ_DEN = ("SELECT COUNT(DISTINCT physical_code) FROM device_links "
           "WHERE status='有效'")


def _seed_indicator_defs() -> list:
    return [
        {
            "code": "WO_ON_TIME_RATE",
            "name": "维修工单按期完成率",
            "biz_def": "统计周期内按期完成的维修工单占比",
            "scope_include": "纳入统计周期内实际完工的维修工单（排除取消）",
            "scope_exclude": "已取消工单、未完工（进行中）工单",
            "time_rule": "完成时间",
            "granularity": "工单",
            "dimensions": [{"name": "model_code", "expr": "model_code"}],
            "data_sources": ["work_orders"],
            "owner_dept": "设备部",
            "owner_role": "设备管理",
            "versions": [
                ("v1.0",
                 {"numerator_sql": _WO_V1_NUM, "denominator_sql": _WO_V1_DEN,
                  "description": "v1.0 口径：按期 = 实际完成日期 <= 计划完成日期；"
                                 "延期审批不计入按期。"},
                 "初始版本"),
                ("v2.0",
                 {"numerator_sql": _WO_V2_NUM, "denominator_sql": _WO_V1_DEN,
                  "description": "v2.0 口径：延期审批通过的工单"
                                 "（delay_approved=1）视为按期完成。"},
                 "v2.0 口径变更：延期审批通过的工单视为按期"
                 "（v1.0 仅按 actual_end<=plan_end 判定）"),
            ],
        },
        {
            "code": "EQ_INTACT_RATE",
            "name": "设备完好率",
            "biz_def": "统计时点设备台账中完好设备的占比",
            "scope_include": "设备台账中状态有效的设备",
            "scope_exclude": "台账中状态失效/退役的设备",
            "time_rule": "统计时点",
            "granularity": "设备",
            "dimensions": [],
            "data_sources": ["device_links", "work_orders"],
            "owner_dept": "设备部",
            "owner_role": "设备管理",
            "versions": [
                ("v1.0",
                 {"numerator_sql": _EQ_NUM, "denominator_sql": _EQ_DEN,
                  "description": "分子=台账有效设备中统计周期内无维修工单的设备数；"
                                 "分母=台账有效设备总数。注意 device_links 无 dept 列，"
                                 "数据范围占位符只出现在 work_orders 子查询内。"},
                 "初始版本"),
            ],
        },
        {
            "code": "MAT_COST_BY_MODEL",
            "name": "备件消耗金额（按型号）",
            "biz_def": "统计周期内各型号设备的备件消耗金额",
            "scope_include": "纳入统计周期内各工单的领料记录",
            "scope_exclude": "无工单关联的领料记录",
            "time_rule": "领料时间",
            "granularity": "型号",
            "dimensions": [{"name": "model_code", "expr": "w.model_code"}],
            "data_sources": ["material_issues", "work_orders"],
            "owner_dept": "设备部",
            "owner_role": "物资管理",
            "versions": [
                ("v1.0",
                 {"numerator_sql": _MAT_V1_NUM, "denominator_sql": "SELECT 1",
                  "description": "v1.0 口径：金额含退料（负金额）；"
                                 "金额类指标分母为 1，指标值即金额。"},
                 "初始版本"),
                ("v2.0",
                 {"numerator_sql": _MAT_V2_NUM, "denominator_sql": "SELECT 1",
                  "description": "v2.0 口径：剔除退料（金额为负）。"},
                 "v2.0 口径变更：剔除退料（金额为负）"),
            ],
        },
    ]


def _upsert_indicator(conn, d: dict) -> None:
    now = _now()
    latest_version = d["versions"][-1][0]
    existing = conn.execute(
        "SELECT id FROM indicators WHERE code = ?", (d["code"],)
    ).fetchone()
    if existing is None:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO indicators
               (name, code, biz_def, calc_rule, scope_include, scope_exclude,
                time_rule, granularity, dimensions, data_sources,
                owner_dept, owner_role, version, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '已发布', ?)""",
            (d["name"], d["code"], d["biz_def"],
             json.dumps(d["versions"][-1][1], ensure_ascii=False),
             d["scope_include"], d["scope_exclude"], d["time_rule"],
             d["granularity"],
             json.dumps(d["dimensions"], ensure_ascii=False),
             json.dumps(d["data_sources"], ensure_ascii=False),
             d["owner_dept"], d["owner_role"], latest_version, now),
        )
        indicator_id = cur.lastrowid
    else:
        indicator_id = existing["id"]
        conn.execute(
            """UPDATE indicators
               SET name = ?, biz_def = ?, calc_rule = ?, scope_include = ?,
                   scope_exclude = ?, time_rule = ?, granularity = ?,
                   dimensions = ?, data_sources = ?, owner_dept = ?,
                   owner_role = ?, version = ?
               WHERE id = ?""",
            (d["name"], d["biz_def"],
             json.dumps(d["versions"][-1][1], ensure_ascii=False),
             d["scope_include"], d["scope_exclude"], d["time_rule"],
             d["granularity"],
             json.dumps(d["dimensions"], ensure_ascii=False),
             json.dumps(d["data_sources"], ensure_ascii=False),
             d["owner_dept"], d["owner_role"], latest_version, indicator_id),
        )
    for version, calc_rule, change_desc in d["versions"]:
        if conn.execute(
            """SELECT 1 FROM indicator_versions
               WHERE indicator_id = ? AND version = ?""",
            (indicator_id, version),
        ).fetchone() is None:
            snapshot = {
                "code": d["code"], "name": d["name"],
                "biz_def": d["biz_def"], "calc_rule": calc_rule,
                "scope_include": d["scope_include"],
                "scope_exclude": d["scope_exclude"],
                "time_rule": d["time_rule"], "granularity": d["granularity"],
                "dimensions": d["dimensions"],
                "data_sources": d["data_sources"],
                "owner_dept": d["owner_dept"], "owner_role": d["owner_role"],
                "formula_desc": "",
            }
            conn.execute(
                """INSERT INTO indicator_versions
                   (indicator_id, version, snapshot, change_desc, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (indicator_id, version,
                 json.dumps(snapshot, ensure_ascii=False),
                 change_desc, now),
            )
    conn.commit()


def seed_metrics() -> None:
    """灌入三期试点数据与种子指标（幂等）。"""
    conn = get_conn()
    try:
        _seed_pilot_data(conn)
        _seed_device_links(conn)
        for d in _seed_indicator_defs():
            _upsert_indicator(conn, d)
    finally:
        conn.close()
