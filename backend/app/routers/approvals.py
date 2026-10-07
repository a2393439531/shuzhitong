"""审批中心：待办/详情/审批决策（含业务状态回写）。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..database import get_conn, rows_to_dicts
from ..deps import get_current_user, log_audit, now_str
from ..permissions import ROLE_LEVEL, require_role

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class DecideBody(BaseModel):
    decision: str  # 通过 / 驳回
    comment: str = ""


def _pending_todo_sql() -> str:
    return """a.status = '待审批' AND EXISTS (
        SELECT 1 FROM approval_steps s
        WHERE s.approval_id = a.id AND s.seq = a.current_step AND s.decision = '待定'
    )"""


def _get_approval_or_404(conn, approval_id: int):
    a = conn.execute(
        "SELECT * FROM approvals WHERE id = ?", (approval_id,)
    ).fetchone()
    if a is None:
        raise HTTPException(status_code=404, detail="审批单不存在")
    return a


@router.get("")
def list_approvals(todo: int | None = None, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        if todo == 1:
            sql = f"SELECT * FROM approvals a WHERE {_pending_todo_sql()}"
            params: list = []
            # operator 只能看自己申请的待办
            if ROLE_LEVEL.get(user["role"], 0) < ROLE_LEVEL["admin"]:
                sql += " AND a.applicant = ?"
                params.append(user["username"])
            sql += " ORDER BY a.id"
            return rows_to_dicts(conn.execute(sql, params))
        # 非待办列表：admin 可见全部，operator 只看自己申请的
        if ROLE_LEVEL.get(user["role"], 0) < ROLE_LEVEL["admin"]:
            return rows_to_dicts(conn.execute(
                "SELECT * FROM approvals WHERE applicant = ? ORDER BY id",
                (user["username"],)))
        return rows_to_dicts(conn.execute("SELECT * FROM approvals ORDER BY id"))
    finally:
        conn.close()


@router.get("/{approval_id}")
def get_approval(approval_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        a = dict(_get_approval_or_404(conn, approval_id))
        if (ROLE_LEVEL.get(user["role"], 0) < ROLE_LEVEL["admin"]
                and a["applicant"] != user["username"]):
            raise HTTPException(status_code=403, detail="无权查看该审批单")
        a["steps"] = rows_to_dicts(conn.execute(
            "SELECT * FROM approval_steps WHERE approval_id = ? ORDER BY seq",
            (approval_id,)))
    finally:
        conn.close()
    return a


@router.post("/{approval_id}/decide")
def decide(approval_id: int, body: DecideBody, request: Request,
           user=Depends(get_current_user)):
    require_role(user, "admin")
    if body.decision not in ("通过", "驳回"):
        raise HTTPException(status_code=400, detail="decision 只能是 通过/驳回")
    conn = get_conn()
    try:
        a = _get_approval_or_404(conn, approval_id)
        if a["status"] != "待审批":
            raise HTTPException(status_code=400, detail="审批单不在待审批状态")
        steps = rows_to_dicts(conn.execute(
            "SELECT * FROM approval_steps WHERE approval_id = ? ORDER BY seq",
            (approval_id,)))
        cur_step = next((s for s in steps if s["seq"] == a["current_step"]), None)
        if cur_step is None or cur_step["decision"] != "待定":
            raise HTTPException(status_code=400, detail="当前步骤不可决策")
        now = now_str()
        conn.execute(
            """UPDATE approval_steps SET decision=?, comment=?, approver=?, acted_at=?
               WHERE id=?""",
            (body.decision, body.comment, user["username"], now, cur_step["id"]),
        )
        max_seq = max(s["seq"] for s in steps)

        if body.decision == "驳回":
            conn.execute("UPDATE approvals SET status = '已驳回' WHERE id = ?",
                         (approval_id,))
            if a["biz_type"] == "标准发布":
                conn.execute("UPDATE standards SET status = '草稿' WHERE id = ?",
                             (a["biz_id"],))
            elif a["biz_type"] == "目录发布":
                conn.execute("UPDATE resources SET status = '已登记' WHERE id = ?",
                             (a["biz_id"],))
            action = "审批驳回"
        else:
            action = "审批通过"
            if a["current_step"] >= max_seq:
                # 最后一步：审批单通过，回写业务状态
                conn.execute("UPDATE approvals SET status = '已通过' WHERE id = ?",
                             (approval_id,))
                if a["biz_type"] == "标准发布":
                    conn.execute("UPDATE standards SET status = '已发布' WHERE id = ?",
                                 (a["biz_id"],))
                elif a["biz_type"] == "目录发布":
                    conn.execute("UPDATE resources SET status = '已发布' WHERE id = ?",
                                 (a["biz_id"],))
            else:
                conn.execute(
                    "UPDATE approvals SET current_step = current_step + 1 WHERE id = ?",
                    (approval_id,),
                )
                # 目录发布步骤1通过后进入审核中
                if a["biz_type"] == "目录发布" and a["current_step"] == 1:
                    conn.execute("UPDATE resources SET status = '审核中' WHERE id = ?",
                                 (a["biz_id"],))
        conn.commit()
        a = dict(conn.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())
    finally:
        conn.close()
    log_audit(user, action,
              f"{action}：审批单 {approval_id}（{a['biz_type']}）{body.decision}"
              f"{'，' + body.comment if body.comment else ''}", request)
    return a
