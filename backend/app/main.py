"""
FastAPI 应用入口。

职责：注册 CORS、全局异常处理、路由（健康检查 / 认证 / 超管用户管理）。
问数流水线路由（/ask）在后续迭代中挂载。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin_code,
    admin_meta,
    admin_ops,
    admin_scope,
    admin_system,
    admin_users,
    ask,
    auth,
    brief_report,
    chart,
    embed,
    errors,
    feedback,
    health,
    memory_prefs,
    research,
    sessions,
)
from app.ask.exceptions import AskError
from app.auth import jwt_tokens
from app.auth.service import AuthError
from app.code.exceptions import CodeKnowledgeError
from app.db.copilot import get_session_factory
from app.meta.exceptions import MetaError
from app.policy.role_policy import PolicyError
from app.core.log_config import get_logger, setup_logging
from app.system.exceptions import SystemConfigError
from app.system.seed_from_env import seed_system_config_from_env
from config.settings import get_settings


http_logger = get_logger("http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：加载配置、种子系统 LLM/数据源、写入 app.state。"""
    settings = get_settings()
    setup_logging(debug=settings.app_debug)
    app.state.settings = settings
    try:
        factory = get_session_factory()
        async with factory() as session:
            await seed_system_config_from_env(session, settings)
    except Exception:
        http_logger.warning("system config seed skipped", exc_info=True)
    yield


def create_app() -> FastAPI:
    """工厂函数：便于测试注入与多实例配置。"""
    settings = get_settings()
    setup_logging(debug=settings.app_debug)
    app = FastAPI(
        title="Data Copilot",
        version="0.1.0",
        lifespan=lifespan,
    )
    # 允许前端 dev server（5173）携带 Cookie / Authorization
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 业务异常 → 统一 JSON：{ "error": { "code", "message" } }
    app.add_exception_handler(AuthError, errors.auth_error_handler)
    app.add_exception_handler(jwt_tokens.TokenError, errors.token_error_handler)
    app.add_exception_handler(PolicyError, errors.policy_error_handler)
    app.add_exception_handler(AskError, errors.ask_error_handler)
    app.add_exception_handler(MetaError, errors.meta_error_handler)
    app.add_exception_handler(CodeKnowledgeError, errors.code_knowledge_error_handler)
    app.add_exception_handler(SystemConfigError, errors.system_config_error_handler)

    app.include_router(health.router, tags=["health"])
    app.include_router(auth.router)
    app.include_router(admin_users.router)
    app.include_router(admin_meta.router)
    app.include_router(admin_ops.router)
    app.include_router(admin_scope.router)
    app.include_router(admin_system.router)
    app.include_router(admin_code.router)
    app.include_router(ask.router)
    app.include_router(brief_report.router)
    app.include_router(sessions.router)
    app.include_router(memory_prefs.router)
    app.include_router(feedback.router)
    app.include_router(research.router)
    app.include_router(chart.router)
    app.include_router(embed.router)

    @app.middleware("http")
    async def log_http_requests(request, call_next):
        """每个 API 请求在终端打一行，便于确认流量是否打到当前进程。"""
        path = request.url.path
        if path.startswith("/api/v1/ask") or path.startswith("/api/v1/research"):
            http_logger.info(">>> %s %s", request.method, path)
        response = await call_next(request)
        if path.startswith("/api/v1/ask") or path.startswith("/api/v1/research"):
            http_logger.info("<<< %s %s status=%s", request.method, path, response.status_code)
        return response

    return app


# Uvicorn 默认入口：uvicorn app.main:app
app = create_app()
