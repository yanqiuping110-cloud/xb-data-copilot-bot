"""
统一业务异常 → HTTP JSON 响应。

前端约定：{ "error": { "code": "...", "message": "..." } }
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.ask.exceptions import AskError
from app.auth import jwt_tokens
from app.auth.service import AuthError
from app.code.exceptions import CodeKnowledgeError
from app.meta.exceptions import MetaError
from app.policy.role_policy import PolicyError


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


async def auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
    """登录失败、未授权、权限不足等。"""
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message),
    )


async def token_error_handler(_: Request, exc: jwt_tokens.TokenError) -> JSONResponse:
    """JWT 过期或签名无效。"""
    return JSONResponse(
        status_code=401,
        content=_error_body(exc.code, exc.message),
    )


async def policy_error_handler(_: Request, exc: PolicyError) -> JSONResponse:
    """问数前校维度策略拒绝（如未选学校）。"""
    return JSONResponse(
        status_code=403,
        content=_error_body(exc.code, exc.message),
    )


async def ask_error_handler(_: Request, exc: AskError) -> JSONResponse:
    """问数业务错误（空问题、暂不支持问法等）。"""
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message),
    )


async def meta_error_handler(_: Request, exc: MetaError) -> JSONResponse:
    """元数据/introspect 业务错误。"""
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message),
    )


async def code_knowledge_error_handler(_: Request, exc: CodeKnowledgeError) -> JSONResponse:
    """Git 代码知识库业务错误。"""
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message),
    )
