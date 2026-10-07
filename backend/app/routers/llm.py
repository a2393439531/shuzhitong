"""大模型辅助：口径解释 / 问题澄清（三期智能问数的调用点验证）。

未配置 LLM 时优雅降级：返回本地规则生成的说明 + 明确原因。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..database import get_conn
from ..deps import get_current_user, log_audit
from ..llm import LLMClient
from ..utils import parse_json

router = APIRouter(prefix="/api/llm", tags=["llm"])


class ExplainBody(BaseModel):
    kind: str = "标准解释"
    ref_type: str = ""
    ref_id: int | None = None
    text: str = ""


def _local_explain(kind: str, ref_type: str, ref_id: int | None, text: str) -> str:
    """本地规则降级说明（不依赖 LLM）。"""
    conn = get_conn()
    try:
        if ref_type == "standard" and ref_id:
            std = conn.execute(
                "SELECT * FROM standards WHERE id = ?", (ref_id,)
            ).fetchone()
            if std:
                allowed = parse_json(std["allowed_values"], [])
                allowed_txt = (
                    "、".join(allowed) if isinstance(allowed, list) else (allowed or "—")
                )
                return (
                    "【{0}】（编码 {1}，版本 {2}）\n"
                    "业务定义：{3}\n允许值：{4}\n"
                    "权威来源：{5}；责任：{6}{7}".format(
                        std["name"], std["code"], std["version"] or "—",
                        std["business_def"] or "—", allowed_txt,
                        std["authority_source"] or "—",
                        std["owner_dept"] or "—", std["owner_role"] or "",
                    )
                )
        if ref_type == "issue" and ref_id:
            iss = conn.execute(
                "SELECT * FROM quality_issues WHERE id = ?", (ref_id,)
            ).fetchone()
            if iss:
                return (
                    "问题「{0}」（类型 {1}，当前状态 {2}）："
                    "建议先确认问题属实，再按认责矩阵派发整改。".format(
                        iss["title"], iss["issue_type"] or "—", iss["status"]
                    )
                )
        if text:
            return "（本地规则）针对「{0}」：请结合数据标准与认责矩阵人工澄清口径。".format(text)
        return "（本地规则）未找到引用对象，请补充说明。"
    finally:
        conn.close()


@router.get("/status")
def llm_status(user=Depends(get_current_user)):
    return LLMClient.from_settings().status()


@router.post("/explain")
def explain(body: ExplainBody, user=Depends(get_current_user)):
    client = LLMClient.from_settings()
    local = _local_explain(body.kind, body.ref_type, body.ref_id, body.text)
    if not client.configured():
        result = {
            "ok": True,
            "content": local,
            "via": "local",
            "reason": client.chat([]).reason,
        }
    else:
        prompt = (
            "你是数据治理助手。请用中文简明解释以下内容（{0}）：\n{1}\n"
            "要求：分条列出业务含义、口径要点、常见误区，不超过 200 字。".format(
                body.kind, local
            )
        )
        r = client.chat([{"role": "user", "content": prompt}])
        result = {
            "ok": r.ok,
            "content": r.content if r.ok else local,
            "via": "llm" if r.ok else "local",
        }
        if not r.ok:
            result["reason"] = r.reason
    log_audit(user, "llm_explain", "{0}（{1}）".format(body.kind, result["via"]), None, 0, "成功")
    return result
