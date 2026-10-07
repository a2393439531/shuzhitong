"""二期种子数据：主数据模型、演示台账（脏数据）、质量规则、字段映射。幂等。"""
import json
from datetime import datetime, timedelta

from .database import get_conn
from .deps import now_str


def _count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]


def _obj_id(conn, code: str):
    row = conn.execute(
        "SELECT id FROM biz_objects WHERE code = ?", (code,)
    ).fetchone()
    return row["id"] if row else None


def _std_id(conn, code: str):
    row = conn.execute(
        "SELECT id FROM standards WHERE code = ?", (code,)
    ).fetchone()
    return row["id"] if row else None


def seed_phase2() -> None:
    conn = get_conn()
    try:
        now = now_str()
        peq_id = _obj_id(conn, "P-EQ")
        mat_id = _obj_id(conn, "MAT")
        std1 = _std_id(conn, "STD-001")

        # ---------- 主数据模型 ----------
        if _count(conn, "md_models") == 0 and peq_id and mat_id:
            cur = conn.cursor()
            models = [
                (peq_id, "MD-EQ", "物理设备主数据", "EQ-",
                 "device_code", "已发布", "v1.0"),
                (mat_id, "MD-MAT", "备件物料主数据", "MAT-",
                 "mat_code", "已发布", "v1.0"),
            ]
            md_ids = {}
            for obj_id, code, name, id_rule, keys, status, ver in models:
                cur.execute(
                    """INSERT INTO md_models
                       (object_id, code, name, id_rule, key_fields, status, version, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (obj_id, code, name, id_rule, keys, status, ver, now),
                )
                md_ids[code] = cur.lastrowid

            # ---------- 演示台账（故意脏：完整性/唯一性/有效性/及时性各 1 例） ----------
            rows = [
                ("D-001", "辅助给水电动泵A", "AFW-1000", "NS1", "设备管理系统",
                 now),                                            # 正常
                ("D-002", "辅助给水电动泵B", "AFW-1000", "NS2", "设备管理系统",
                 now),                                            # 正常
                ("", "主给水电动泵", "MFW-2000", "NS1", "设备管理系统",
                 now),                                            # 完整性：编码为空
                ("D-003", "凝结水泵A", "CWP-500", "NS3", "设备管理系统",
                 now),                                            # 唯一性之一
                ("D-003", "凝结水泵A(重复)", "CWP-500", "NS3", "设备管理系统",
                 now),                                            # 唯一性之二
                ("D-004", "安全壳喷淋泵", "CSS-300", "N99", "设备管理系统",
                 now),                                            # 有效性：N99 不在分级值域
                ("D-005", "化学容积控制泵", "CVCS-100", "非核级", "设备管理系统",
                 (datetime.now() - timedelta(days=30)).strftime(
                     "%Y-%m-%d %H:%M:%S")),                      # 及时性：30 天未更新
                ("D-006", "设备冷却水泵", "CCW-400", "NS2", "设备管理系统",
                 now),                                            # 正常
            ]
            for dc, dn, mc, sc, sys, upd in rows:
                cur.execute(
                    """INSERT INTO demo_device_ledger
                       (device_code, device_name, model_code, safety_class,
                        source_system, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (dc, dn, mc, sc, sys, upd),
                )

            # ---------- 质量规则 ----------
            allowed = json.dumps(["NS1", "NS2", "NS3", "非核级"],
                                 ensure_ascii=False)
            rules = [
                ("设备编码完整性检查", peq_id, "demo_device_ledger", "device_code",
                 "完整性", "{}", "高", "业务"),
                ("设备编码唯一性检查", peq_id, "demo_device_ledger", "device_code",
                 "唯一性", "{}", "高", "业务"),
                ("核安全分级有效性检查", peq_id, "demo_device_ledger",
                 "safety_class", "有效性",
                 json.dumps({"allowed_values": json.loads(allowed)},
                            ensure_ascii=False), "高", "业务"),
                ("台账更新及时性检查", peq_id, "demo_device_ledger", "updated_at",
                 "及时性", json.dumps({"hours": 168}, ensure_ascii=False),
                 "中", "技术"),
            ]
            for name, oid, table, field, rtype, params, sev, atype in rules:
                cur.execute(
                    """INSERT INTO quality_rules
                       (name, object_id, target_table, target_field, rule_type,
                        params, severity, is_enabled, assignee_type, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                    (name, oid, table, field, rtype, params, sev, atype, now),
                )

            # ---------- 字段映射示例 ----------
            mappings = [
                ("设备管理系统", "EQ_EQUIPMENT", "safety_grade", std1, None, "",
                 peq_id, "源系统安全分级字段映射到核安全分级标准"),
                ("设备管理系统", "EQ_EQUIPMENT", "device_code", None,
                 md_ids["MD-EQ"], "device_code", peq_id,
                 "源系统设备编码映射到物理设备主数据属性"),
                ("维修管理系统", "WO_ORDER", "device_code", None,
                 md_ids["MD-EQ"], "device_code", peq_id,
                 "工单系统设备编码映射到物理设备主数据属性"),
            ]
            for (sys, table, field, sid, mid, attr, oid, remark) in mappings:
                cur.execute(
                    """INSERT INTO field_mappings
                       (source_system, source_table, source_field, standard_id,
                        md_model_id, md_attr, object_id, remark, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (sys, table, field, sid, mid, attr, oid, remark, now),
                )

        # ---------- 认责补行：field_name=safety_class（供规则自动派发） ----------
        if peq_id:
            has = conn.execute(
                """SELECT 1 FROM responsibilities
                   WHERE object_id = ? AND field_name = 'safety_class'""",
                (peq_id,),
            ).fetchone()
            if has is None:
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO responsibilities
                       (object_id, field_name, business_owner_dept, authority_source,
                        source_process_id, input_role, review_role, data_steward,
                        tech_owner, org_unit, valid_from, valid_to, agent_for)
                       VALUES (?, 'safety_class', '核安全部', '设计文件', NULL,
                               '设备专工', '核安全工程师', '设备部数据专员',
                               '信息中心', '设备部', NULL, NULL, NULL)""",
                    (peq_id,),
                )
        conn.commit()
    finally:
        conn.close()
