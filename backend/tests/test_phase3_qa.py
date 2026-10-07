"""数治通三期智能问数测试：TestClient + 独立测试库。原创。"""
import os
import tempfile
from datetime import date

# 必须在 import app 之前指定测试库路径
_tmp = tempfile.mkdtemp(prefix="szt_test_phase3_qa_")
os.environ["SZT_DB_PATH"] = os.path.join(_tmp, "test.db")

import pytest
from fastapi.testclient import TestClient

from app.database import get_conn
from app.deps import now_str
from app.main import app
from app.qa_engine import (
    MOCKED_ENGINES,
    build_template_sql,
    detect_chart_type,
    detect_intent,
    extract_entities,
    validate_select_sql,
)

# main.py 按约束不改动，此处在测试进程内注册 qa 路由做联调
from app.routers import qa as qa_router  # noqa: E402

app.include_router(qa_router.router)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def tokens(client):
    out = {}
    for username, password in [
        ("admin", "Admin@123"),
        ("weixiu", "Weixiu@123"),
        ("audit", "Audit@123"),
    ]:
        r = client.post("/api/auth/login",
                        json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        out[username] = r.json()["token"]
    return out


def H(token):
    return {"Authorization": f"Bearer {token}"}


def _ym(offset: int) -> str:
    """距今 offset 个月的 YYYY-MM（offset<=0 为过去）"""
    t = date.today()
    m = t.year * 12 + t.month - 1 + offset
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


@pytest.fixture(scope="module")
def qa_seed(client):
    """问数试点表种子：日期相对今天动态生成，保证落在“近一年”内。

    同时补齐 metrics_engine / services_engine 真实计算所需的
    indicators（code + 已发布 + calc_rule）与 services（code + 已发布 + 公开）。
    """
    import json as _json

    conn = get_conn()
    try:
        if not conn.execute(
                "SELECT COUNT(*) c FROM work_orders").fetchone()["c"]:
            now = now_str()
            wos = [
                # code, device_code, model, base, dept, plan, actual, cancel, status
                ("WO-2026-001", "P-AFW-001", "AFW-1000", "一号基地", "维修处",
                 f"{_ym(-1)}-10", f"{_ym(-1)}-09", 0, "已完成"),
                ("WO-2026-002", "P-AFW-001", "AFW-1000", "一号基地", "维修处",
                 f"{_ym(-2)}-15", f"{_ym(-2)}-20", 0, "已完成"),
                ("WO-2026-003", "P-AFW-003", "AFW-2000", "二号基地", "维修处",
                 f"{_ym(-3)}-01", None, 0, "执行中"),
                ("WO-2026-004", "P-AFW-001", "AFW-1000", "一号基地", "维修处",
                 f"{_ym(-4)}-01", f"{_ym(-4)}-02", 1, "已取消"),
                ("WO-2026-005", "P-AFW-002", "AFW-1000", "一号基地", "设备部",
                 f"{_ym(-1)}-20", f"{_ym(-1)}-19", 0, "已完成"),
                ("WO-2026-006", "P-AFW-003", "AFW-2000", "二号基地", "设备部",
                 f"{_ym(-5)}-10", f"{_ym(-5)}-10", 0, "已完成"),
            ]
            for w in wos:
                conn.execute(
                    """INSERT INTO work_orders
                       (code, device_code, model_code, base, dept, plan_end,
                        actual_end, cancel_flag, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (w[0], w[1], w[2], w[3], w[4], w[5], w[6], w[7], w[8], now),
                )
            mis = [
                # wo_code, material_code, name, qty, amount, issue_date, dept
                ("WO-2026-001", "M-AFW-PUMP", "给水泵备件", 2, 12000.50,
                 f"{_ym(-1)}-05", "维修处"),
                ("WO-2026-005", "M-AFW-VALVE", "阀门备件", 1, 8000.00,
                 f"{_ym(-1)}-18", "设备部"),
                ("WO-2026-002", "M-AFW-PUMP", "给水泵备件", 1, -1200.00,
                 f"{_ym(-2)}-16", "维修处"),
            ]
            for m in mis:
                conn.execute(
                    """INSERT INTO material_issues
                       (wo_code, material_code, material_name, qty, amount,
                        issue_date, dept)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    m,
                )
            for logic, model, phys in [
                ("L-AFW-001", "AFW-1000", "P-AFW-001"),
                ("L-AFW-002", "AFW-1000", "P-AFW-002"),
                ("L-AFW-003", "AFW-2000", "P-AFW-003"),
            ]:
                conn.execute(
                    """INSERT INTO device_links
                       (logic_code, model_code, physical_code, effective_from,
                        status, created_at)
                       VALUES (?, ?, ?, ?, '有效', ?)""",
                    (logic, model, phys, f"{_ym(-11)}-01", now),
                )

        # ---------- 指标定义（metrics_engine 真实计算） ----------
        now = now_str()
        obj = {r["code"]: r["id"] for r in
               conn.execute("SELECT code, id FROM biz_objects").fetchall()}
        wo_base = ("substr(plan_end, 1, 7) >= {period_start} "
                   "AND substr(plan_end, 1, 7) <= {period_end} "
                   "{dept_filter} {dimension_filter}")
        ind_defs = [
            {"code": "WO_ON_TIME_RATE", "name": "维修工单按期完成率",
             "object_id": obj.get("WO"),
             "biz_def": "维修工单按期完成率 = 按期完工工单数 ÷ 计划完成工单总数；"
                        "取消单不纳入统计",
             "time_rule": "按计划完成日期归属统计期",
             "dimensions": [{"name": "model_code", "expr": "model_code"}],
             "calc_rule": {
                 "numerator_sql":
                     "SELECT COUNT(*) FROM work_orders WHERE cancel_flag = 0 "
                     "AND actual_end IS NOT NULL AND actual_end <= plan_end "
                     f"AND {wo_base}",
                 "denominator_sql":
                     "SELECT COUNT(*) FROM work_orders WHERE cancel_flag = 0 "
                     f"AND {wo_base}",
             }},
            {"code": "EQ_INTACT_RATE", "name": "设备完好率",
             "object_id": obj.get("P-EQ"),
             "biz_def": "设备完好率 = 完好设备数 ÷ 设备总数",
             "time_rule": "按统计时点口径",
             "dimensions": [],
             "calc_rule": {
                 "numerator_sql":
                     "SELECT COUNT(DISTINCT physical_code) FROM device_links "
                     "WHERE status = '有效'",
                 "denominator_sql":
                     "SELECT COUNT(DISTINCT physical_code) FROM device_links",
             }},
            {"code": "MAT_COST_BY_MODEL", "name": "备件消耗金额",
             "object_id": obj.get("MAT"),
             "biz_def": "备件消耗金额 = 备件领料金额合计（退料金额为负数冲减）",
             "time_rule": "按领料日期归属统计期",
             "dimensions": [],
             "calc_rule": {
                 "numerator_sql":
                     "SELECT COALESCE(SUM(amount), 0) FROM material_issues "
                     "WHERE substr(issue_date, 1, 7) >= {period_start} "
                     "AND substr(issue_date, 1, 7) <= {period_end} {dept_filter}",
                 "denominator_sql": "SELECT 1",
             }},
        ]
        for d in ind_defs:
            if conn.execute("SELECT 1 FROM indicators WHERE code = ?",
                            (d["code"],)).fetchone():
                continue
            conn.execute(
                """INSERT INTO indicators
                   (code, name, object_id, biz_def, calc_rule, time_rule,
                    dimensions, version, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'v1.0', '已发布', ?)""",
                (d["code"], d["name"], d["object_id"], d["biz_def"],
                 _json.dumps(d["calc_rule"], ensure_ascii=False),
                 d["time_rule"],
                 _json.dumps(d["dimensions"], ensure_ascii=False), now),
            )

        # ---------- 服务定义（services_engine 真实调用，公开免订阅） ----------
        for code, name in [
            ("SVC-REL-3CODE", "设备三码关系查询服务"),
            ("SVC-WO-DETAIL", "工单明细查询服务"),
            ("SVC-CODE-VALIDATE", "设备编码校验服务"),
        ]:
            if conn.execute("SELECT 1 FROM services WHERE code = ?",
                            (code,)).fetchone():
                continue
            conn.execute(
                """INSERT INTO services
                   (name, code, version, status, permission_req, created_at)
                   VALUES (?, ?, 'v1.0', '已发布', '公开', ?)""",
                (name, code, now),
            )
        conn.commit()
    finally:
        conn.close()


def ask(client, token, question, chart="auto"):
    return client.post("/api/qa/ask", json={"question": question, "chart": chart},
                       headers=H(token))


# ---------- 引擎单元测试 ----------

def test_01_validate_select_sql():
    ok, _ = validate_select_sql(
        "SELECT code FROM work_orders WHERE 1=1 {dept_filter} LIMIT 200")
    assert ok
    ok, reason = validate_select_sql(
        "SELECT * FROM work_orders; DROP TABLE work_orders")
    assert not ok and "分号" in reason
    ok, reason = validate_select_sql(
        "SELECT * FROM work_orders WHERE code='x' OR '1'='1' -- comment")
    assert ok  # 注释被剥离后仍是合法单条 SELECT
    ok, reason = validate_select_sql("DELETE FROM work_orders")
    assert not ok
    ok, reason = validate_select_sql("SELECT * FROM users")
    assert not ok and "白名单" in reason
    ok, _ = validate_select_sql(
        "WITH a AS (SELECT 1 AS x) SELECT x FROM a JOIN work_orders ON 1=1")
    assert ok  # CTE 别名不计入外部表


def test_02_detect_intent_and_entities():
    assert detect_intent("近一年维修工单按期完成率是多少")["code"] == "WO_ON_TIME_RATE"
    assert detect_intent("设备完好率")["code"] == "EQ_INTACT_RATE"
    assert detect_intent("查询设备三码关系")["code"] == "SVC-REL-3CODE"
    assert detect_intent("工单明细")["code"] == "SVC-WO-DETAIL"
    assert detect_intent("备件消耗金额")["code"] == "MAT_COST_BY_MODEL"
    assert detect_intent("查询备件领料明细")["kind"] == "sql"
    assert detect_intent("今天天气怎么样")["kind"] == "refuse"
    ent = extract_entities("近一年AFW-1000一号基地维修工单按期完成率")
    assert ent["period_start"] and ent["period_end"]
    assert ent["model_code"] == "AFW-1000"
    assert ent["base"] == "一号基地"
    ent2 = extract_entities("2026年1月工单明细")
    assert ent2["period_start"] == "2026-01" and ent2["period_end"] == "2026-01"
    assert detect_chart_type("按月趋势", ["月份", "完成率"], "time") == "line"
    assert detect_chart_type("各型号对比", ["型号", "金额"], "category") == "bar"
    assert detect_chart_type("占比构成", ["x", "y"], None) == "pie"
    assert detect_chart_type("是多少", ["指标", "数值"], "stat") == "stat"
    assert build_template_sql({"kind": "sql", "target": "work_orders"}, {})


# ---------- 问数主流程 ----------

def test_03_metric_success_five_elements(client, tokens, qa_seed):
    r = ask(client, tokens["admin"], "近一年维修工单按期完成率是多少")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "success"
    # 五要素齐全
    for k in ("understanding", "scope", "interpretation", "sources",
              "follow_ups"):
        assert d[k], k
    assert d["understanding"]["intent"] == "metric"
    assert d["understanding"]["target"] == "WO_ON_TIME_RATE"
    assert "按期完成率" in d["interpretation"]
    assert d["scope"]["caliber"] and d["scope"]["time"]
    assert d["chart"]["chart_type"] == "stat"
    assert d["via"] == "metric"
    assert d["elapsed_ms"] >= 0
    assert d["is_favorite"] is False
    assert d["id"]


def test_04_metric_need_clarify(client, tokens, qa_seed):
    r = ask(client, tokens["admin"], "工单完成率")
    d = r.json()
    assert d["status"] == "need_clarify"
    assert d["clarify_questions"]
    assert "时间范围" in d["clarify_questions"][0]


def test_05_refused_out_of_scope(client, tokens, qa_seed):
    r = ask(client, tokens["admin"], "今天天气怎么样")
    d = r.json()
    assert d["status"] == "refused"
    assert "超出口径范围" in d["error"]
    assert d["follow_ups"]


def test_06_injection_blocked_and_table_survives(client, tokens, qa_seed):
    conn = get_conn()
    try:
        n_before = conn.execute(
            "SELECT COUNT(*) c FROM work_orders").fetchone()["c"]
    finally:
        conn.close()
    assert n_before > 0
    r = ask(client, tokens["admin"], "工单明细; DROP TABLE work_orders")
    d = r.json()
    assert d["status"] in ("refused", "error")
    conn = get_conn()
    try:
        n_after = conn.execute(
            "SELECT COUNT(*) c FROM work_orders").fetchone()["c"]
        assert n_after == n_before  # 注入未破坏表数据
    finally:
        conn.close()


def test_07_scope_weixiu_sees_less_than_admin(client, tokens, qa_seed):
    ra = ask(client, tokens["admin"], "工单明细")
    rw = ask(client, tokens["weixiu"], "工单明细")
    assert ra.json()["status"] == "success"
    # 工单明细服务是"授权"类：weixiu 未订阅 → 越权被拒（权限可验证）
    assert rw.json()["status"] == "error"
    assert "授权" in (rw.json().get("error") or "")
    # SQL 意图走行级部门过滤：维修处只能看到本部门工单
    ra2 = ask(client, tokens["admin"], "查询全部工单")
    rw2 = ask(client, tokens["weixiu"], "查询全部工单")
    assert ra2.json()["via"] == "sql"
    assert ra2.json()["status"] == "success"
    assert rw2.json()["status"] == "success"
    conn = get_conn()
    try:
        expect_w = conn.execute(
            "SELECT COUNT(*) c FROM work_orders WHERE dept='维修处'"
        ).fetchone()["c"]
        expect_a = conn.execute(
            "SELECT COUNT(*) c FROM work_orders").fetchone()["c"]
    finally:
        conn.close()
    assert rw2.json()["row_count"] == expect_w
    assert ra2.json()["row_count"] == expect_a
    assert rw2.json()["row_count"] < ra2.json()["row_count"]


def test_08_service_three_code_with_assumption(client, tokens, qa_seed):
    r = ask(client, tokens["admin"], "查询设备三码关系")
    d = r.json()
    assert d["status"] == "success"
    assert d["via"] == "service"
    assert d["row_count"] >= 1
    assert any("logic_code" in c for c in d["columns"])
    # 未指定逻辑编码 → 默认 L-AFW-001 并注明假设
    assert "assumption" in d["understanding"]
    assert "L-AFW-001" in d["understanding"]["assumption"]


def test_08b_service_code_validate(client, tokens, qa_seed):
    # 带标准编码 → 真实走 SVC-CODE-VALIDATE
    r = ask(client, tokens["admin"], "按 STD-002 校验 P-AFW-001 编码")
    d = r.json()
    assert d["status"] == "success", d
    assert d["via"] == "service"
    assert "校验" in d["interpretation"]
    assert "STD-002" in d["interpretation"]
    # 缺标准编码 → need_clarify
    r = ask(client, tokens["admin"], "校验 P-AFW-001 编码是否有效")
    assert r.json()["status"] == "need_clarify"


def test_09_sql_material_issues(client, tokens, qa_seed):
    r = ask(client, tokens["admin"], "查询备件领料明细")
    d = r.json()
    assert d["status"] == "success"
    assert d["via"] == "sql"
    assert d["sql"] and "material_issues" in d["sql"]
    ok, _ = validate_select_sql(d["sql"])
    assert ok
    conn = get_conn()
    try:
        expect = conn.execute(
            "SELECT COUNT(*) c FROM material_issues").fetchone()["c"]
    finally:
        conn.close()
    assert d["row_count"] == expect and expect > 0


def test_10_quality_note_excludes_cancelled(client, tokens, qa_seed):
    r = ask(client, tokens["admin"], "近一年维修工单按期完成率是多少")
    d = r.json()
    assert "取消单" in d["quality_note"]
    assert "work_orders" in d["quality_note"]


# ---------- 历史 / 收藏 / 重跑 / 删除 ----------

def test_11_favorite_toggle(client, tokens, qa_seed):
    hid = ask(client, tokens["weixiu"], "近一年维修工单按期完成率是多少").json()["id"]
    r = client.patch(f"/api/qa/history/{hid}/favorite",
                     headers=H(tokens["weixiu"]))
    assert r.status_code == 200 and r.json()["is_favorite"] is True
    r = client.patch(f"/api/qa/history/{hid}/favorite",
                     headers=H(tokens["weixiu"]))
    assert r.json()["is_favorite"] is False


def test_12_favorite_others_record_404(client, tokens, qa_seed):
    hid = ask(client, tokens["admin"], "近一年维修工单按期完成率是多少").json()["id"]
    r = client.patch(f"/api/qa/history/{hid}/favorite",
                     headers=H(tokens["weixiu"]))
    assert r.status_code == 404


def test_13_rerun(client, tokens, qa_seed):
    hid = ask(client, tokens["weixiu"], "工单完成率").json()["id"]
    r = client.post(f"/api/qa/history/{hid}/rerun", headers=H(tokens["weixiu"]))
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "need_clarify"
    assert d["id"] != hid


def test_14_history_list_and_favorite_filter(client, tokens, qa_seed):
    hid = ask(client, tokens["weixiu"], "今天天气怎么样").json()["id"]
    client.patch(f"/api/qa/history/{hid}/favorite", headers=H(tokens["weixiu"]))
    r = client.get("/api/qa/history", headers=H(tokens["weixiu"]))
    assert r.status_code == 200
    ids = [h["id"] for h in r.json()]
    assert ids == sorted(ids, reverse=True)  # 倒序
    assert all(h["user_id"] is not None for h in r.json())
    r = client.get("/api/qa/history", params={"favorite_only": 1},
                   headers=H(tokens["weixiu"]))
    favs = r.json()
    assert favs and all(h["is_favorite"] for h in favs)
    # admin 可看全部
    r = client.get("/api/qa/history", params={"all": 1},
                   headers=H(tokens["admin"]))
    assert len(r.json()) >= len(client.get("/api/qa/history",
                                           headers=H(tokens["weixiu"])).json())


def test_15_delete_permissions(client, tokens, qa_seed):
    hid_w = ask(client, tokens["weixiu"], "今天天气怎么样").json()["id"]
    hid_a = ask(client, tokens["admin"], "今天天气怎么样").json()["id"]
    # weixiu 删 admin 的记录 → 403
    r = client.delete(f"/api/qa/history/{hid_a}", headers=H(tokens["weixiu"]))
    assert r.status_code == 403
    # admin 可删别人的
    r = client.delete(f"/api/qa/history/{hid_w}", headers=H(tokens["admin"]))
    assert r.status_code == 200 and r.json()["deleted"] == hid_w
    # 本人可删自己的
    hid_w2 = ask(client, tokens["weixiu"], "今天天气怎么样").json()["id"]
    r = client.delete(f"/api/qa/history/{hid_w2}", headers=H(tokens["weixiu"]))
    assert r.status_code == 200


def test_16_audit_log_has_qa_ask(client, tokens, qa_seed):
    ask(client, tokens["admin"], "近一年维修工单按期完成率是多少")
    conn = get_conn()
    try:
        n = conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action = 'qa_ask' "
            "AND username = 'admin'").fetchone()["c"]
        assert n >= 1
        n2 = conn.execute(
            "SELECT COUNT(*) c FROM qa_history WHERE user_id = "
            "(SELECT id FROM users WHERE username = 'admin')").fetchone()["c"]
        assert n2 >= 1
    finally:
        conn.close()


def test_17_mocked_engines_noted():
    # metrics_engine / services_engine 由并行 worker 提供；缺失时走本地 mock
    print("\n[MOCKED_ENGINES]", MOCKED_ENGINES)
    assert MOCKED_ENGINES == {"metrics": False, "services": False}, \
        "真实引擎应已就位"
