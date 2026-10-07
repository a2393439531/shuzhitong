"""四期种子数据：基地档案、标准/指标基地差异。幂等。"""
import json

from .database import get_conn
from .deps import now_str


def _count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]


def seed_phase4() -> None:
    conn = get_conn()
    try:
        now = now_str()
        # ---------- 基地档案 ----------
        if _count(conn, "bases") == 0:
            cur = conn.cursor()
            for code, name, stack, status, desc in [
                ("BASE-A", "基地A", "PWR1000", "运行中", "首个商运基地，集团共性标准全量落标"),
                ("BASE-B", "基地B", "PWR600", "建设中", "新建基地，堆型差异导致部分标准允许值不同"),
            ]:
                cur.execute(
                    """INSERT INTO bases (code, name, stack_type, status, description, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (code, name, stack, status, desc, now),
                )

        # ---------- 标准基地差异：STD-001 核安全分级 ----------
        if _count(conn, "std_base_diff") == 0:
            s = conn.execute(
                "SELECT id FROM standards WHERE code = 'STD-001'").fetchone()
            if s:
                conn.execute(
                    """INSERT INTO std_base_diff
                       (standard_id, base_code, diff_type, diff_desc, reason,
                        effective_from, effective_to, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (s["id"], "BASE-B", "允许值",
                     json.dumps({
                         "allowed_values": ["NS1", "NS2", "非核级"],
                         "note": "B基地堆型不涉及NS3级设备，落标时按此值域校验",
                     }, ensure_ascii=False),
                     "B基地堆型（PWR600）不涉及NS3级设备",
                     "2025-01-01", None, "已发布", now),
                )

        # ---------- 指标基地差异：WO_ON_TIME_RATE ----------
        if _count(conn, "indicator_base_diff") == 0:
            ind = conn.execute(
                "SELECT id FROM indicators WHERE code = 'WO_ON_TIME_RATE'"
            ).fetchone()
            if ind:
                conn.execute(
                    """INSERT INTO indicator_base_diff
                       (indicator_id, base_code, diff_type, diff_desc, reason,
                        effective_from, effective_to, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ind["id"], "BASE-B", "口径",
                     json.dumps({
                         "scope_note": "B基地建设期工单纳入统计，集团口径仅统计商运机组",
                         "formula_note": "分子分母口径与集团一致，统计范围扩大至建设期",
                     }, ensure_ascii=False),
                     "B基地处于建设期，工单统计范围与商运基地不同",
                     "2025-01-01", None, "已发布", now),
                )
        conn.commit()
    finally:
        conn.close()
