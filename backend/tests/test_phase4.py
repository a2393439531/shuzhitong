"""数治通四期（推广运营）测试：独立测试库 + 独立 FastAPI 应用。

覆盖：多基地配置 / 基地差异 / 有效口径 / 变更全链路（申请→分析→确认→
生效拦截→生效→通知→回退）/ 运营大盘 / 问数基地口径声明。
必须在 import app 模块之前指定 SZT_DB_PATH。
原创。
"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="szt_test_phase4_")
os.environ["SZT_DB_PATH"] = os.path.join(_tmp, "test.db")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.database as database

database._engine = None  # 隔离：按本文件 SZT_DB_PATH 重建引擎

from app.database import get_conn, init_db  # noqa: E402
from app.routers.auth import router as auth_router  # noqa: E402
from app.routers.bases import router as bases_router  # noqa: E402
from app.routers.changes import router as changes_router  # noqa: E402
from app.routers.ops import router as ops_router  # noqa: E402
from app.routers.qa import router as qa_router  # noqa: E402
from app.seed import seed  # noqa: E402

init_db()
seed()

test_app = FastAPI()
test_app.include_router(auth_router)
test_app.include_router(bases_router)
test_app.include_router(changes_router)
test_app.include_router(ops_router)
test_app.include_router(qa_router)


@pytest.fixture(scope="module")
def client():
    with TestClient(test_app) as c:
        yield c


@pytest.fixture(scope="module")
def tokens(client):
    out = {}
    for username, password in [
        ("admin", "Admin@123"),
        ("heping", "Heping@123"),
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


def _std_id(code="STD-001"):
    conn = get_conn()
    try:
        return conn.execute("SELECT id FROM standards WHERE code = ?",
                            (code,)).fetchone()["id"]
    finally:
        conn.close()


def _ind_id(code="WO_ON_TIME_RATE"):
    conn = get_conn()
    try:
        return conn.execute("SELECT id FROM indicators WHERE code = ?",
                            (code,)).fetchone()["id"]
    finally:
        conn.close()


# ================= 种子 =================

def test_01_seed_bases_and_diffs():
    conn = get_conn()
    try:
        codes = {r["code"] for r in conn.execute(
            "SELECT code FROM bases").fetchall()}
        assert {"BASE-A", "BASE-B"} <= codes
        n = conn.execute(
            "SELECT COUNT(*) c FROM std_base_diff "
            "WHERE base_code = 'BASE-B' AND status = '已发布'").fetchone()["c"]
        assert n >= 1
        n2 = conn.execute(
            "SELECT COUNT(*) c FROM indicator_base_diff "
            "WHERE base_code = 'BASE-B' AND status = '已发布'").fetchone()["c"]
        assert n2 >= 1
    finally:
        conn.close()


# ================= 基地 CRUD =================

def test_02_create_base(client, tokens):
    r = client.post("/api/bases", json={
        "code": "BASE-C", "name": "基地C", "stack_type": "PWR1000",
        "status": "建设中", "description": "测试基地",
    }, headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["code"] == "BASE-C"


def test_03_create_base_duplicate(client, tokens):
    r = client.post("/api/bases", json={"code": "BASE-A", "name": "重复"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 400


def test_04_create_base_empty_code(client, tokens):
    r = client.post("/api/bases", json={"code": "", "name": "空"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 400


def test_05_get_base_detail(client, tokens):
    r = client.get("/api/bases/BASE-B", headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "基地B"
    assert len(body["std_diffs"]) >= 1
    assert len(body["indicator_diffs"]) >= 1


# ================= 基地差异 =================

def test_06_create_std_diff_draft(client, tokens):
    r = client.post("/api/bases/diffs/standards",
                    params={"standard_id": _std_id()},
                    json={"base_code": "BASE-A", "diff_type": "允许值",
                          "diff_desc": {"note": "测试差异"},
                          "reason": "测试"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "草稿"


def test_07_create_std_diff_bad_standard(client, tokens):
    r = client.post("/api/bases/diffs/standards",
                    params={"standard_id": 99999},
                    json={"base_code": "BASE-A", "diff_type": "允许值"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 404


def test_08_publish_std_diff(client, tokens):
    conn = get_conn()
    try:
        did = conn.execute(
            "SELECT id FROM std_base_diff WHERE base_code = 'BASE-A' "
            "AND status = '草稿' ORDER BY id DESC LIMIT 1").fetchone()["id"]
    finally:
        conn.close()
    r = client.post(f"/api/bases/diffs/standards/{did}/publish",
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "已发布"


def test_09_publish_diff_forbidden(client, tokens):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM std_base_diff WHERE status = '草稿' LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if row is None:  # 没有草稿就造一个
        r = client.post("/api/bases/diffs/standards",
                        params={"standard_id": _std_id()},
                        json={"base_code": "BASE-A", "diff_type": "口径"},
                        headers=H(tokens["admin"]))
        did = r.json()["id"]
    else:
        did = row["id"]
    r = client.post(f"/api/bases/diffs/standards/{did}/publish",
                    headers=H(tokens["audit"]))
    assert r.status_code == 403


def test_10_effective_standard_with_base(client, tokens):
    r = client.get(f"/api/bases/effective/standard/{_std_id()}",
                   params={"base_code": "BASE-B"},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effective_allowed_values"] == ["NS1", "NS2", "非核级"]
    assert "基地B" in body["base_note"]


def test_11_effective_standard_common(client, tokens):
    r = client.get(f"/api/bases/effective/standard/{_std_id()}",
                   headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "NS3" in body["effective_allowed_values"]
    assert body["base_note"] == ""


def test_12_effective_indicator_with_base(client, tokens):
    r = client.get("/api/bases/effective/indicator/WO_ON_TIME_RATE",
                   params={"base_code": "BASE-B"},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert "基地B" in r.json()["base_note"]


def test_13_create_ind_diff(client, tokens):
    r = client.post("/api/bases/diffs/indicators",
                    params={"indicator_id": _ind_id()},
                    json={"base_code": "BASE-A", "diff_type": "口径",
                          "diff_desc": {"scope_note": "测试"},
                          "reason": "测试"},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "草稿"


# ================= 变更全链路 =================

def _mk_change(client, tokens, ctype="标准版本", tid=None, title="测试变更"):
    tid = tid or _std_id()
    r = client.post("/api/changes", json={
        "change_type": ctype, "target_id": tid, "title": title,
        "change_desc": "测试", "version_to": "v9.9",
    }, headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    return r.json()


def test_14_create_change(client, tokens):
    body = _mk_change(client, tokens, title="STD-001 升级 v1.1")
    assert body["status"] == "草稿"
    assert body["version_from"] == "v1.0"
    assert body["snapshot"]["version"] == "v1.0"


def test_15_create_change_bad_type(client, tokens):
    r = client.post("/api/changes", json={
        "change_type": "乱填", "target_id": 1, "title": "x"},
        headers=H(tokens["admin"]))
    assert r.status_code == 400


def test_16_create_change_forbidden(client, tokens):
    r = client.post("/api/changes", json={
        "change_type": "标准版本", "target_id": _std_id(), "title": "x"},
        headers=H(tokens["audit"]))
    assert r.status_code == 403


def test_17_submit_generates_impacts(client, tokens):
    ch = _mk_change(client, tokens, title="提交测试")
    r = client.post(f"/api/changes/{ch['id']}/submit",
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "待确认"
    cats = {i["category"] for i in body["impacts"]}
    assert "责任人" in cats
    assert len(body["confirmations"]) >= 1
    assert all(c["status"] == "待确认" for c in body["confirmations"])


def test_18_submit_twice_rejected(client, tokens):
    ch = _mk_change(client, tokens, title="重复提交测试")
    r = client.post(f"/api/changes/{ch['id']}/submit",
                    headers=H(tokens["admin"]))
    assert r.status_code == 200
    r2 = client.post(f"/api/changes/{ch['id']}/submit",
                     headers=H(tokens["admin"]))
    assert r2.status_code == 400


def test_19_effect_blocked_without_confirm(client, tokens):
    ch = _mk_change(client, tokens, title="拦截测试")
    client.post(f"/api/changes/{ch['id']}/submit",
                headers=H(tokens["admin"]))
    r = client.post(f"/api/changes/{ch['id']}/effect",
                    headers=H(tokens["admin"]))
    assert r.status_code == 400, r.text
    assert "缺失确认" in r.json()["detail"]


def test_20_confirm_all_then_effect(client, tokens):
    ch = _mk_change(client, tokens, title="生效测试")
    r = client.post(f"/api/changes/{ch['id']}/submit",
                    headers=H(tokens["admin"]))
    cid = r.json()["id"]
    # admin 代确认全部
    for _ in range(10):
        d = client.get(f"/api/changes/{cid}",
                       headers=H(tokens["admin"])).json()
        pend = [c for c in d["confirmations"] if c["status"] == "待确认"]
        if not pend:
            break
        rr = client.post(f"/api/changes/{cid}/confirm", json={},
                         headers=H(tokens["admin"]))
        assert rr.status_code == 200, rr.text
    r = client.post(f"/api/changes/{cid}/effect",
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "已生效"
    assert body["effective_at"]
    assert len(body["notices"]) >= 2  # 责任人 + 申请人
    conn = get_conn()
    try:
        v = conn.execute("SELECT version FROM standards WHERE id = ?",
                         (_std_id(),)).fetchone()["version"]
        assert v == "v9.9", v
        sv = conn.execute(
            "SELECT COUNT(*) c FROM std_versions WHERE standard_id = ? "
            "AND version = 'v9.9'", (_std_id(),)).fetchone()["c"]
        assert sv >= 1
    finally:
        conn.close()


def test_21_rollback_restores_snapshot(client, tokens):
    conn = get_conn()
    try:
        before = conn.execute("SELECT version FROM standards WHERE id = ?",
                              (_std_id(),)).fetchone()["version"]
    finally:
        conn.close()
    ch = _mk_change(client, tokens, title="回退测试")
    r = client.post(f"/api/changes/{ch['id']}/submit",
                    headers=H(tokens["admin"]))
    cid = r.json()["id"]
    for _ in range(10):
        d = client.get(f"/api/changes/{cid}",
                       headers=H(tokens["admin"])).json()
        pend = [c for c in d["confirmations"] if c["status"] == "待确认"]
        if not pend:
            break
        client.post(f"/api/changes/{cid}/confirm", json={},
                    headers=H(tokens["admin"]))
    client.post(f"/api/changes/{cid}/effect", headers=H(tokens["admin"]))
    r = client.post(f"/api/changes/{cid}/rollback",
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "已回退"
    conn = get_conn()
    try:
        v = conn.execute("SELECT version FROM standards WHERE id = ?",
                         (_std_id(),)).fetchone()["version"]
        assert v == before, (v, before)
    finally:
        conn.close()


def test_22_rollback_only_when_effective(client, tokens):
    ch = _mk_change(client, tokens, title="回退拦截测试")
    r = client.post(f"/api/changes/{ch['id']}/rollback",
                    headers=H(tokens["admin"]))
    assert r.status_code == 400


def test_23_reject_change(client, tokens):
    ch = _mk_change(client, tokens, title="驳回测试")
    client.post(f"/api/changes/{ch['id']}/submit",
                headers=H(tokens["admin"]))
    r = client.post(f"/api/changes/{ch['id']}/reject", json={"comment": "不行"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "已驳回"


def test_24_confirm_not_in_pending_status(client, tokens):
    ch = _mk_change(client, tokens, title="确认状态测试")
    r = client.post(f"/api/changes/{ch['id']}/confirm", json={},
                    headers=H(tokens["admin"]))
    assert r.status_code == 400  # 草稿状态不可确认


# ================= 运营大盘 =================

def test_25_ops_overview(client, tokens):
    r = client.get("/api/ops/overview", headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("governance", "quality_trend", "service_usage", "qa_usage",
              "change_stats", "trend_days"):
        assert k in body, k
    assert body["trend_days"] == 14
    assert len(body["quality_trend"]["days"]) == 14
    assert body["governance"]["bases"] >= 2


def test_26_ops_overview_forbidden(client, tokens):
    r = client.get("/api/ops/overview", headers=H(tokens["audit"]))
    assert r.status_code == 403


def test_27_audit_trend(client, tokens):
    r = client.get("/api/ops/audit-trend", params={"days": 7},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["days"]) == 7
    assert "series" in body


def test_28_audit_trend_forbidden(client, tokens):
    r = client.get("/api/ops/audit-trend", headers=H(tokens["weixiu"]))
    assert r.status_code == 403


# ================= 问数基地口径声明 =================

def test_29_qa_with_base_declares_caliber(client, tokens):
    r = client.post("/api/qa/ask", json={
        "question": "近一年维修工单按期完成率是多少",
        "base_code": "BASE-B",
    }, headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success", body
    note = (body.get("scope") or {}).get("base", {}).get("note", "")
    assert "基地B" in note, note
    assert "口径声明" in (body.get("interpretation") or ""), \
        body.get("interpretation")


def test_30_qa_without_base_no_note(client, tokens):
    r = client.post("/api/qa/ask", json={
        "question": "近一年维修工单按期完成率是多少",
    }, headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success", body
    note = (body.get("scope") or {}).get("base", {}).get("note", "")
    assert note == "", note
