"""系统配置只读接口：返回当前生效的非敏感配置。

敏感项（JWT 密钥、LLM Key、数据库密码）永不返回。
"""
from fastapi import APIRouter, Depends

from ..config import settings
from ..deps import get_current_user
from ..llm import LLMClient
from ..permissions import require_role

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/config")
def system_config(user=Depends(get_current_user)):
    require_role(user, "admin")
    llm = LLMClient.from_settings()
    return {
        "version": settings.SZT_APP_VERSION,
        "db_type": settings.db_type,
        "db_dsn": settings.safe_db_url,
        "llm_provider": llm.provider,
        "llm_configured": llm.configured(),
        "llm_model": llm.model,
        "seed_enabled": settings.SZT_SEED_DEMO_DATA,
        "host": settings.SZT_HOST,
        "port": settings.SZT_PORT,
        "log_level": settings.SZT_LOG_LEVEL,
        "jwt_is_default": settings.jwt_secret_is_default,
        "token_expire_minutes": settings.token_expire_minutes,
    }
