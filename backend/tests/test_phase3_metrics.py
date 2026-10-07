"""数治通三期指标管理测试：独立测试库 + 独立 FastAPI 应用（仅挂载 auth/metrics 路由）。

注意：不改 main.py（按任务约束），故自建测试应用挂载 metrics 路由。
必须在 import app 模块之前指定 SZT_DB_PATH；若与其它测试文件同进程运行，
强制重置 database._engine 以隔离到本文件测试库。
原创。
"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="szt_test_phase3_")
os.environ["SZT_DB_PATH"] = os.path.join(_tmp, "test.db")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.database as database

database._engine = None  # 隔离：按本文件 SZT_DB_PATH 重建引擎

from app.database import get_conn, init_db  # noqa: E402
from app.routers.auth import router as auth_router  # noqa: E402
from app.routers.metrics import router as metrics_router  # noqa: E402
from app.seed import seed  # noqa: E402
from app.seed_metrics import seed_metrics  # noqa: E402

init_db()
seed()
seed_metrics()

test_app = FastAPI()
test_app.include_router(auth_router)
test_app.include_router(metrics_router)

FULL = {"period_start": "2025-11", "period_end": "2026-10"}

TST_CALC_V1 = {
    "numerator_sql": (
        "SELECT COUNT(*) FROM work_orders WHERE 1=1 {dept_filter} "
        "AND cancel_flag=0 AND actual_end IS NOT NULL "
        "AND substr(actual_end,1,7)>='{period_start}' "
        "AND substr(actual_end,1,7)<='{period_end}' AND actual_end<=plan_end"
    ),
    "denominator_sql": (
        "SELECT COUNT(*) FROM work_orders WHERE 1=1 {dept_filter} "
        "AND cancel_flag=0 AND actual_end IS NOT NULL "
        "AND substr(actual_end,1,7)>='{period_start}' "
        "AND substr(actual_end,1,7)<='{period_end}'"
    ),
    "description": "测试口径 v1",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(test_app) as c:
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


# ---------- 种子数据 ----------

def test_01_seed_metrics_loaded():
    conn = get_conn()
    try:
        wo = conn.execute("SELECT COUNT(*) c FROM work_orders").fetchone()["c"]
        mi = conn.execute(
            "SELECT COUNT(*) c FROM material_issues").fetchone()["c"]
        assert wo == 26, wo
        assert mi == 44, mi
        codes = {r["code"] for r in conn.execute(
            "SELECT code FROM indicators WHERE code IS NOT NULL").fetchall()}
        assert {"WO_ON_TIME_RATE", "EQ_INTACT_RATE",
                "MAT_COST_BY_MODEL"} <= codes
    finally:
        conn.close()


# ---------- 指标 CRUD ----------

def test_02_create_metric_admin(client, tokens):
    r = client.post("/api/metrics", json={
        "code": "TST-RATE", "name": "测试按期完成率", "biz_def": "测试",
        "calc_rule": TST_CALC_V1,
        "dimensions": [{"name": "model_code", "expr": "model_code"}],
        "data_sources": ["work_orders"], "owner_dept": "设备部",
    }, headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "TST-RATE"
    assert body["version"] == "v1.0"
    assert body["status"] == "已发布"


def test_03_create_metric_readonly_forbidden(client, tokens):
    r = client.post("/api/metrics", json={
        "code": "TST-NO", "name": "不应成功",
        "calc_rule": TST_CALC_V1,
    }, headers=H(tokens["audit"]))
    assert r.status_code == 403, r.text


def test_04_list_metrics(client, tokens):
    r = client.get("/api/metrics", headers=H(tokens["admin"]))
    assert r.status_code == 200
    codes = {m["code"] for m in r.json()}
    assert "WO_ON_TIME_RATE" in codes and "TST-RATE" in codes


def test_05_get_metric_detail(client, tokens):
    r = client.get("/api/metrics/WO_ON_TIME_RATE", headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["calc_rule"], dict)
    assert "numerator_sql" in body["calc_rule"]
    assert isinstance(body["dimensions"], list)
    assert body["version_count"] == 2


# ---------- 计算与缓存 ----------

def test_06_compute_on_time_rate(client, tokens):
    r = client.post("/api/metrics/WO_ON_TIME_RATE/compute", json=FULL,
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["numerator"] is not None and body["denominator"] is not None
    assert 0 < body["value"] <= 1
    assert abs(body["value"] - body["numerator"] / body["denominator"]) < 1e-9
    assert body["cached"] is False
    # 种子指标已是 v2.0：20/22
    assert body["numerator"] == 20 and body["denominator"] == 22


def test_07_compute_cached_second_time(client, tokens):
    r = client.post("/api/metrics/WO_ON_TIME_RATE/compute", json=FULL,
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cached"] is True
    assert body["value"] == 20 / 22


def test_08_weixiu_scope_smaller_denominator(client, tokens):
    r = client.post("/api/metrics/WO_ON_TIME_RATE/compute", json=FULL,
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["denominator"] == 2  # 维修处仅 2 行工单
    assert body["denominator"] < 22  # 小于 admin 全量
    assert body["value"] == 1.0


def test_09_compute_unauthorized(client):
    r = client.post("/api/metrics/WO_ON_TIME_RATE/compute", json=FULL)
    assert r.status_code == 401


# ---------- 版本与口径对比 ----------

def test_10_update_bumps_version(client, tokens):
    v2_calc = dict(TST_CALC_V1)
    v2_calc["numerator_sql"] = TST_CALC_V1["numerator_sql"].replace(
        "AND actual_end<=plan_end",
        "AND (actual_end<=plan_end OR delay_approved=1)")
    v2_calc["description"] = "测试口径 v2：延期审批视为按期"
    r = client.put("/api/metrics/TST-RATE", json={
        "calc_rule": v2_calc,
        "change_desc": "测试口径变更：延期审批视为按期",
    }, headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["version"] == "v2.0"


def test_11_update_requires_change_desc(client, tokens):
    r = client.put("/api/metrics/TST-RATE", json={"name": "改名"},
                   headers=H(tokens["admin"]))
    assert r.status_code == 400, r.text


def test_12_compare_caliber_diff(client, tokens):
    r = client.get("/api/metrics/TST-RATE/compare",
                   params={"from": "v1.0", "to": "v2.0"},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_caliber_diff"] is True
    fields = {d["field"] for d in body["diff"]}
    assert "calc_rule" in fields


def test_13_compare_no_diff(client, tokens):
    r = client.get("/api/metrics/TST-RATE/compare",
                   params={"from": "v2.0", "to": "v2.0"},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["diff"] == []
    assert r.json()["has_caliber_diff"] is False


def test_14_seed_versions_list(client, tokens):
    r = client.get("/api/metrics/WO_ON_TIME_RATE/versions",
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    versions = [v["version"] for v in r.json()]
    assert versions == ["v1.0", "v2.0"]


# ---------- 趋势 ----------

def test_15_trend_12_months(client, tokens):
    from datetime import datetime
    now = datetime.now()
    expected_last = f"{now.year:04d}-{now.month:02d}"
    r = client.get("/api/metrics/WO_ON_TIME_RATE/trend",
                   params={"months": 12}, headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 12
    assert all(set(e.keys()) == {"period", "value"} for e in body)
    assert body[-1]["period"] == expected_last  # 以当前月份为基准
    periods = [e["period"] for e in body]
    assert periods == sorted(periods)  # 升序
    # 2026-08 当月：v2 口径下 delay_approved 行计入按期（1/1=1.0）
    aug = [e for e in body if e["period"] == "2026-08"]
    assert len(aug) == 1 and aug[0]["value"] == 1.0


def test_16_trend_with_dimension(client, tokens):
    r = client.get("/api/metrics/MAT_COST_BY_MODEL/trend",
                   params={"months": 12, "dimension": "model_code",
                           "dimension_value": "AFW-1000"},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert len(r.json()) == 12


# ---------- 安全校验 ----------

def test_17_drop_sql_compute_400(client, tokens):
    r = client.post("/api/metrics", json={
        "code": "TST-DROP", "name": "含DROP的指标",
        "calc_rule": {
            "numerator_sql": "SELECT COUNT(*) FROM work_orders WHERE code='DROP'",
            "denominator_sql": "SELECT 1",
            "description": "危险关键字测试",
        },
    }, headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    r = client.post("/api/metrics/TST-DROP/compute", json=FULL,
                    headers=H(tokens["admin"]))
    assert r.status_code == 400, r.text


def test_18_unknown_table_compute_400(client, tokens):
    r = client.post("/api/metrics", json={
        "code": "TST-BADTABLE", "name": "未知表指标",
        "calc_rule": {
            "numerator_sql": "SELECT COUNT(*) FROM hacker_table",
            "denominator_sql": "SELECT 1",
            "description": "表白名单测试",
        },
    }, headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    r = client.post("/api/metrics/TST-BADTABLE/compute", json=FULL,
                    headers=H(tokens["admin"]))
    assert r.status_code == 400, r.text


# ---------- 删除 ----------

def test_19_delete_metric_admin(client, tokens):
    for code in ("TST-DROP", "TST-BADTABLE", "TST-RATE"):
        r = client.delete(f"/api/metrics/{code}",
                          headers=H(tokens["admin"]))
        assert r.status_code == 200, (code, r.text)
        r = client.get(f"/api/metrics/{code}",
                       headers=H(tokens["admin"]))
        assert r.status_code == 404, (code, r.text)


def test_20_delete_readonly_forbidden(client, tokens):
    r = client.delete("/api/metrics/WO_ON_TIME_RATE",
                      headers=H(tokens["audit"]))
    assert r.status_code == 403
