"""统一大模型客户端：OpenAI 兼容的 chat completions 接口。

- provider: deepseek | qwen | openai_compatible | disabled（默认 disabled）
- 未配置 / 调用失败时优雅降级，返回明确原因，不抛异常。
- 为三期智能问数预留调用点；本期先接"口径解释 / 问题澄清"辅助功能做验证。
- API Key 只存内存，禁止打日志、禁止返回前端。

原创实现。
"""
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import settings

PROVIDER_DEFAULTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "openai_compatible": {"base_url": "", "model": ""},
}

SUPPORTED = ("deepseek", "qwen", "openai_compatible", "disabled")


@dataclass
class LLMResult:
    ok: bool
    content: str = ""
    reason: str = ""  # 降级 / 失败原因（不含密钥）


class LLMClient:
    def __init__(
        self,
        provider: str = "disabled",
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        timeout: int = 60,
    ):
        self.provider = (provider or "disabled").strip().lower()
        defaults = PROVIDER_DEFAULTS.get(self.provider, {})
        self.base_url = (base_url or defaults.get("base_url", "")).rstrip("/")
        self.model = model or defaults.get("model", "")
        self.timeout = timeout or 60
        # Key 只保留在实例内存中
        self._api_key = api_key or ""

    @classmethod
    def from_settings(cls) -> "LLMClient":
        return cls(
            provider=settings.SZT_LLM_PROVIDER,
            base_url=settings.SZT_LLM_BASE_URL,
            api_key=settings.SZT_LLM_API_KEY,
            model=settings.SZT_LLM_MODEL,
            timeout=settings.SZT_LLM_TIMEOUT,
        )

    def configured(self) -> bool:
        """是否可真实调用：provider 非 disabled 且有 base_url 与 key、model。"""
        return (
            self.provider in SUPPORTED
            and self.provider != "disabled"
            and bool(self.base_url)
            and bool(self._api_key)
            and bool(self.model)
        )

    def status(self) -> dict:
        """给前端 / 运维的状态（不含 Key）。"""
        return {
            "provider": self.provider,
            "configured": self.configured(),
            "model": self.model,
            "timeout": self.timeout,
        }

    def chat(self, messages: list, temperature: float = 0.3) -> LLMResult:
        if self.provider not in SUPPORTED or self.provider == "disabled":
            return LLMResult(ok=False, reason="LLM 未配置（SZT_LLM_PROVIDER=disabled），已降级为本地规则")
        if not self.configured():
            missing = []
            if not self.base_url:
                missing.append("SZT_LLM_BASE_URL")
            if not self._api_key:
                missing.append("SZT_LLM_API_KEY")
            if not self.model:
                missing.append("SZT_LLM_MODEL")
            return LLMResult(
                ok=False,
                reason=f"LLM 配置不完整（缺少 { '、'.join(missing) }），已降级为本地规则",
            )
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer <redacted>",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            if not content:
                return LLMResult(ok=False, reason="LLM 返回为空，已降级为本地规则")
            return LLMResult(ok=True, content=content.strip())
        except urllib.error.HTTPError as e:
            return LLMResult(
                ok=False, reason=f"LLM 调用失败（HTTP {e.code}），已降级为本地规则"
            )
        except Exception as e:  # noqa: BLE001 - 降级路径兜底
            return LLMResult(ok=False, reason=f"LLM 调用异常（{type(e).__name__}），已降级为本地规则")
