"""
FastAPI 应用入口。

职责：注册 CORS、全局异常处理、路由（健康检查 / 认证 / 超管用户管理）。
问数流水线路由（/ask）在后续迭代中挂载。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin_code, admin_meta, admin_users, ask, auth, errors, feedback, health, memory_prefs, sessions
from app.ask.exceptions import AskError
from app.auth import jwt_tokens
from app.auth.service import AuthError
from app.code.exceptions import CodeKnowledgeError
from app.meta.exceptions import MetaError
from app.policy.role_policy import PolicyError
from app.core.log_config import get_logger, setup_logging
from config.settings import get_settings


http_logger = get_logger("http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载配置到 app.state，供 /ready 等使用。"""
    settings = get_settings()
    setup_logging(debug=settings.app_debug)
    app.state.settings = settings
    yield


def create_app() -> FastAPI:
    """工厂函数：便于测试注入与多实例配置。"""
    settings = get_settings()
    setup_logging(debug=settings.app_debug)
    app = FastAPI(
        title="小奔问数 Data Copilot",
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

    app.include_router(health.router, tags=["health"])
    app.include_router(auth.router)
    app.include_router(admin_users.router)
    app.include_router(admin_meta.router)
    app.include_router(admin_code.router)
    app.include_router(ask.router)
    app.include_router(sessions.router)
    app.include_router(memory_prefs.router)
    app.include_router(feedback.router)

    @app.middleware("http")
    async def log_http_requests(request, call_next):
        """每个 API 请求在终端打一行，便于确认流量是否打到当前进程。"""
        path = request.url.path
        if path.startswith("/api/v1/ask"):
            http_logger.info(">>> %s %s", request.method, path)
        response = await call_next(request)
        if path.startswith("/api/v1/ask"):
            http_logger.info("<<< %s %s status=%s", request.method, path, response.status_code)
        return response

    return app


# Uvicorn 默认入口：uvicorn app.main:app
app = create_app()
