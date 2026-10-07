"""数据库抽象：SQLAlchemy 引擎（SQLite / PostgreSQL 双兼容）。

设计说明：
- 全部表结构用 SQLAlchemy Model 声明（一期 19 张表，二期表由各模块追加），
  建表走 ``Base.metadata.create_all()``，两种数据库同一套定义。
- 为兼容一期既有 routers（raw SQL + ``?`` 占位符 + ``get_conn()``），本模块
  提供一套轻量兼容层：``get_conn()`` 返回的连接支持
  ``execute(sql, params) / cursor() / commit() / close()``，``?`` 自动翻译为
  各方言参数风格，行对象支持 ``row["col"]`` 与 ``dict(row)``。
- 新表直接用 Model；新代码推荐用兼容层写 SQL（两种库通用）。
- 既有表新增列走 ``EXTRA_COLUMNS`` 轻量迁移（两种库通用），不手写 ALTER。

原创实现。
"""
import re

from sqlalchemy import Column, Integer, String, create_engine, text as sa_text
from sqlalchemy.orm import declarative_base

from .config import settings

Base = declarative_base()

# ================= 一期表结构（与旧 DDL 逐列对应） =================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    salt = Column(String, nullable=False)
    real_name = Column(String)
    role = Column(String, nullable=False)
    dept = Column(String)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(String, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    username = Column(String)
    action = Column(String, nullable=False)
    detail = Column(String)
    ip = Column(String)
    elapsed_ms = Column(Integer, nullable=False, default=0)
    result = Column(String, nullable=False, default="成功")
    created_at = Column(String, nullable=False)


class Domain(Base):
    __tablename__ = "domains"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    owner_dept = Column(String)
    description = Column(String)


class BizObject(Base):
    __tablename__ = "biz_objects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    definition = Column(String)
    domain_id = Column(Integer)
    owner_dept = Column(String)
    unique_id_desc = Column(String)
    created_at = Column(String, nullable=False)


class ObjectAttr(Base):
    __tablename__ = "object_attrs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    object_id = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    data_type = Column(String)
    is_key = Column(Integer, nullable=False, default=0)
    description = Column(String)


class ObjectRelation(Base):
    __tablename__ = "object_relations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    from_object_id = Column(Integer, nullable=False)
    to_object_id = Column(Integer, nullable=False)
    rel_type = Column(String, nullable=False)
    description = Column(String)
    effective_from = Column(String)
    effective_to = Column(String)


class Process(Base):
    __tablename__ = "processes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    domain_id = Column(Integer)
    owner_dept = Column(String)
    description = Column(String)


class ProcessNode(Base):
    __tablename__ = "process_nodes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    process_id = Column(Integer, nullable=False)
    seq = Column(Integer, nullable=False)
    node_name = Column(String, nullable=False)
    produces_data = Column(String)
    uses_data = Column(String)
    input_role = Column(String)
    review_role = Column(String)
    check_rules = Column(String)


class ObjectProcess(Base):
    __tablename__ = "object_processes"
    object_id = Column(Integer, primary_key=True)
    process_id = Column(Integer, primary_key=True)
    role_in_process = Column(String)


class Standard(Base):
    __tablename__ = "standards"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    std_type = Column(String)
    version = Column(String)
    status = Column(String, nullable=False, default="草稿")
    business_def = Column(String)
    allowed_values = Column(String)
    authority_source = Column(String)
    owner_dept = Column(String)
    owner_role = Column(String)
    check_rules = Column(String)
    change_requirement = Column(String)
    effective_date = Column(String)
    created_at = Column(String, nullable=False)


class StdVersion(Base):
    __tablename__ = "std_versions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    standard_id = Column(Integer, nullable=False)
    version = Column(String, nullable=False)
    change_desc = Column(String)
    created_at = Column(String, nullable=False)


class StdAdoption(Base):
    __tablename__ = "std_adoption"
    id = Column(Integer, primary_key=True, autoincrement=True)
    standard_id = Column(Integer, nullable=False)
    system_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    diff_desc = Column(String)


class Resource(Base):
    __tablename__ = "resources"
    id = Column(Integer, primary_key=True, autoincrement=True)
    res_code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    domain_id = Column(Integer)
    object_id = Column(Integer)
    source_system = Column(String)
    table_or_api = Column(String)
    fields_desc = Column(String)
    lineage = Column(String)
    authority_source = Column(String)
    owner_dept = Column(String)
    related_standards = Column(String)
    update_freq = Column(String)
    quality_status = Column(String)
    access_scope = Column(String)
    service_mode = Column(String)
    status = Column(String, nullable=False, default="已登记")
    description = Column(String)
    created_at = Column(String, nullable=False)


class Responsibility(Base):
    __tablename__ = "responsibilities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    object_id = Column(Integer, nullable=False)
    field_name = Column(String, nullable=False)
    business_owner_dept = Column(String)
    authority_source = Column(String)
    source_process_id = Column(Integer)
    input_role = Column(String)
    review_role = Column(String)
    data_steward = Column(String)
    tech_owner = Column(String)
    org_unit = Column(String)
    valid_from = Column(String)
    valid_to = Column(String)
    agent_for = Column(String)


class QualityIssue(Base):
    __tablename__ = "quality_issues"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    issue_type = Column(String)
    object_id = Column(Integer)
    resource_id = Column(Integer)
    assignee = Column(String)
    status = Column(String, nullable=False, default="待确认")
    created_at = Column(String, nullable=False)


class Approval(Base):
    __tablename__ = "approvals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    biz_type = Column(String, nullable=False)
    biz_id = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    applicant = Column(String)
    status = Column(String, nullable=False, default="待审批")
    current_step = Column(Integer, nullable=False, default=1)
    created_at = Column(String, nullable=False)


class ApprovalStep(Base):
    __tablename__ = "approval_steps"
    id = Column(Integer, primary_key=True, autoincrement=True)
    approval_id = Column(Integer, nullable=False)
    seq = Column(Integer, nullable=False)
    step_name = Column(String, nullable=False)
    approver_role = Column(String)
    approver = Column(String)
    decision = Column(String, nullable=False, default="待定")
    comment = Column(String)
    acted_at = Column(String)


class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    object_id = Column(Integer)
    description = Column(String)
    version = Column(String)
    status = Column(String)


class Indicator(Base):
    __tablename__ = "indicators"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    object_id = Column(Integer)
    formula_desc = Column(String)
    version = Column(String)
    status = Column(String)


# ================= 二期表结构（治理执行） =================

class MdModel(Base):
    __tablename__ = "md_models"
    id = Column(Integer, primary_key=True, autoincrement=True)
    object_id = Column(Integer)
    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    id_rule = Column(String)
    key_fields = Column(String)
    status = Column(String, nullable=False, default="草稿")
    version = Column(String)
    created_at = Column(String, nullable=False)


class MdRecord(Base):
    __tablename__ = "md_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, nullable=False)
    master_code = Column(String, nullable=False, unique=True)
    attrs = Column(String)
    source_system = Column(String)
    source_code = Column(String)
    status = Column(String, nullable=False, default="已发布")
    version = Column(Integer, nullable=False, default=1)
    effective_from = Column(String)
    effective_to = Column(String)
    created_at = Column(String, nullable=False)
    updated_at = Column(String)


class MdApplication(Base):
    __tablename__ = "md_applications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, nullable=False)
    app_type = Column(String, nullable=False)
    payload = Column(String)
    master_code = Column(String)
    merge_to_code = Column(String)
    reason = Column(String)
    status = Column(String, nullable=False, default="待审核")
    applicant = Column(String)
    reviewer = Column(String)
    review_comment = Column(String)
    created_at = Column(String, nullable=False)
    reviewed_at = Column(String)


class MdHistory(Base):
    __tablename__ = "md_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(Integer, nullable=False)
    version = Column(Integer, nullable=False)
    attrs = Column(String)
    change_desc = Column(String)
    changed_by = Column(String)
    created_at = Column(String, nullable=False)


class MdDistribution(Base):
    __tablename__ = "md_distributions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(Integer, nullable=False)
    target_system = Column(String, nullable=False)
    status = Column(String, nullable=False, default="成功")
    result_msg = Column(String)
    distributed_at = Column(String, nullable=False)


class MdCodeMap(Base):
    __tablename__ = "md_code_map"
    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, nullable=False)
    master_code = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    source_code = Column(String, nullable=False)


