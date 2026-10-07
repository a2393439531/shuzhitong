"""三期种子：5 个统一数据服务。原创实现。

幂等：按 code 做 upsert（一期占位行的 code 为 NULL，保留不动）；
每个服务补 service_versions（v1.0，初始发布）与 service_notices（一行“服务已发布”）。

注意：本文件不被 main.py / seed.py 引用（任务约束禁止改动），由调用方
在合适时机执行 seed_services()。
"""
from .database import get_conn
from .deps import now_str

SEED_SERVICES = [
    {
        "code": "SVC-MD-EQ",
        "name": "设备主数据查询服务",
        "svc_type": "master",
        "description": "查询主数据平台已发布的主数据记录，支持按主数据编码/模型编码过滤",
        "object_id": None,
        "data_source": "主数据平台/设备台账",
        "standard_version": "STD-001 v2.0",
        "owner": "何平",
        "permission_req": "公开",
        "quality_status": "正常",
        "update_freq": "每日",
        "api_version": "v1.0",
        "endpoint_path": "/api/services/SVC-MD-EQ/invoke",
    },
    {
        "code": "SVC-REL-3CODE",
        "name": "设备三码关系查询服务",
        "svc_type": "relation",
        "description": "按逻辑设备编码查询指定时点的三码对应关系（逻辑码/型号码/物理码）",
        "object_id": None,
        "data_source": "主数据平台/设备台账",
        "standard_version": "STD-001 v2.0",
        "owner": "何平",
        "permission_req": "公开",
        "quality_status": "正常",
        "update_freq": "每日",
        "api_version": "v1.0",
        "endpoint_path": "/api/services/SVC-REL-3CODE/invoke",
    },
    {
        "code": "SVC-WO-DETAIL",
        "name": "维修工单明细查询服务",
        "svc_type": "detail",
        "description": "按基地/型号/时间范围查询维修工单明细，部门级行数据范围",
        "object_id": None,
        "data_source": "主数据平台/设备台账",
        "standard_version": "STD-001 v2.0",
        "owner": "何平",
        "permission_req": "授权",
        "quality_status": "正常",
        "update_freq": "每日",
        "api_version": "v1.0",
        "endpoint_path": "/api/services/SVC-WO-DETAIL/invoke",
    },
    {
        "code": "SVC-MAT-COST",
        "name": "备件消耗组合分析服务",
        "svc_type": "combo",
        "description": "按设备型号汇总物料领用次数与金额（组合分析）",
        "object_id": None,
        "data_source": "主数据平台/设备台账",
        "standard_version": "STD-001 v2.0",
        "owner": "何平",
        "permission_req": "授权",
        "quality_status": "正常",
        "update_freq": "每日",
        "api_version": "v1.0",
        "endpoint_path": "/api/services/SVC-MAT-COST/invoke",
    },
    {
        "code": "SVC-CODE-VALIDATE",
        "name": "数据标准值域校验服务",
        "svc_type": "validate",
        "description": "按数据标准编码校验字段值是否在允许值域内",
        "object_id": None,
        "data_source": "主数据平台/设备台账",
        "standard_version": "STD-001 v2.0",
        "owner": "何平",
        "permission_req": "公开",
        "quality_status": "正常",
        "update_freq": "每日",
        "api_version": "v1.0",
        "endpoint_path": "/api/services/SVC-CODE-VALIDATE/invoke",
    },
]

_SVC_COLS = ("code, name, svc_type, description, object_id, data_source,"
             " standard_version, owner, permission_req, quality_status,"
             " update_freq, api_version, endpoint_path")


def seed_services() -> None:
    conn = get_conn()
    try:
        now = now_str()
        cur = conn.cursor()
        for s in SEED_SERVICES:
            row = conn.execute(
                "SELECT id, name FROM services WHERE code = ?", (s["code"],)
            ).fetchone()
            if row is None:
                cur.execute(
                    f"""INSERT INTO services
                       ({_SVC_COLS}, version, status, created_by, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '已发布', 'seed', ?)""",
                    (s["code"], s["name"], s["svc_type"], s["description"],
                     s["object_id"], s["data_source"], s["standard_version"],
                     s["owner"], s["permission_req"], s["quality_status"],
                     s["update_freq"], s["api_version"], s["endpoint_path"],
                     s["api_version"], now),
                )
                service_id = cur.lastrowid
            else:
                service_id = row["id"]
                cur.execute(
                    """UPDATE services
                       SET name = ?, svc_type = ?, description = ?,
                           object_id = ?, data_source = ?,
                           standard_version = ?, owner = ?,
                           permission_req = ?, quality_status = ?,
                           update_freq = ?, api_version = ?,
                           endpoint_path = ?, version = ?,
                           status = '已发布'
                       WHERE id = ?""",
                    (s["name"], s["svc_type"], s["description"], s["object_id"],
                     s["data_source"], s["standard_version"], s["owner"],
                     s["permission_req"], s["quality_status"], s["update_freq"],
                     s["api_version"], s["endpoint_path"], s["api_version"],
                     service_id),
                )
            # 版本记录（v1.0，初始发布）：不存在才写
            has_ver = conn.execute(
                """SELECT 1 FROM service_versions
                   WHERE service_id = ? AND version = 'v1.0'""",
                (service_id,)).fetchone()
            if has_ver is None:
                cur.execute(
                    """INSERT INTO service_versions
                       (service_id, version, change_desc, created_at)
                       VALUES (?, 'v1.0', '初始发布', ?)""",
                    (service_id, now),
                )
            # 通知：不存在才写
            content = f"服务「{s['name']}」已发布，版本 v1.0"
            has_notice = conn.execute(
                """SELECT 1 FROM service_notices
                   WHERE service_id = ? AND content = ?""",
                (service_id, content)).fetchone()
            if has_notice is None:
                cur.execute(
                    """INSERT INTO service_notices
                       (service_id, version, content, created_at)
                       VALUES (?, 'v1.0', ?, ?)""",
                    (service_id, content, now),
                )
        conn.commit()
    finally:
        conn.close()
