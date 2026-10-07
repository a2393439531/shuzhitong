"""数治通一期 API 测试：TestClient + 独立测试库。"""
import os
import tempfile

# 必须在 import app 之前指定测试库路径
_tmp = tempfile.mkdtemp(prefix="szt_test_")
os.environ["SZT_DB_PATH"] = os.path.join(_tmp, "test.db")

import pytest
from fastapi.testclient import TestClient

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


# ---------- 认证 ----------

def test_1_login_success(client):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": "Admin@123"})
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "super_admin"


def test_2_login_wrong_password(client):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_3_unauthorized_401(client):
    r = client.get("/api/objects")
    assert r.status_code == 401


def test_4_me(client, tokens):
    r = client.get("/api/auth/me", headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


# ---------- 权限 ----------

def test_5_readonly_cannot_write(client, tokens):
    r = client.post("/api/objects", headers=H(tokens["audit"]),
                    json={"code": "X", "name": "X"})
    assert r.status_code == 403


def test_6_operator_create_object(client, tokens):
    r = client.post("/api/objects", headers=H(tokens["weixiu"]),
                    json={"code": "T-OBJ", "name": "测试对象",
                          "definition": "测试用", "owner_dept": "设备部"})
    assert r.status_code == 200
    assert r.json()["code"] == "T-OBJ"


# ---------- 对象卡聚合 ----------

def test_7_object_card_full(client, tokens):
    oid = obj_id_by_code(client, tokens["admin"], "L-EQ")
    r = client.get(f"/api/objects/{oid}/card", headers=H(tokens["admin"]))
    assert r.status_code == 200
    card = r.json()
    for key in ["object", "attrs", "relations", "processes", "resources",
                "standards", "responsibilities", "source_systems",
                "quality_issues", "services", "indicators"]:
        assert key in card, key
    assert card["object"]["code"] == "L-EQ"
    assert len(card["attrs"]) >= 2
    # 三码关系：安装关系带有效时间
    installs = [x for x in card["relations"]
                if x["rel_type"] == "安装" and x["peer_code"] == "P-EQ"]
    assert len(installs) == 2
    eff = {(x["effective_from"], x["effective_to"]) for x in installs}
    assert ("2020-01-01", "2025-05-31") in eff
    assert ("2025-06-01", None) in eff
    assert all(x.get("peer_name") for x in installs)
    # 型号关系
    models = [x for x in card["relations"] if x["rel_type"] == "型号为"]
    assert len(models) == 1
    assert models[0]["effective_from"] == "2020-01-01"


def test_8_object_card_processes_roles(client, tokens):
    wo = obj_id_by_code(client, tokens["admin"], "WO")
    r = client.get(f"/api/objects/{wo}/card", headers=H(tokens["admin"]))
    roles = {p["process"]["code"]: p["role_in_process"]
             for p in r.json()["processes"]}
    assert roles.get("WO-PROC") == "产生"
    peq = obj_id_by_code(client, tokens["admin"], "P-EQ")
    r = client.get(f"/api/objects/{peq}/card", headers=H(tokens["admin"]))
    roles = {p["process"]["code"]: p["role_in_process"]
             for p in r.json()["processes"]}
    assert roles.get("WO-PROC") == "使用"
    # P-EQ 卡片含服务与指标占位、标准（经资源关联）
    assert any(s["name"] == "设备关系查询服务" for s in r.json()["services"])
    assert any(s["code"] == "STD-001" for s in r.json()["standards"])


# ---------- 资源提交→审批→发布完整流 ----------

def _res_by_code(client, token, code):
    r = client.get("/api/resources", params={"q": code}, headers=H(token))
    assert r.status_code == 200
    for x in r.json():
        if x["res_code"] == code:
            return x
    raise AssertionError(f"resource {code} not found")


def test_9_resource_submit_approve_publish(client, tokens):
    admin, op = H(tokens["admin"]), H(tokens["weixiu"])
    res = _res_by_code(client, tokens["admin"], "RES-003")
    assert res["status"] == "已登记"
    # 提交
    r = client.post(f"/api/resources/{res['id']}/submit", headers=op)
    assert r.status_code == 200
    approval_id = r.json()["approval_id"]
    r = client.get(f"/api/resources/{res['id']}", headers=admin)
    assert r.json()["status"] == "技术核验中"
    # 审批单两步
    r = client.get(f"/api/approvals/{approval_id}", headers=admin)
    steps = r.json()["steps"]
    assert [s["step_name"] for s in steps] == ["技术核验", "归口审核"]
    # 步骤1通过 → 审核中，进入步骤2
    r = client.post(f"/api/approvals/{approval_id}/decide", headers=admin,
                    json={"decision": "通过", "comment": "技术核验通过"})
    assert r.status_code == 200
    assert r.json()["current_step"] == 2
    r = client.get(f"/api/resources/{res['id']}", headers=admin)
    assert r.json()["status"] == "审核中"
    # 步骤2通过 → 已发布
    r = client.post(f"/api/approvals/{approval_id}/decide", headers=admin,
                    json={"decision": "通过", "comment": "同意发布"})
    assert r.status_code == 200
    assert r.json()["status"] == "已通过"
    r = client.get(f"/api/resources/{res['id']}", headers=admin)
    assert r.json()["status"] == "已发布"


def test_10_offline_blocked_by_service(client, tokens):
    admin = H(tokens["admin"])
    res = _res_by_code(client, tokens["admin"], "RES-001")  # 对象 P-EQ 有已发布服务
    r = client.post(f"/api/resources/{res['id']}/offline", headers=admin)
    assert r.status_code == 400
    deps = r.json()["detail"]["dependencies"]
    assert any(d["name"] == "设备关系查询服务" for d in deps)


def test_11_offline_success_no_ref(client, tokens):
    admin = H(tokens["admin"])
    r = client.post("/api/resources", headers=admin,
                    json={"res_code": "RES-T1", "name": "测试资源",
                          "source_system": "测试系统"})
    assert r.status_code == 200
    rid = r.json()["id"]
    r = client.post(f"/api/resources/{rid}/offline", headers=admin)
    assert r.status_code == 200
    r = client.get(f"/api/resources/{rid}", headers=admin)
    assert r.json()["status"] == "已下架"


# ---------- 标准提交与驳回回退 ----------

def test_12_standard_submit_and_reject(client, tokens):
    admin = H(tokens["admin"])
    r = client.post("/api/standards", headers=admin,
                    json={"code": "STD-T1", "name": "测试标准",
                          "std_type": "字段类", "version": "v0.1"})
    assert r.status_code == 200
    sid = r.json()["id"]
    assert r.json()["status"] == "草稿"
    r = client.post(f"/api/standards/{sid}/submit", headers=admin)
    assert r.status_code == 200
    approval_id = r.json()["approval_id"]
    r = client.get(f"/api/standards/{sid}", headers=admin)
    assert r.json()["status"] == "审批中"
    # 驳回 → 审批单已驳回，标准回退草稿
    r = client.post(f"/api/approvals/{approval_id}/decide", headers=admin,
                    json={"decision": "驳回", "comment": "定义不完整"})
    assert r.status_code == 200
    assert r.json()["status"] == "已驳回"
    r = client.get(f"/api/standards/{sid}", headers=admin)
    assert r.json()["status"] == "草稿"


# ---------- 审批待办 ----------

def test_13_todo_admin_sees_seed_approval(client, tokens):
    r = client.get("/api/approvals", params={"todo": 1},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    items = r.json()
    assert any("STD-003" in x["title"] and x["status"] == "待审批"
               for x in items)


def test_14_todo_operator_only_own(client, tokens):
    r = client.get("/api/approvals", params={"todo": 1},
                   headers=H(tokens["weixiu"]))
    assert r.status_code == 200
    assert all(x["applicant"] == "weixiu" for x in r.json())


# ---------- 认责矩阵 ----------

def test_15_responsibilities_query(client, tokens):
    wo = obj_id_by_code(client, tokens["admin"], "WO")
    r = client.get("/api/responsibilities", params={"object_id": wo},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    rows = r.json()
    eq = [x for x in rows if x["field_name"] == "设备编码"][0]
    assert eq["business_owner_dept"] == "设备部"
    assert eq["data_steward"] == "设备部数据专员"
    assert eq["input_role"] == "维修班长"
    assert eq["object_code"] == "WO"


# ---------- 质量问题自动派发 ----------

def test_16_quality_auto_assign_business(client, tokens):
    wo = obj_id_by_code(client, tokens["admin"], "WO")
    r = client.post("/api/quality", headers=H(tokens["weixiu"]),
                    json={"title": "测试缺码", "issue_type": "缺码",
                          "object_id": wo})
    assert r.status_code == 200
    assert r.json()["assignee"] == "设备部数据专员"


def test_17_quality_auto_assign_sync_fail(client, tokens):
    wo = obj_id_by_code(client, tokens["admin"], "WO")
    r = client.post("/api/quality", headers=H(tokens["weixiu"]),
                    json={"title": "测试同步失败", "issue_type": "同步失败",
                          "object_id": wo})
    assert r.status_code == 200
    assert r.json()["assignee"] == "信息中心"


def test_18_quality_status_update(client, tokens):
    r = client.get("/api/quality", params={"status": "待确认"},
                   headers=H(tokens["admin"]))
    qid = r.json()[0]["id"]
    r = client.put(f"/api/quality/{qid}", headers=H(tokens["weixiu"]),
                   json={"status": "整改中"})
    assert r.status_code == 200
    assert r.json()["status"] == "整改中"


# ---------- 审计 ----------

def test_19_audit_log_written(client, tokens):
    r = client.get("/api/audit", params={"action": "创建对象"},
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(i["username"] == "weixiu" for i in body["items"])
    # readonly 无权查看审计
    r = client.get("/api/audit", headers=H(tokens["audit"]))
    assert r.status_code == 403


# ---------- 工作台 ----------

def test_20_dashboard(client, tokens):
    r = client.get("/api/dashboard", headers=H(tokens["admin"]))
    assert r.status_code == 200
    d = r.json()
    for key in ["todo_count", "objects_count", "resources_published",
                "standards_published", "open_issues"]:
        assert key in d
    assert d["objects_count"] >= 5
    assert d["standards_published"] >= 2
    assert d["resources_published"] >= 2
    assert d["open_issues"] >= 3


# ---------- 删除权限 ----------

def test_21_operator_cannot_delete_object(client, tokens):
    wo = obj_id_by_code(client, tokens["admin"], "WO")
    r = client.delete(f"/api/objects/{wo}", headers=H(tokens["weixiu"]))
    assert r.status_code == 403


def test_22_admin_delete_object(client, tokens):
    oid = obj_id_by_code(client, tokens["admin"], "T-OBJ")
    r = client.delete(f"/api/objects/{oid}", headers=H(tokens["admin"]))
    assert r.status_code == 200
    r = client.get(f"/api/objects/{oid}", headers=H(tokens["admin"]))
    assert r.status_code == 404


# ---------- 流程与落标 ----------

def test_23_process_nodes(client, tokens):
    r = client.get("/api/processes", headers=H(tokens["admin"]))
    proc = [p for p in r.json() if p["code"] == "WO-PROC"][0]
    r = client.get(f"/api/processes/{proc['id']}",
                   headers=H(tokens["admin"]))
    nodes = r.json()["nodes"]
    assert len(nodes) == 3
    n1 = [n for n in nodes if n["seq"] == 1][0]
    assert n1["node_name"] == "报修"
    assert n1["produces_data"] == "维修工单"
    assert n1["input_role"] == "维修班长"
    assert n1["review_role"] == "维修主管"


def test_24_standard_adoption(client, tokens):
    r = client.get("/api/standards", params={"q": "STD-001"},
                   headers=H(tokens["admin"]))
    sid = [s for s in r.json() if s["code"] == "STD-001"][0]["id"]
    r = client.get(f"/api/standards/{sid}/adoption",
                   headers=H(tokens["admin"]))
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3
    wms = [x for x in rows if x["system_name"] == "维修管理系统"][0]
    assert wms["status"] == "有差异"
    assert wms["diff_desc"] == "历史数据存在空值"
