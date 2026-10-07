"""数治通三期 API 测试：统一数据服务（服务目录/发布/订阅/调用）。原创。"""
import json
import os
import tempfile

# 必须在 import app 之前指定测试库路径
_tmp = tempfile.mkdtemp(prefix="szt_test_phase3_services_")
os.environ["SZT_DB_PATH"] = os.path.join(_tmp, "test.db")

import pytest
from fastapi.testclient import TestClient

from app import services_engine
from app.config import settings
from app.database import get_conn
from app.deps import now_str
from app.main import app
from app.routers import services as services_router
from app.seed_services import seed_services

# main.py 不允许改动，测试内挂载三期服务路由
app.include_router(services_router.router)


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


@pytest.fixture(scope="module")
def seeded(client, tokens):
    """灌三期服务种子 + 本测试专用的业务演示数据。"""
    seed_services()
    # 幂等：重复灌一次，验证不产生重复行
    seed_services()
    conn = get_conn()
    try:
        now = now_str()
        model = conn.execute(
            "SELECT id FROM md_models WHERE code = 'MD-EQ'").fetchone()
        assert model is not None
        cur = conn.cursor()
        # 主数据记录
        for mcode, attrs in [
            ("EQ-AFW-1001", {"device_code": "D-001", "safety_class": "NS1"}),
            ("EQ-CWP-2001", {"device_code": "D-004", "safety_class": "NS3"}),
        ]:
            if conn.execute(
                "SELECT 1 FROM md_records WHERE master_code = ?",
                (mcode,)).fetchone() is None:
                cur.execute(
                    """INSERT INTO md_records
                       (model_id, master_code, attrs, source_system,
                        source_code, status, version, created_at)
                       VALUES (?, ?, ?, '设备管理系统', ?, '已发布', 1, ?)""",
                    (model["id"], mcode,
                     json.dumps(attrs, ensure_ascii=False), mcode, now),
                )
        # 设备三码关系
        if conn.execute(
            "SELECT 1 FROM device_links WHERE logic_code = 'L-1001'"
        ).fetchone() is None:
            cur.execute(
                """INSERT INTO device_links
                   (logic_code, model_code, physical_code, effective_from,
                    effective_to, status, created_at)
                   VALUES ('L-1001', 'AFW-1000', 'P-9001', '2025-01-01',
                           NULL, '有效', ?)""",
                (now,),
            )
        # 工单：维修处 1 张、设备部 1 张（验证部门过滤）
        for code, dept, mc in [
            ("WO-TEST-001", "维修处", "AFW-1000"),
            ("WO-TEST-002", "设备部", "CWP-500"),
        ]:
            if conn.execute(
                "SELECT 1 FROM work_orders WHERE code = ?",
                (code,)).fetchone() is None:
                cur.execute(
                    """INSERT INTO work_orders
                       (code, device_code, model_code, base, dept, title,
                        plan_start, plan_end, status, created_at)
                       VALUES (?, 'D-001', ?, '华东基地', ?, '测试工单',
                               '2026-09-01', '2026-09-10', '已完成', ?)""",
                    (code, mc, dept, now),
                )
        # 物料领用
        if conn.execute(
            "SELECT 1 FROM material_issues WHERE wo_code = 'WO-TEST-001'"
        ).fetchone() is None:
            cur.execute(
                """INSERT INTO material_issues
                   (wo_code, material_code, material_name, qty, amount,
                    issue_date, dept)
                   VALUES ('WO-TEST-001', 'M-001', '轴承', 2, 5000.0,
                           '2026-09-05', '维修处')""",
            )
        conn.commit()
        return {"seed_ok": True}
    finally:
        conn.close()


def svc_id_by_code(client, token, code):
    r = client.get("/api/services", headers=H(token))
    assert r.status_code == 200
    for s in r.json():
        if s["code"] == code:
            return s["id"]
    raise AssertionError(f"service {code} not found")


# ---------- 用例 ----------