class DeviceLink(Base):
    __tablename__ = "device_links"
    id = Column(Integer, primary_key=True, autoincrement=True)
    logic_code = Column(String, nullable=False)
    model_code = Column(String, nullable=False)
    physical_code = Column(String, nullable=False)
    effective_from = Column(String, nullable=False)
    effective_to = Column(String)
    status = Column(String, nullable=False, default="有效")
    created_at = Column(String, nullable=False)


class FieldMapping(Base):
    __tablename__ = "field_mappings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_system = Column(String, nullable=False)
    source_table = Column(String)
    source_field = Column(String, nullable=False)
    standard_id = Column(Integer)
    md_model_id = Column(Integer)
    md_attr = Column(String)
    object_id = Column(Integer)
    remark = Column(String)
    created_at = Column(String, nullable=False)


class QualityRule(Base):
    __tablename__ = "quality_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    object_id = Column(Integer)
    target_table = Column(String, nullable=False)
    target_field = Column(String, nullable=False)
    rule_type = Column(String, nullable=False)
    params = Column(String)
    severity = Column(String)
    is_enabled = Column(Integer, nullable=False, default=1)
    assignee_type = Column(String, nullable=False, default="业务")
    created_at = Column(String, nullable=False)


class QualityRun(Base):
    __tablename__ = "quality_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="运行中")
    issue_count = Column(Integer, nullable=False, default=0)
    triggered_by = Column(String)
    message = Column(String)
    started_at = Column(String, nullable=False)
    finished_at = Column(String)


class RuleSchedule(Base):
    __tablename__ = "rule_schedules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, nullable=False, unique=True)
    cron_expr = Column(String)
    is_enabled = Column(Integer, nullable=False, default=1)
    last_run = Column(String)


