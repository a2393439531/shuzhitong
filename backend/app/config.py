"""应用配置：全部走环境变量 / .env（pydantic-settings）。

配置项总览见项目根 .env.example（逐项中文注释）。
敏感配置（JWT 密钥、LLM Key、数据库密码）禁止打日志、禁止返回前端。
"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根 = ~/workspace/shuzhitong（backend 的父目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_JWT_SECRET = "dev-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---------------- 应用 ----------------
    SZT_APP_VERSION: str = "1.2.0"

    # ---------------- Server ----------------
    SZT_HOST: str = "0.0.0.0"
    SZT_PORT: int = 8000
    SZT_WORKERS: int = 1
    SZT_CORS_ORIGINS: str = "*"  # 逗号分隔，如 https://a.com,https://b.com
    SZT_LOG_LEVEL: str = "info"

    # ---------------- Database ----------------
    # 为空则用 SQLite（SZT_DATA_DIR/shuzhitong.db）；PostgreSQL 示例：
    # postgresql://szt:szt123@shuzhitong-db:5432/shuzhitong
    SZT_DB_URL: str = ""
    SZT_DATA_DIR: str = ""  # 为空则 <项目根>/backend/data

    # ---------------- LLM ----------------
    # deepseek | qwen | openai_compatible | disabled
    SZT_LLM_PROVIDER: str = "disabled"
    SZT_LLM_BASE_URL: str = ""
    SZT_LLM_API_KEY: str = ""
    SZT_LLM_MODEL: str = ""
    SZT_LLM_TIMEOUT: int = 60

    # ---------------- Auth ----------------
    SZT_JWT_SECRET: str = DEFAULT_JWT_SECRET
    SZT_TOKEN_EXPIRE_MINUTES: int = 720

    # ---------------- 其他 ----------------
    SZT_SEED_DEMO_DATA: bool = True  # 生产可设为 false 关闭演示数据灌入

    # ---------------- 三期：服务应用 ----------------
    SZT_SVC_RATE_LIMIT: int = 60  # 服务调用限流：每用户每服务每分钟次数
    SZT_QA_SQL_LIMIT: int = 200  # 智能问数受控查询默认行数上限

    # ---------------- 四期：推广运营 ----------------
    SZT_OPS_TREND_DAYS: int = 14  # 运营大盘趋势统计天数

    # ---------- 派生属性 ----------

    @property
    def data_dir(self) -> Path:
        p = Path(self.SZT_DATA_DIR) if self.SZT_DATA_DIR else PROJECT_ROOT / "backend" / "data"
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_url(self) -> str:
        """实际生效的数据库连接串。"""
        if "SZT_DB_URL" in self.model_fields_set and self.SZT_DB_URL:
            url = self.SZT_DB_URL.strip()
        else:
            # 兼容一期旧变量名
            legacy = os.environ.get("SZT_DB_PATH") or os.environ.get("DATABASE_PATH")
            if legacy:
                url = f"sqlite:///{legacy}"
            else:
                url = ""
        if not url:
            url = f"sqlite:///{self.data_dir / 'shuzhitong.db'}"
        if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
            # 相对路径按项目根解析为绝对路径
            path = url[len("sqlite:///"):]
            if not os.path.isabs(path):
                url = f"sqlite:///{PROJECT_ROOT / path}"
        return url

    @property
    def db_type(self) -> str:
        return "postgresql" if self.db_url.startswith("postgresql") else "sqlite"

    @property
    def safe_db_url(self) -> str:
        """打日志用：密码脱敏。"""
        url = self.db_url
        if "://" in url and "@" in url:
            head, rest = url.split("://", 1)
            if "@" in rest:
                creds, tail = rest.rsplit("@", 1)
                if ":" in creds:
                    user = creds.split(":", 1)[0]
                    return f"{head}://{user}:***@{tail}"
        return url

    @property
    def cors_origins(self) -> list:
        if self.SZT_CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.SZT_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def jwt_secret_is_default(self) -> bool:
        return self.SZT_JWT_SECRET == DEFAULT_JWT_SECRET

    @property
    def token_expire_minutes(self) -> int:
        # 兼容一期旧变量 SZT_JWT_EXPIRE_HOURS
        if "SZT_TOKEN_EXPIRE_MINUTES" not in self.model_fields_set:
            legacy = os.environ.get("SZT_JWT_EXPIRE_HOURS")
            if legacy:
                try:
                    return int(legacy) * 60
                except ValueError:
                    pass
        return self.SZT_TOKEN_EXPIRE_MINUTES


settings = Settings()
