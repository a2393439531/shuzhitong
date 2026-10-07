"""确定性种子数据：核电试点（设备—维修工单—备件链路）。原创数据组织。"""
import json

from .auth import hash_password
from .database import get_conn
from .deps import now_str
from .seed_phase2 import seed_phase2


def seed() -> None:
    conn = get_conn()
    try:
        exists = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if not exists:  # 已灌过则一期幂等跳过；二期种子始终执行
            now = now_str()
            cur = conn.cursor()

            # ---------- 用户 ----------
            users = [
                ("admin", "Admin@123", "系统管理员", "super_admin", "信息中心"),
                ("heping", "Heping@123", "何平", "admin", "设备部"),
                ("weixiu", "Weixiu@123", "维修员", "operator", "维修处"),
                ("audit", "Audit@123", "审计员", "readonly", "审计部"),
            ]
            for username, pwd, real_name, role, dept in users:
                ph, salt = hash_password(pwd)
                cur.execute(
                    """INSERT INTO users
                       (username, password_hash, salt, real_name, role, dept, is_active, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                    (username, ph, salt, real_name, role, dept, now),
                )

            # ---------- 业务领域 ----------
            domains = [
                ("DOM-EQ", "设备管理", "设备部", "电站设备全生命周期管理"),
                ("DOM-WO", "维修管理", "设备部", "设备维修工单与检修管理"),
                ("DOM-MAT", "物资管理", "物资部", "备件物料采购仓储管理"),
            ]
            domain_ids = {}
            for code, name, owner_dept, desc in domains:
                cur.execute(
                    "INSERT INTO domains (code, name, owner_dept, description) VALUES (?, ?, ?, ?)",
                    (code, name, owner_dept, desc),
                )
                domain_ids[code] = cur.lastrowid

            # ---------- 业务对象 ----------
            objects = [
                ("L-EQ", "逻辑设备", "电站功能位置，标识设备安装的逻辑位置",
                 "DOM-EQ", "设备部", "逻辑位置编码规则：机组-系统-设备序号"),
                ("M-EQ", "型号设备", "设备型号规格，同一型号可对应多台物理设备",
                 "DOM-EQ", "设备部", "型号编码规则"),
                ("P-EQ", "物理设备", "现场实际安装的单台设备实体",
                 "DOM-EQ", "设备部", "物理设备编码规则"),
                ("WO", "维修工单", "设备维修作业的工单记录",
                 "DOM-WO", "设备部", "工单编号规则：年度+流水号"),
                ("MAT", "备件物料", "维修备件与物料主数据",
                 "DOM-MAT", "物资部", "物料统一编码规则"),
            ]
            obj_ids = {}
            for code, name, definition, dom, owner_dept, uid in objects:
                cur.execute(
                    """INSERT INTO biz_objects
                       (code, name, definition, domain_id, owner_dept, unique_id_desc, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (code, name, definition, domain_ids[dom], owner_dept, uid, now),
                )
                obj_ids[code] = cur.lastrowid

            # ---------- 对象属性 ----------
            attrs = [
                ("L-EQ", "位置编码", "文本", 1, "逻辑位置唯一编码"),
                ("L-EQ", "所属系统", "文本", 0, "所属工艺系统"),
                ("M-EQ", "型号编码", "文本", 1, "设备型号唯一编码"),
                ("M-EQ", "技术规格", "文本", 0, "型号技术规格说明"),
                ("P-EQ", "设备编码", "文本", 1, "物理设备唯一编码"),
                ("P-EQ", "核安全分级", "枚举", 0, "NS1/NS2/NS3/非核级"),
                ("P-EQ", "安装位置", "文本", 0, "当前安装的逻辑位置"),
                ("WO", "工单编号", "文本", 1, "工单唯一编号"),
                ("WO", "设备编码", "文本", 0, "关联的物理设备编码"),
                ("WO", "报修时间", "日期时间", 0, "报修发起时间"),
                ("WO", "完工时间", "日期时间", 0, "维修完工确认时间"),
                ("WO", "工单状态", "枚举", 0, "待处理/处理中/已完工/已关闭"),
                ("MAT", "物料编码", "文本", 1, "物料统一编码"),
                ("MAT", "技术参数", "文本", 0, "物料技术参数说明"),
                ("MAT", "采购属性", "文本", 0, "采购相关属性"),
                ("MAT", "统一编码", "文本", 0, "物资编码组织分配的统一编码"),
            ]
            for code, name, dtype, is_key, desc in attrs:
                cur.execute(
                    """INSERT INTO object_attrs (object_id, name, data_type, is_key, description)
                       VALUES (?, ?, ?, ?, ?)""",
                    (obj_ids[code], name, dtype, is_key, desc),
                )

            # ---------- 三码关系（带有效时间） ----------
            relations = [
                ("L-EQ", "M-EQ", "型号为",
                 "1号机辅助给水泵位置 L-AFW-001 的型号为辅助给水泵 AFW-1000",
                 "2020-01-01", None),
                ("L-EQ", "P-EQ", "安装",
                 "1号机辅助给水泵位置 L-AFW-001 安装物理设备给水泵 P-AFW-001A",
                 "2020-01-01", "2025-05-31"),
                ("L-EQ", "P-EQ", "安装",
                 "1号机辅助给水泵位置 L-AFW-001 安装物理设备给水泵 P-AFW-001B（替换 P-AFW-001A）",
                 "2025-06-01", None),
            ]
            for f, t, rel_type, desc, eff_from, eff_to in relations:
                cur.execute(
                    """INSERT INTO object_relations
                       (from_object_id, to_object_id, rel_type, description, effective_from, effective_to)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (obj_ids[f], obj_ids[t], rel_type, desc, eff_from, eff_to),
                )

            # ---------- 业务流程 ----------
            cur.execute(
                """INSERT INTO processes (code, name, domain_id, owner_dept, description)
                   VALUES (?, ?, ?, ?, ?)""",
                ("WO-PROC", "设备维修流程", domain_ids["DOM-WO"], "设备部",
                 "从报修、领料到完工确认的设备维修全流程"),
            )
            proc_id = cur.lastrowid
            nodes = [
                (1, "报修", "维修工单", "设备台账", "维修班长", "维修主管", "设备编码存在性检查"),
                (2, "领料", "领料记录", "备件库存", "仓管员", "物资主管", "物料编码有效性+库存充足"),
                (3, "完工确认", "完工报告", "维修工单", "维修工程师", "设备专工", "工单必填项完整"),
            ]
            for seq, name, produces, uses, inp, review, rules in nodes:
                cur.execute(
                    """INSERT INTO process_nodes
                       (process_id, seq, node_name, produces_data, uses_data, input_role, review_role, check_rules)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (proc_id, seq, name, produces, uses, inp, review, rules),
                )

            # ---------- 对象—流程关联 ----------
            for code, role_in in [("WO", "产生"), ("P-EQ", "使用"), ("MAT", "使用")]:
                cur.execute(
                    "INSERT INTO object_processes (object_id, process_id, role_in_process) VALUES (?, ?, ?)",
                    (obj_ids[code], proc_id, role_in),
                )

            # ---------- 数据标准 ----------
            std_check = json.dumps({
                "值域检查": "取值为NS1/NS2/NS3/非核级",
                "适用性检查": "核岛设备必填",
                "来源完整性检查": "分级变更须附设计变更单",
            }, ensure_ascii=False)
            standards = [
                ("STD-001", "设备核安全分级", "编码类", "v1.0", "已发布",
                 "按核安全重要性划分的设备分级",
                 json.dumps(["NS1", "NS2", "NS3", "非核级"], ensure_ascii=False),
                 "设计文件", "核安全部", "核安全工程师", std_check,
                 "分级变更须经核安全部审批", "2024-01-01"),
                ("STD-002", "设备编码规则", "字段类", "v1.0", "已发布",
                 "物理设备编码编制规则",
                 json.dumps(["机组代码+系统代码+设备序号"], ensure_ascii=False),
                 "设备编码规范", "设备部", "设备专工",
                 json.dumps({"格式检查": "编码符合既定格式"}, ensure_ascii=False),
                 "编码规则变更须经设备部审批", "2024-01-01"),
                ("STD-003", "物料编码规则", "编码类", "v0.1", "草稿",
                 "备件物料统一编码编制规则", None,
                 "物资编码规范", "物资部", "物资编码员", None,
                 "编码规则变更须经物资编码组织审批", None),
            ]
            std_ids = {}
            for (code, name, stype, ver, status, bdef, allowed, auth_src,
                 owner_dept, owner_role, rules, change_req, eff_date) in standards:
                cur.execute(
                    """INSERT INTO standards
                       (code, name, std_type, version, status, business_def, allowed_values,
                        authority_source, owner_dept, owner_role, check_rules,
                        change_requirement, effective_date, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (code, name, stype, ver, status, bdef, allowed, auth_src,
                     owner_dept, owner_role, rules, change_req, eff_date, now),
                )
                std_ids[code] = cur.lastrowid

            cur.execute(
                """INSERT INTO std_versions (standard_id, version, change_desc, created_at)
                   VALUES (?, ?, ?, ?)""",
                (std_ids["STD-001"], "v1.0", "初始发布", now),
            )

            # ---------- 落标情况 ----------
            for sys_name, status, diff in [
                ("DCS系统", "已落标", None),
                ("维修管理系统", "有差异", "历史数据存在空值"),
                ("物资系统", "未接入", None),
            ]:
                cur.execute(
                    """INSERT INTO std_adoption (standard_id, system_name, status, diff_desc)
                       VALUES (?, ?, ?, ?)""",
                    (std_ids["STD-001"], sys_name, status, diff),
                )

            # ---------- 数据资源目录 ----------
            resources = [
                ("RES-001", "设备台账", "DOM-EQ", "P-EQ", "设备管理系统", "EQ_EQUIPMENT",
                 "设备编码/核安全分级/安装位置", "设备管理系统→数据中台", "设备部",
                 json.dumps([std_ids["STD-001"], std_ids["STD-002"]]),
                 "日", "良好", "内部共享", "API+库表", "已发布", "全厂设备台账主数据"),
                ("RES-002", "维修工单记录", "DOM-WO", "WO", "维修管理系统", "WO_ORDER",
                 "工单编号/设备编码/报修时间/完工时间", "维修管理系统→数据中台", "设备部",
                 json.dumps([]), "日", "良好", "内部共享", "API", "已发布", "设备维修工单记录"),
                ("RES-003", "领料记录", "DOM-MAT", "MAT", "物资管理系统", "MAT_ISSUE",
                 "领料单号/物料编码/领料数量", "物资管理系统→数据中台", "物资部",
                 json.dumps([std_ids["STD-003"]]), "日", "待核验", "部门内", "库表", "已登记", "维修领料记录"),
                ("RES-004", "维修费用结算", "DOM-WO", "WO", "财务系统", "FIN_WO_COST",
                 "工单编号/费用明细", "财务系统→数据中台", "财务部",
                 json.dumps([]), "月", "待核验", "部门内", "文件", "技术核验中", "维修费用结算数据"),
            ]
            res_ids = {}
            for (code, name, dom, obj, src_sys, table, fields, lineage, auth_src,
                 rel_std, freq, qstat, scope, mode, status, desc) in resources:
                cur.execute(
                    """INSERT INTO resources
                       (res_code, name, domain_id, object_id, source_system, table_or_api,
                        fields_desc, lineage, authority_source, owner_dept, related_standards,
                        update_freq, quality_status, access_scope, service_mode, status,
                        description, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (code, name, domain_ids[dom], obj_ids[obj], src_sys, table,
                     fields, lineage, auth_src, {"DOM-EQ": "设备部", "DOM-WO": "设备部",
                                                "DOM-MAT": "物资部"}[dom],
                     rel_std, freq, qstat, scope, mode, status, desc, now),
                )
                res_ids[code] = cur.lastrowid

            # ---------- 认责矩阵（字段—流程—责任） ----------
            resps = [
                ("WO", "设备编码", "设备部", "设备台账", proc_id,
                 "维修班长", "维修主管", "设备部数据专员", "信息中心", "设备部", None, None, None),
                ("MAT", "技术参数", "设备部", "设计文件", None,
                 "设备专工", "设备主管", "设备部数据专员", "信息中心", "设备部", None, None, None),
                ("MAT", "采购属性", "采购部", "采购订单", None,
                 "采购员", "采购主管", "采购部数据专员", "信息中心", "采购部", None, None, None),
                ("MAT", "统一编码", "物资编码组织", "物资编码规范", None,
                 "物资编码员", "物资主管", "物资编码组织专员", "信息中心", "物资部", None, None, None),
                ("WO", "完工时间", "设备部", "维修工单", proc_id,
                 "维修工程师", "设备专工", "设备部数据专员", "信息中心", "设备部", None, None, None),
                ("P-EQ", "核安全分级", "核安全部", "设计文件", None,
                 "设备专工", "核安全工程师", "设备部数据专员", "信息中心", "设备部", None, None, None),
                ("P-EQ", "设备编码", "设备部", "设备台账", None,
                 "设备专工", "设备主管", "设备部数据专员", "信息中心", "设备部", None, None, None),
            ]
            for (obj, field, dept, auth_src, spid, inp, review,
                 steward, tech, org, vf, vt, agent) in resps:
                cur.execute(
                    """INSERT INTO responsibilities
                       (object_id, field_name, business_owner_dept, authority_source,
                        source_process_id, input_role, review_role, data_steward,
                        tech_owner, org_unit, valid_from, valid_to, agent_for)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (obj_ids[obj], field, dept, auth_src, spid, inp, review,
                     steward, tech, org, vf, vt, agent),
                )

            # ---------- 质量问题 ----------
            issues = [
                ("QI-001 维修工单存在设备编码缺码", "缺码", "WO", None, "设备部数据专员", "待确认"),
                ("QI-002 领料记录物料编码无法关联主数据", "无法关联", "MAT", res_ids["RES-003"],
                 "物资编码组织专员", "整改中"),
                ("QI-003 设备台账存在重复物理设备记录", "重复记录", "P-EQ", res_ids["RES-001"],
                 "设备部数据专员", "待确认"),
            ]
            for title, itype, obj, rid, assignee, status in issues:
                cur.execute(
                    """INSERT INTO quality_issues
                       (title, issue_type, object_id, resource_id, assignee, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (title, itype, obj_ids[obj], rid, assignee, status, now),
                )

            # ---------- 服务占位 ----------
            for name, obj, ver, status in [
                ("设备关系查询服务", "P-EQ", "v1.0", "已发布"),
                ("工单明细查询服务", "WO", "v1.0", "已发布"),
            ]:
                cur.execute(
                    """INSERT INTO services (name, object_id, description, version, status)
                       VALUES (?, ?, ?, ?, ?)""",
                    (name, obj_ids[obj], f"{name}（占位）", ver, status),
                )

            # ---------- 指标占位 ----------
            for name, obj, formula in [
                ("维修工单按期完成率", "WO", "按期完工工单数/工单总数"),
                ("备件消耗统计", "MAT", "按物料分类汇总领用数量"),
                ("设备完好率", "P-EQ", "完好设备数/设备总数"),
            ]:
                cur.execute(
                    """INSERT INTO indicators (name, object_id, formula_desc, version, status)
                       VALUES (?, ?, ?, ?, ?)""",
                    (name, obj_ids[obj], formula, "v1.0", "草稿"),
                )

            # ---------- 审批示例：STD-003 待审批（给 admin 留待办） ----------
            cur.execute(
                """INSERT INTO approvals
                   (biz_type, biz_id, title, applicant, status, current_step, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("标准发布", std_ids["STD-003"], "标准发布审批：STD-003 物料编码规则",
                 "heping", "待审批", 1, now),
            )
            appr_id = cur.lastrowid
            cur.execute(
                """INSERT INTO approval_steps
                   (approval_id, seq, step_name, approver_role, approver, decision, comment, acted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (appr_id, 1, "归口审核", "admin", None, "待定", None, None),
            )
            cur.execute("UPDATE standards SET status = '审批中' WHERE id = ?",
                        (std_ids["STD-003"],))

        conn.commit()
    finally:
        conn.close()
    seed_phase2()  # 二期种子（各表为空才灌；即使一期已灌过也会执行）
