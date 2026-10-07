"""数治通后端入口。原创实现。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .routers import (
    approvals,
    audit,
    auth,
    compliance,
    dashboard,
    domains,
    fieldmap,
    llm,
    masterdata,
    metrics,
    objects,
    processes,
    qa,
    quality,
    resources,
    responsibilities,
    services,
    standards,
    system,
)
from .seed import seed

log = logging.getLogger("shuzhitong")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时打印实际生效的配置（敏感项脱敏 / 不打印）
    print(f"[shuzhitong] 版本 v{settings.SZT_APP_VERSION}")
    print(f"[shuzhitong] 数据库类型: {settings.db_type}，连接: {settings.safe_db_url}")
    if settings.jwt_secret_is_default:
        print("[shuzhitong] WARNING: 正在使用默认 JWT 密钥，生产环境请设置 SZT_JWT_SECRET")
    else:
        print("[shuzhitong] JWT 密钥: 已自定义")
    print(f"[shuzhitong] LLM: provider={settings.SZT_LLM_PROVIDER}")
    init_db()
    if settings.SZT_SEED_DEMO_DATA:
        seed()
        print("[shuzhitong] 演示数据: 已灌入（SZT_SEED_DEMO_DATA=true）")
    else:
        print("[shuzhitong] 演示数据: 已跳过（SZT_SEED_DEMO_DATA=false）")
    yield


app = FastAPI(title=f"数治通 v{settings.SZT_APP_VERSION}", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(domains.router)
app.include_router(objects.router)
app.include_router(processes.router)
app.include_router(standards.router)
app.include_router(resources.router)
app.include_router(responsibilities.router)
app.include_router(quality.router)
app.include_router(masterdata.router)
app.include_router(fieldmap.router)
app.include_router(compliance.router)
app.include_router(approvals.router)
app.include_router(audit.router)
app.include_router(dashboard.router)
app.include_router(llm.router)
app.include_router(system.router)
app.include_router(services.router)
app.include_router(metrics.router)
app.include_router(qa.router)


@app.get("/api/health")
def health():
    return {"ok": True, "app": "shuzhitong", "version": settings.SZT_APP_VERSION}
