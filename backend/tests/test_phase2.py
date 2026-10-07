"""数治通二期 API 测试：TestClient + 独立测试库。原创。"""
import os
import re
import tempfile

# 必须在 import app 之前指定测试库路径
_tmp = tempfile.mkdtemp(prefix="szt_test_phase2_")
os.environ["SZT_DB_PATH"] = os.path.join(_tmp, "test.db")

import pytest
from fastapi.testclient import TestClient

from app.database import get_conn
from app.main import app


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


def obj_id_by_code(client, token, code):
    r = client.get("/api/objects", params={"q": code}, headers=H(token))
    assert r.status_code == 200
    for o in r.json():
        if o["code"] == code:
            return o["id"]
    raise AssertionError(f"object {code} not found")


def std_id_by_code(client, token, code):
    r = client.get("/api/standards", params={"q": code}, headers=H(token))
    assert r.status_code == 200
    for s in r.json():
        if s["code"] == code:
            return s["id"]
    raise AssertionError(f"standard {code} not found")


@pytest.fixture(scope="module")
def md_model(client, tokens):
    """测试专用主数据模型（模块级共享，顺序依赖的测试用其 ID）。"""
    peq = obj_id_by_code(client, tokens["admin"], "P-EQ")
    r = client.post("/api/masterdata/models",
                    json={"code": "MD-T", "name": "测试设备主数据",
                          "object_id": peq, "id_rule": "T-",
                          "key_fields": "device_code", "status": "已发布"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    return r.json()


# ---------- 种子数据 ----------

def test_01_seed_phase2_loaded(client):
    conn = get_conn()
    try:
        assert conn.execute(
            "SELECT COUNT(*) c FROM md_models").fetchone()["c"] >= 2
        assert conn.execute(
            "SELECT COUNT(*) c FROM demo_device_ledger").fetchone()["c"] == 8
        assert conn.execute(
            "SELECT COUNT(*) c FROM quality_rules").fetchone()["c"] >= 4
        assert conn.execute(
            "SELECT COUNT(*) c FROM field_mappings").fetchone()["c"] == 3
        r = conn.execute(
            "SELECT data_steward, tech_owner FROM responsibilities "
            "WHERE field_name = 'safety_class'").fetchone()
        assert r and r["data_steward"] and r["tech_owner"]
    finally:
        conn.close()


# ---------- 主数据模型 ----------

def test_02_models_include_object_info(client, tokens, md_model):
    r = client.get("/api/masterdata/models", headers=H(tokens["admin"]))
    assert r.status_code == 200
    by_code = {m["code"]: m for m in r.json()}
    assert by_code["MD-EQ"]["object_code"] == "P-EQ"
    assert by_code["MD-EQ"]["object_name"] == "物理设备"
    assert by_code["MD-T"]["object_code"] == "P-EQ"


def test_03_model_forbidden_for_operator(client, tokens):
    r = client.post("/api/masterdata/models",
                    json={"code": "MD-X", "name": "无权创建"},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 403


def test_04_model_detail_record_count(client, tokens, md_model):
    r = client.get(f"/api/masterdata/models/{md_model['id']}",
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert r.json()["record_count"] == 0


def test_05_model_duplicate_code(client, tokens):
    r = client.post("/api/masterdata/models",
                    json={"code": "MD-EQ", "name": "重复编码"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 400


# ---------- 申请 → 审核 ----------

def test_06_apply_add_no_duplicates(client, tokens, md_model):
    r = client.post(f"/api/masterdata/models/{md_model['id']}/apply",
                    json={"app_type": "新增",
                          "payload": {"device_code": "T-DEV-001",
                                     "device_name": "测试泵"},
                          "reason": "新设备投运"},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "待审核"
    assert body["duplicates"] == []


def test_07_review_approve_add_generates_code(client, tokens, md_model):
    r = client.get("/api/masterdata/applications",
                   params={"status": "待审核", "model_id": md_model["id"]},
                   headers=H(tokens["admin"]))
    app_id = r.json()[0]["id"]
    r = client.post(f"/api/masterdata/applications/{app_id}/review",
                    json={"decision": "通过", "comment": "同意"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "已通过"
    assert re.match(r"^T-\d{6}$", body["record"]["master_code"])
    assert body["record"]["attrs"]["device_code"] == "T-DEV-001"
    assert body["record"]["status"] == "已发布"
    assert body["record"]["version"] == 1


def test_08_apply_add_detects_duplicates(client, tokens, md_model):
    r = client.post(f"/api/masterdata/models/{md_model['id']}/apply",
                    json={"app_type": "新增",
                          "payload": {"device_code": "T-DEV-001",
                                     "device_name": "另一台"},
                          "reason": "重复录入"},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    dups = r.json()["duplicates"]
    assert len(dups) == 1
    assert re.match(r"^T-\d{6}$", dups[0]["master_code"])
    assert dups[0]["attrs"]["device_name"] == "测试泵"


def test_09_review_reject(client, tokens, md_model):
    r = client.get("/api/masterdata/applications",
                   params={"status": "待审核", "model_id": md_model["id"]},
                   headers=H(tokens["admin"]))
    app_id = r.json()[0]["id"]
    r = client.post(f"/api/masterdata/applications/{app_id}/review",
                    json={"decision": "驳回", "comment": "疑似重复"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert r.json()["status"] == "已驳回"
    assert r.json()["record"] is None


def test_10_apply_change_review_writes_history(client, tokens, md_model):
    r = client.get("/api/masterdata/records",
                   params={"model_id": md_model["id"]},
                   headers=H(tokens["admin"]))
    master_code = r.json()[0]["master_code"]
    r = client.post(f"/api/masterdata/models/{md_model['id']}/apply",
                    json={"app_type": "变更", "master_code": master_code,
                          "payload": {"device_name": "测试泵(改名)"},
                          "reason": "更名"},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    app_id = r.json()["application_id"]
    r = client.post(f"/api/masterdata/applications/{app_id}/review",
                    json={"decision": "通过", "comment": "同意变更"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    rec = r.json()["record"]
    assert rec["version"] == 2
    assert rec["attrs"]["device_name"] == "测试泵(改名)"
    assert rec["attrs"]["device_code"] == "T-DEV-001"
    r = client.get(f"/api/masterdata/records/{rec['id']}",
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    body = r.json()
    assert len(body["history"]) == 2
    assert body["history"][-1]["version"] == 2


def test_11_apply_deactivate_review(client, tokens, md_model):
    r = client.get("/api/masterdata/records",
                   params={"model_id": md_model["id"]},
                   headers=H(tokens["admin"]))
    master_code = r.json()[0]["master_code"]
    r = client.post(f"/api/masterdata/models/{md_model['id']}/apply",
                    json={"app_type": "停用", "master_code": master_code,
                          "reason": "设备退役"},
                    headers=H(tokens["weixiu"]))
    app_id = r.json()["application_id"]
    r = client.post(f"/api/masterdata/applications/{app_id}/review",
                    json={"decision": "通过", "comment": "同意停用"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["record"]["status"] == "已停用"


def test_12_review_twice_rejected(client, tokens, md_model):
    r = client.get("/api/masterdata/applications",
                   params={"status": "已通过", "model_id": md_model["id"]},
                   headers=H(tokens["admin"]))
    app_id = r.json()[0]["id"]
    r = client.post(f"/api/masterdata/applications/{app_id}/review",
                    json={"decision": "通过"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 400


def test_13_apply_bad_type_400(client, tokens, md_model):
    r = client.post(f"/api/masterdata/models/{md_model['id']}/apply",
                    json={"app_type": "作废"},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 400


# ---------- 记录直接变更 / 分发 ----------

def test_14_record_put_merges_attrs_and_history(client, tokens, md_model):
    r = client.get("/api/masterdata/records",
                   params={"model_id": md_model["id"]},
                   headers=H(tokens["admin"]))
    rec_id = r.json()[0]["id"]
    ver_before = r.json()[0]["version"]
    hist_before = len(client.get(f"/api/masterdata/records/{rec_id}",
                                 headers=H(tokens["admin"])).json()["history"])
    r = client.put(f"/api/masterdata/records/{rec_id}",
                   json={"attrs": {"remark": "直接备注"}},
                   headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["version"] == ver_before + 1
    assert rec["attrs"]["remark"] == "直接备注"
    assert rec["attrs"]["device_code"] == "T-DEV-001"
    r = client.get(f"/api/masterdata/records/{rec_id}",
                   headers=H(tokens["admin"]))
    hist = r.json()["history"]
    assert len(hist) == hist_before + 1
    assert hist[-1]["version"] == ver_before + 1
    assert hist[-1]["change_desc"] == "直接变更"


def test_15_record_distribute(client, tokens, md_model):
    r = client.get("/api/masterdata/records",
                   params={"model_id": md_model["id"]},
                   headers=H(tokens["admin"]))
    rec_id = r.json()[0]["id"]
    r = client.post(f"/api/masterdata/records/{rec_id}/distribute",
                    json={"target_systems": ["DCS系统", "维修管理系统"]},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    assert r.json()["distributed"] == ["DCS系统", "维修管理系统"]
    r = client.get(f"/api/masterdata/records/{rec_id}",
                   headers=H(tokens["admin"]))
    dists = r.json()["distributions"]
    assert len(dists) == 2
    assert all(d["status"] == "成功" for d in dists)


def test_16_record_detail_parses_attrs(client, tokens, md_model):
    r = client.get("/api/masterdata/records",
                   params={"model_id": md_model["id"]},
                   headers=H(tokens["admin"]))
    rec_id = r.json()[0]["id"]
    r = client.get(f"/api/masterdata/records/{rec_id}",
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert isinstance(r.json()["attrs"], dict)


def test_17_records_query_filter(client, tokens, md_model):
    r = client.get("/api/masterdata/records",
                   params={"model_id": md_model["id"], "status": "已停用",
                           "q": "T-DEV-001"},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert len(r.json()) >= 1


# ---------- 编码映射 ----------

def test_18_code_map_crud(client, tokens, md_model):
    r = client.get("/api/masterdata/records",
                   params={"model_id": md_model["id"]},
                   headers=H(tokens["admin"]))
    master_code = r.json()[0]["master_code"]
    r = client.post("/api/masterdata/code-map",
                    json={"model_id": md_model["id"], "master_code": master_code,
                          "source_system": "设备管理系统", "source_code": "EQ-OLD-1"},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    r = client.get("/api/masterdata/code-map",
                   params={"model_id": md_model["id"],
                           "source_system": "设备管理系统"},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert any(m["source_code"] == "EQ-OLD-1" for m in r.json())


# ---------- 三码关系 ----------

def test_19_device_links_truncate_and_effective(client, tokens):
    hdrs = H(tokens["weixiu"])
    r = client.post("/api/masterdata/device-links",
                    json={"logic_code": "L-TEST-001", "model_code": "M-1",
                          "physical_code": "P-OLD", "effective_from": "2020-01-01"},
                    headers=hdrs)
    assert r.status_code == 200, r.text
    assert r.json()["truncated"] == 0
    r = client.post("/api/masterdata/device-links",
                    json={"logic_code": "L-TEST-001", "model_code": "M-1",
                          "physical_code": "P-NEW", "effective_from": "2025-06-01"},
                    headers=hdrs)
    assert r.status_code == 200, r.text
    assert r.json()["truncated"] == 1
    assert r.json()["link"]["effective_to"] is None
    r = client.get("/api/masterdata/device-links",
                   params={"logic_code": "L-TEST-001", "at": "2024-01-01"},
                   headers=H(tokens["admin"]))
    assert [l["physical_code"] for l in r.json()] == ["P-OLD"]
    r = client.get("/api/masterdata/device-links",
                   params={"logic_code": "L-TEST-001", "at": "2026-01-01"},
                   headers=H(tokens["admin"]))
    assert [l["physical_code"] for l in r.json()] == ["P-NEW"]
    r = client.get("/api/masterdata/device-links",
                   params={"physical_code": "P-NEW"},
                   headers=H(tokens["admin"]))
    assert len(r.json()) == 1


# ---------- 字段映射 ----------

def test_20_field_mapping_crud(client, tokens):
    peq = obj_id_by_code(client, tokens["admin"], "P-EQ")
    std1 = std_id_by_code(client, tokens["admin"], "STD-001")
    hdrs = H(tokens["weixiu"])
    r = client.post("/api/field-mappings/",
                    json={"source_system": "测试系统", "source_table": "T_TEST",
                          "source_field": "f_grade", "standard_id": std1,
                          "object_id": peq, "remark": "测试映射"},
                    headers=hdrs)
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    r = client.get("/api/field-mappings/",
                   params={"source_system": "设备管理系统"},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert len(r.json()) >= 2  # 种子 3 条中 2 条是设备管理系统
    r = client.get("/api/field-mappings/", params={"object_id": peq},
                   headers=H(tokens["admin"]))
    assert any(m["id"] == mid for m in r.json())
    r = client.put(f"/api/field-mappings/{mid}",
                   json={"source_system": "测试系统", "source_table": "T_TEST",
                         "source_field": "f_grade", "standard_id": std1,
                         "object_id": peq, "remark": "已修改"},
                   headers=hdrs)
    assert r.status_code == 200
    assert r.json()["remark"] == "已修改"
    # operator 无权删除
    r = client.delete(f"/api/field-mappings/{mid}", headers=hdrs)
    assert r.status_code == 403
    r = client.delete(f"/api/field-mappings/{mid}",
                      headers=H(tokens["admin"]))
    assert r.status_code == 200
    r = client.get("/api/field-mappings/", params={"object_id": peq},
                   headers=H(tokens["admin"]))
    assert not any(m["id"] == mid for m in r.json())


def test_21_field_mapping_seed_has_standard_and_md(client, tokens):
    r = client.get("/api/field-mappings/",
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    rows = r.json()
    assert any(m["standard_code"] == "STD-001" for m in rows)
    assert any(m["md_model_code"] == "MD-EQ" for m in rows)


# ---------- 质量规则引擎 ----------

def test_22_rule_crud_and_toggle(client, tokens):
    peq = obj_id_by_code(client, tokens["admin"], "P-EQ")
    r = client.post("/api/quality/rules",
                    json={"name": "测试规则-临时", "object_id": peq,
                          "target_table": "demo_device_ledger",
                          "target_field": "device_code", "rule_type": "完整性",
                          "severity": "低", "assignee_type": "业务"},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 403  # operator 无权
    r = client.post("/api/quality/rules",
                    json={"name": "测试规则-临时", "object_id": peq,
                          "target_table": "demo_device_ledger",
                          "target_field": "device_code", "rule_type": "完整性",
                          "severity": "低", "assignee_type": "业务"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    r = client.patch(f"/api/quality/rules/{rid}/toggle",
                     headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert r.json()["is_enabled"] == 0
    r = client.patch(f"/api/quality/rules/{rid}/toggle",
                     headers=H(tokens["admin"]))
    assert r.json()["is_enabled"] == 1
    r = client.put(f"/api/quality/rules/{rid}",
                   json={"name": "测试规则-改名", "object_id": peq,
                         "target_table": "demo_device_ledger",
                         "target_field": "device_code", "rule_type": "完整性",
                         "severity": "低", "assignee_type": "业务"},
                   headers=H(tokens["admin"]))
    assert r.json()["name"] == "测试规则-改名"
    r = client.delete(f"/api/quality/rules/{rid}",
                      headers=H(tokens["admin"]))
    assert r.status_code == 200
    r = client.get("/api/quality/rules", headers=H(tokens["admin"]))
    assert not any(x["id"] == rid for x in r.json())


def _rule_id_by_name(client, token, name):
    r = client.get("/api/quality/rules", headers=H(token))
    for x in r.json():
        if x["name"] == name:
            return x["id"]
    raise AssertionError(f"rule {name} not found")


def test_23_run_completeness_rule_creates_issues(client, tokens):
    rid = _rule_id_by_name(client, tokens["admin"], "设备编码完整性检查")
    r = client.post(f"/api/quality/rules/{rid}/run",
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] > 0
    assert body["issue_count"] >= 1  # 空编码行
    assert all(i["assignee"] for i in body["issues"])  # 自动派发非空
    assert all(i["record_ref"] == "台账ID:3" for i in body["issues"])
    # 执行记录可查
    r = client.get(f"/api/quality/runs/{body['run_id']}",
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert r.json()["status"] == "完成"


def test_24_run_dedupes_open_issues(client, tokens):
    rid = _rule_id_by_name(client, tokens["admin"], "设备编码完整性检查")
    r = client.post(f"/api/quality/rules/{rid}/run",
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200
    assert r.json()["issue_count"] == 0  # 未关闭的不重复建


def test_25_run_uniqueness_rule(client, tokens):
    rid = _rule_id_by_name(client, tokens["admin"], "设备编码唯一性检查")
    r = client.post(f"/api/quality/rules/{rid}/run",
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    assert r.json()["issue_count"] >= 2  # D-003 重复两行
    refs = {i["record_ref"] for i in r.json()["issues"]}
    assert refs == {"台账ID:4", "台账ID:5"}


def test_26_run_validity_rule_dispatches_by_field(client, tokens):
    rid = _rule_id_by_name(client, tokens["admin"], "核安全分级有效性检查")
    r = client.post(f"/api/quality/rules/{rid}/run",
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    issues = r.json()["issues"]
    assert len(issues) >= 1  # N99 行
    assert any(i["record_ref"] == "台账ID:6" for i in issues)
    # field_name=safety_class 精确匹配认责 → 业务派发给数据专员
    assert any(i["assignee"] == "设备部数据专员" for i in issues)


def test_27_run_timeliness_rule(client, tokens):
    rid = _rule_id_by_name(client, tokens["admin"], "台账更新及时性检查")
    r = client.post(f"/api/quality/rules/{rid}/run",
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    issues = r.json()["issues"]
    assert any(i["record_ref"] == "台账ID:7" for i in issues)
    # 技术类 → 派发给技术负责人
    assert any(i["assignee"] == "信息中心" for i in issues)


def test_28_run_all(client, tokens):
    r = client.post("/api/quality/rules/run-all",
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    runs = r.json()["runs"]
    assert len(runs) >= 4
    assert all(x["ok"] for x in runs)
    r = client.get("/api/quality/runs", headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert len(r.json()) >= 4


def test_29_schedule_upsert_and_trigger_due(client, tokens):
    rid = _rule_id_by_name(client, tokens["admin"], "设备编码完整性检查")
    r = client.post("/api/quality/schedule",
                    json={"rule_id": rid, "cron_expr": "0 2 * * *",
                          "is_enabled": 1},
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    r = client.get("/api/quality/schedule", headers=H(tokens["admin"]))
    assert any(s["rule_id"] == rid for s in r.json())
    runs_before = len(client.get("/api/quality/runs",
                                 headers=H(tokens["admin"])).json())
    r = client.post("/api/quality/schedule/trigger-due",
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    assert len(r.json()["triggered"]) >= 1
    runs_after = len(client.get("/api/quality/runs",
                                headers=H(tokens["admin"])).json())
    assert runs_after > runs_before
    # 24h 内不再触发
    r = client.post("/api/quality/schedule/trigger-due",
                    headers=H(tokens["weixiu"]))
    assert r.json()["triggered"] == []


def _open_issue_id(client, token, record_ref):
    r = client.get("/api/quality", params={"status": "待确认"},
                   headers=H(token))
    for i in r.json():
        if i.get("record_ref") == record_ref:
            return i["id"]
    raise AssertionError(f"no open issue for {record_ref}")


def test_30_issue_lifecycle_confirm_fix(client, tokens):
    iid = _open_issue_id(client, tokens["weixiu"], "台账ID:6")
    r = client.post(f"/api/quality/issues/{iid}/confirm",
                    json={"lead_assignee": "设备部数据专员"},
                    headers=H(tokens["audit"]))
    assert r.status_code == 403  # readonly 无权
    r = client.post(f"/api/quality/issues/{iid}/confirm",
                    json={"lead_assignee": "设备部数据专员"},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "已确认"
    assert r.json()["lead_assignee"] == "设备部数据专员"
    r = client.post(f"/api/quality/issues/{iid}/fix",
                    json={"fix_desc": "已更正为 NS1",
                          "root_cause": "录入时选错分级"},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "整改中"
    assert r.json()["fix_desc"] == "已更正为 NS1"


def test_31_issue_recheck_still_bad(client, tokens):
    # 台账ID:6 的问题已进入整改中（test_30），台账数据仍未改 → 保持整改中
    r = client.get("/api/quality", params={"status": "整改中"},
                   headers=H(tokens["weixiu"]))
    iid = [i for i in r.json()
           if i.get("record_ref") == "台账ID:6"][0]["id"]
    r = client.post(f"/api/quality/issues/{iid}/recheck",
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    assert r.json()["issue"]["status"] == "整改中"
    assert "仍有问题" in r.json()["recheck_result"]


def test_32_issue_recheck_pass_then_close(client, tokens):
    # 台账ID:3（完整性）问题：先确认→整改，再把台账数据修好，复核→待复核→关闭
    iid = _open_issue_id(client, tokens["weixiu"], "台账ID:3")
    client.post(f"/api/quality/issues/{iid}/confirm", json={},
                headers=H(tokens["weixiu"]))
    client.post(f"/api/quality/issues/{iid}/fix",
                json={"fix_desc": "补录设备编码"}, headers=H(tokens["weixiu"]))
    conn = get_conn()
    try:
        conn.execute("UPDATE demo_device_ledger SET device_code = 'D-008' "
                     "WHERE id = 3")
        conn.commit()
    finally:
        conn.close()
    r = client.post(f"/api/quality/issues/{iid}/recheck",
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    assert r.json()["issue"]["status"] == "待复核"
    r = client.post(f"/api/quality/issues/{iid}/close",
                    json={"review_comment": "复核通过"},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 403  # operator 无权关闭
    r = client.post(f"/api/quality/issues/{iid}/close",
                    json={"review_comment": "复核通过"},
                    headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "已关闭"
    assert "复核意见：复核通过" in (r.json()["fix_desc"] or "")


def test_33_issue_illegal_transition(client, tokens):
    r = client.get("/api/quality", params={"status": "已关闭"},
                   headers=H(tokens["admin"]))
    iid = r.json()[0]["id"]
    r = client.post(f"/api/quality/issues/{iid}/confirm", json={},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 400


# ---------- 落标检查 ----------

def test_34_compliance_run_finds_diffs(client, tokens):
    std1 = std_id_by_code(client, tokens["admin"], "STD-001")
    r = client.post("/api/compliance/run",
                    json={"standard_id": std1,
                          "systems": ["设备管理系统", "新接入系统"]},
                    headers=H(tokens["weixiu"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["check_id"] > 0
    assert body["diff_count"] >= 2  # N99 值域不符 + 新接入系统未接入
    r = client.get(f"/api/compliance/checks/{body['check_id']}",
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    diffs = r.json()["diffs"]
    types = {d["diff_type"] for d in diffs}
    assert "值域不符" in types
    assert "未接入" in types
    assert any(d["field_name"] == "safety_class" and d["actual"] == "N99"
               for d in diffs)


def test_35_compliance_checks_list(client, tokens):
    r = client.get("/api/compliance/checks", headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_36_compliance_system_status(client, tokens):
    std1 = std_id_by_code(client, tokens["admin"], "STD-001")
    r = client.get("/api/compliance/system-status",
                   params={"standard_id": std1},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    by_sys = {s["system_name"]: s for s in r.json()}
    # 演示台账来自设备管理系统，且有差异 → 有差异
    assert by_sys["设备管理系统"]["status"] == "有差异"
    assert by_sys["设备管理系统"]["diff_count"] > 0
    # 物资系统从未接入 → 未接入
    assert by_sys["物资系统"]["status"] == "未接入"
    # DCS系统已落标且无差异 → 已落标
    assert by_sys["DCS系统"]["status"] == "已落标"


# ---------- 幂等性 ----------

def test_37_seed_phase2_idempotent(client):
    from app.seed_phase2 import seed_phase2
    conn = get_conn()
    try:
        n_models = conn.execute(
            "SELECT COUNT(*) c FROM md_models").fetchone()["c"]
        n_ledger = conn.execute(
            "SELECT COUNT(*) c FROM demo_device_ledger").fetchone()["c"]
        n_rules = conn.execute(
            "SELECT COUNT(*) c FROM quality_rules").fetchone()["c"]
    finally:
        conn.close()
    seed_phase2()
    conn = get_conn()
    try:
        assert conn.execute(
            "SELECT COUNT(*) c FROM md_models").fetchone()["c"] == n_models
        assert conn.execute(
            "SELECT COUNT(*) c FROM demo_device_ledger").fetchone()["c"] == n_ledger
        assert conn.execute(
            "SELECT COUNT(*) c FROM quality_rules").fetchone()["c"] == n_rules
    finally:
        conn.close()
