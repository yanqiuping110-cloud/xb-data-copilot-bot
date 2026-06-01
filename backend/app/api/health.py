"""
健康检查与就绪探针（K8s / 运维）。

/health：进程存活；/ready：依赖 MySQL copilot + 业务库是否可达。
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db.business import check_business_connection
from app.db.copilot import check_copilot_connection
from config.settings import Settings

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """存活探针，不探测外部依赖。"""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request):
    """
    就绪探针：双库均连通时 200，否则 503 degraded。

    便于部署时发现 MySQL 账号或网络配置错误。
    """
    settings: Settings = request.app.state.settings
    copilot_ok = await check_copilot_connection()
    business_ok = await check_business_connection()
    checks = {
        "app_env": settings.app_env,
        "mysql_copilot": copilot_ok,
        "mysql_business": business_ok,
        "llm_api_base": settings.llm_api_base,
        "ragflow_enabled": settings.ragflow_enabled,
    }
    all_ok = copilot_ok and business_ok
    body = {"status": "ready" if all_ok else "degraded", "checks": checks}
    if not all_ok:
        return JSONResponse(status_code=503, content=body)
    return body