def test_01_seed_services_loaded(client, tokens, seeded):
    r = client.get("/api/services", headers=H(tokens["admin"]))
    assert r.status_code == 200
    codes = {s["code"] for s in r.json()}
    for c in ["SVC-MD-EQ", "SVC-REL-3CODE", "SVC-WO-DETAIL",
              "SVC-MAT-COST", "SVC-CODE-VALIDATE"]:
        assert c in codes, f"{c} missing"
    # 幂等：每个种子服务只有一条
    conn = get_conn()
    try:
        n = conn.execute(
            "SELECT COUNT(*) c FROM services WHERE code = 'SVC-MD-EQ'"
        ).fetchone()["c"]
        assert n == 1
        # 一期占位行（code 为 NULL）保留不动
        n2 = conn.execute(
            "SELECT COUNT(*) c FROM services WHERE code IS NULL"
        ).fetchone()["c"]
        assert n2 == 2
    finally:
        conn.close()


def test_02_admin_create_service_ok(client, tokens, seeded):
    r = client.post(
        "/api/services",
        json={"code": "SVC-TEST-1", "name": "测试服务一",
              "svc_type": "metric", "permission_req": "授权"},
        headers=H(tokens["admin"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "草稿"
    assert body["svc_type_label"] == "指标服务"


def test_03_readonly_create_403(client, tokens, seeded):
    r = client.post(
        "/api/services",
        json={"code": "SVC-TEST-X", "name": "不该建成的服务"},
        headers=H(tokens["audit"]),
    )
    assert r.status_code == 403


def test_04_publish_flow(client, tokens, seeded):
    sid = svc_id_by_code(client, tokens["admin"], "SVC-TEST-1")
    r = client.post(f"/api/services/{sid}/publish",
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "已发布"
    r = client.get(f"/api/services/{sid}", headers=H(tokens["admin"]))
    assert r.status_code == 200
    body = r.json()
    assert len(body["versions"]) >= 1
    assert len(body["notices"]) >= 1


def test_05_subscribe_then_invoke_403(client, tokens, seeded):
    sid = svc_id_by_code(client, tokens["admin"], "SVC-WO-DETAIL")
    r = client.post(f"/api/services/{sid}/subscribe",
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    sub_id = r.json()["id"]
    assert r.json()["status"] == "待审核"
    # 幂等：重复申请返回同一条
    r2 = client.post(f"/api/services/{sid}/subscribe",
                     headers=H(tokens["weixiu"]))
    assert r2.status_code == 200
    assert r2.json()["id"] == sub_id
    # 未审核前调用 → 403
    r = client.post("/api/services/SVC-WO-DETAIL/invoke",
                    json={"params": {}}, headers=H(tokens["weixiu"]))
    assert r.status_code == 403, r.text
    assert "未授权" in r.json()["detail"]


def test_06_review_then_invoke_200(client, tokens, seeded):
    sid = svc_id_by_code(client, tokens["admin"], "SVC-WO-DETAIL")
    r = client.get("/api/services/subscriptions/mine",
                   headers=H(tokens["weixiu"]))
    assert r.status_code == 200
    subs = [s for s in r.json() if s["service_id"] == sid
            and s["status"] == "待审核"]
    assert subs
    sub_id = subs[0]["id"]
    r = client.post(f"/api/services/subscriptions/{sub_id}/review",
                    json={"approve": True, "note": "同意"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "已授权"
    # 审核通过后调用 → 200，且只能看到本部门（维修处）工单
    r = client.post("/api/services/SVC-WO-DETAIL/invoke",
                    json={"params": {}}, headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    codes = {w["code"] for w in body["data"]}
    assert "WO-TEST-001" in codes
    assert "WO-TEST-002" not in codes  # 设备部工单被部门过滤掉
    # service_calls 有日志
    conn = get_conn()
    try:
        n = conn.execute(
            """SELECT COUNT(*) c FROM service_calls
               WHERE service_id = ? AND username = 'weixiu'
                 AND status_code = 200""",
            (sid,)).fetchone()["c"]
        assert n >= 1
    finally:
        conn.close()


def test_07_public_invoke_200(client, tokens, seeded):
    # 公开服务无需订阅即可调用
    r = client.post("/api/services/SVC-REL-3CODE/invoke",
                    json={"params": {"logic_code": "L-1001"}},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["physical_code"] == "P-9001"


def test_08_code_validate(client, tokens, seeded):
    r = client.post("/api/services/SVC-CODE-VALIDATE/invoke",
                    json={"params": {"std_code": "STD-001",
                                     "value": "NS1"}},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["valid"] is True
    r = client.post("/api/services/SVC-CODE-VALIDATE/invoke",
                    json={"params": {"std_code": "STD-001",
                                     "value": "N99"}},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["valid"] is False


def test_09_md_service_and_combo(client, tokens, seeded):
    r = client.post("/api/services/SVC-MD-EQ/invoke",
                    json={"params": {"code": "EQ-AFW-1001"}},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["model_name"] == "物理设备主数据"
    # 组合分析：先给 weixiu 授权 MAT-COST（admin 直接调也行，这里走订阅审核）
    sid = svc_id_by_code(client, tokens["admin"], "SVC-MAT-COST")
    r = client.post(f"/api/services/{sid}/subscribe",
                    headers=H(tokens["weixiu"]))
    sub_id = r.json()["id"]
    client.post(f"/api/services/subscriptions/{sub_id}/review",
                json={"approve": True}, headers=H(tokens["admin"]))
    r = client.post("/api/services/SVC-MAT-COST/invoke",
                    json={"params": {}}, headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    afw = [d for d in data if d["model"] == "AFW-1000"]
    assert afw and afw[0]["issue_count"] >= 1
    assert float(afw[0]["total_amount"]) >= 5000.0


def test_10_offline_blocked_with_dependencies(client, tokens, seeded):
    sid = svc_id_by_code(client, tokens["admin"], "SVC-WO-DETAIL")
    r = client.post(f"/api/services/{sid}/offline",
                    headers=H(tokens["admin"]))
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["detail"] == "存在依赖，无法下架"
    deps = body["dependencies"]
    assert deps["subscriptions"] >= 1
    assert deps["recent_calls"] >= 1


def test_11_offline_ok_without_dependencies(client, tokens, seeded):
    sid = svc_id_by_code(client, tokens["admin"], "SVC-TEST-1")
    r = client.post(f"/api/services/{sid}/offline",
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "已下架"


def test_12_stats_fields(client, tokens, seeded):
    sid = svc_id_by_code(client, tokens["admin"], "SVC-WO-DETAIL")
    r = client.get(f"/api/services/{sid}/stats",
                   headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "calls_7d" in body and "avg_ms" in body and "error_rate" in body
    assert body["calls_7d"] >= 1  # 至少有一次 200 调用
    assert body["error_rate"] > 0  # test_05 的 403 调用记入失败


def test_13_notices_nonempty(client, tokens, seeded):
    r = client.get("/api/services/notices", headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) >= 5  # 5 个种子服务各至少一条
    assert body[0]["service_name"]


def test_14_rate_limit(client, tokens, seeded, monkeypatch):
    services_engine._RATE_BUCKETS.clear()
    monkeypatch.setattr(settings, "SZT_SVC_RATE_LIMIT", 2)
    try:
        for i in range(2):
            r = client.post(
                "/api/services/SVC-REL-3CODE/invoke",
                json={"params": {"logic_code": "L-1001"}},
                headers=H(tokens["audit"]))
            assert r.status_code == 200, r.text
        r = client.post("/api/services/SVC-REL-3CODE/invoke",
                        json={"params": {"logic_code": "L-1001"}},
                        headers=H(tokens["audit"]))
        assert r.status_code == 429, r.text
    finally:
        services_engine._RATE_BUCKETS.clear()