class ComplianceCheck(Base):
    __tablename__ = "compliance_checks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    standard_id = Column(Integer, nullable=False)
    target_desc = Column(String)
    status = Column(String, nullable=False, default="完成")
    diff_count = Column(Integer, nullable=False, default=0)
    result_summary = Column(String)
    created_at = Column(String, nullable=False)


class ComplianceDiff(Base):
    __tablename__ = "compliance_diffs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    check_id = Column(Integer, nullable=False)
    system_name = Column(String, nullable=False)
    field_name = Column(String)
    diff_type = Column(String, nullable=False)
    expected = Column(String)
    actual = Column(String)
    record_ref = Column(String)


class DemoDeviceLedger(Base):
    __tablename__ = "demo_device_ledger"
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_code = Column(String)
    device_name = Column(String)
    model_code = Column(String)
    safety_class = Column(String)
    source_system = Column(String)
    updated_at = Column(String)


# ================= 轻量迁移：既有表新增列 =================
# {表名: [(列名, 类型), ...]}，init_db 时自动补列（SQLite / PostgreSQL 通用）。
EXTRA_COLUMNS: dict = {
    "quality_issues": [
        ("assignee_type", "TEXT"),   # 业务 / 技术
        ("lead_assignee", "TEXT"),    # 多责任方时的牵头人
        ("root_cause", "TEXT"),       # 根本原因
        ("fix_desc", "TEXT"),         # 整改说明
        ("confirmed_at", "TEXT"),
        ("closed_at", "TEXT"),
        ("rule_id", "INTEGER"),       # 来源规则
        ("record_ref", "TEXT"),       # 问题记录定位（如 台账ID:3）
    ],
}


def _existing_columns(conn, table: str) -> set:
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").all()
        return {r[1] for r in rows}
    rows = conn.exec_driver_sql(
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_name = '{table}'"
    ).all()
    return {r[0] for r in rows}


def ensure_columns(engine) -> None:
    with engine.begin() as conn:
        for table, cols in EXTRA_COLUMNS.items():
            existing = _existing_columns(conn, table)
            for col, ctype in cols:
                if col not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {col} {ctype}"
                    )


# ================= 引擎 =================

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = settings.db_url
        if url.startswith("sqlite"):
            _engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
    return _engine


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    ensure_columns(engine)


# ================= 兼容层（供一期 routers / seed 沿用） =================

_qmark = re.compile(r"\?")


def _translate(sql: str):
    """把 ? 占位符按顺序翻译为 :p0, :p1, ..."""
    idx = 0

    def _rep(_m):
        nonlocal idx
        name = f"p{idx}"
        idx += 1
        return f":{name}"

    return _qmark.sub(_rep, sql), idx


def _bind(params, count: int):
    if params is None:
        return {}
    if isinstance(params, dict):
        return params
    return {f"p{i}": v for i, v in enumerate(params)}


class _Row:
    """dict 化行：支持 row["col"]、dict(row)、in 判断。"""

    __slots__ = ("_d",)

    def __init__(self, mapping):
        self._d = dict(mapping)

    def __getitem__(self, key):
        return self._d[key]

    def __iter__(self):
        return iter(self._d.values())

    def __contains__(self, key):
        return key in self._d

    def __len__(self):
        return len(self._d)

    def keys(self):
        return self._d.keys()

    def get(self, key, default=None):
        return self._d.get(key, default)


class _Cursor:
    def __init__(self, sa_conn):
        self._conn = sa_conn
        self._result = None
        self._lastrowid = None

    def execute(self, sql, params=None):
        tsql, count = _translate(sql)
        binds = _bind(params, count)
        is_pg = self._conn.engine.dialect.name == "postgresql"
        stripped = sql.lstrip().upper()
        if is_pg and stripped.startswith("INSERT") and "RETURNING" not in stripped:
            tsql += " RETURNING id"
        self._result = self._conn.execute(sa_text(tsql), binds)
        if stripped.startswith("INSERT"):
            if is_pg:
                row = self._result.fetchone()
                self._lastrowid = row[0] if row else None
            else:
                self._lastrowid = self._result.lastrowid
        return self

    def executemany(self, sql, seq_of_params):
        for p in seq_of_params:
            self.execute(sql, p)
        return self

    def fetchone(self):
        if self._result is None:
            return None
        row = self._result.fetchone()
        return _Row(row._mapping) if row is not None else None

    def fetchall(self):
        if self._result is None:
            return []
        return [_Row(r._mapping) for r in self._result.all()]

    @property
    def lastrowid(self):
        return self._lastrowid


class _Connection:
    def __init__(self, sa_conn):
        self._conn = sa_conn

    def execute(self, sql, params=None):
        return _Cursor(self._conn).execute(sql, params)

    def cursor(self):
        return _Cursor(self._conn)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def get_conn() -> _Connection:
    return _Connection(get_engine().connect())


def rows_to_dicts(cursor) -> list:
    return [dict(r) for r in cursor.fetchall()]
