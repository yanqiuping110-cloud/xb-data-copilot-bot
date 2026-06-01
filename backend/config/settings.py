"""
应用配置：按 APP_ENV 加载 backend/.env.development 或 .env.production。

ROOT_DIR 指向 backend/ 目录，与虚拟环境、DDL 脚本同级。
"""

from functools import lru_cache
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 根目录（本文件在 backend/config/ 下）
ROOT_DIR = Path(__file__).resolve().parent.parent


def _env_file() -> str:
    """解析当前应加载的 env 文件路径。"""
    env = os.getenv("APP_ENV", "development")
    path = ROOT_DIR / f".env.{env}"
    if path.is_file():
        return str(path)
    fallback = ROOT_DIR / ".env.example"
    return str(fallback) if fallback.is_file() else str(ROOT_DIR / ".env.development")


class Settings(BaseSettings):
    """从环境变量读取的全部运行时配置。"""

    model_config = SettingsConfigDict(
        env_file=_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- 运行环境 ----------
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    cors_origins: str = Field(
        default="http://localhost:5173",
        alias="CORS_ORIGINS",
        description="前端来源，逗号分隔，用于 CORS",
    )

    # ---------- LLM（OpenAI 兼容，本机多为 Ollama）----------
    llm_api_base: str = Field(
        default="http://127.0.0.1:11434/v1",
        alias="LLM_API_BASE",
    )
    llm_api_key: str = Field(default="ollama", alias="LLM_API_KEY")
    llm_model: str = Field(default="qwen2.5-coder:7b", alias="LLM_MODEL")
    llm_timeout_sec: int = Field(default=120, alias="LLM_TIMEOUT_SEC")

    # ---------- MySQL：智慧体育业务库（只读账号）----------
    mysql_business_host: str = Field(default="127.0.0.1", alias="MYSQL_BUSINESS_HOST")
    mysql_business_port: int = Field(default=3306, alias="MYSQL_BUSINESS_PORT")
    mysql_business_user: str = Field(default="ask_readonly", alias="MYSQL_BUSINESS_USER")
    mysql_business_password: str = Field(default="", alias="MYSQL_BUSINESS_PASSWORD")
    mysql_business_database: str = Field(default="sport", alias="MYSQL_BUSINESS_DATABASE")

    # ---------- MySQL：问数库 copilot（用户/审计/指标）----------
    mysql_copilot_host: str = Field(default="127.0.0.1", alias="MYSQL_COPILOT_HOST")
    mysql_copilot_port: int = Field(default=3306, alias="MYSQL_COPILOT_PORT")
    mysql_copilot_user: str = Field(default="copilot", alias="MYSQL_COPILOT_USER")
    mysql_copilot_password: str = Field(default="", alias="MYSQL_COPILOT_PASSWORD")
    mysql_copilot_database: str = Field(default="copilot", alias="MYSQL_COPILOT_DATABASE")

    # ---------- JWT 与超管种子（seed_admin.py）----------
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_expire_hours: int = Field(default=24, alias="JWT_EXPIRE_HOURS")
    seed_admin_username: str = Field(default="admin", alias="SEED_ADMIN_USERNAME")
    seed_admin_password: str = Field(default="change-me", alias="SEED_ADMIN_PASSWORD")

    # ---------- SQL 执行安全（问数链路使用）----------
    sql_dialect: str = Field(default="mysql", alias="SQL_DIALECT")
    sql_max_rows: int = Field(default=5000, alias="SQL_MAX_ROWS")
    sql_timeout_sec: int = Field(default=10, alias="SQL_TIMEOUT_SEC")
    ask_rate_limit_per_user_per_min: int = Field(
        default=20,
        alias="ASK_RATE_LIMIT_PER_USER_PER_MIN",
    )

    # ---------- RAGFlow / ES（二期可选）----------
    ragflow_enabled: bool = Field(default=False, alias="RAGFLOW_ENABLED")
    ragflow_base_url: str = Field(default="https://127.0.0.1", alias="RAGFLOW_BASE_URL")
    elasticsearch_url: str = Field(
        default="http://127.0.0.1:1200",
        alias="ELASTICSEARCH_URL",
    )
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", alias="REDIS_URL")
    minio_endpoint: str = Field(default="http://127.0.0.1:9000", alias="MINIO_ENDPOINT")

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS 白名单列表。"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def copilot_database_url(self) -> str:
        """SQLAlchemy 异步连接串：问数库。"""
        return (
            f"mysql+aiomysql://{self.mysql_copilot_user}:{self.mysql_copilot_password}"
            f"@{self.mysql_copilot_host}:{self.mysql_copilot_port}"
            f"/{self.mysql_copilot_database}?charset=utf8mb4"
        )

    @property
    def business_database_url(self) -> str:
        """SQLAlchemy 异步连接串：业务只读库。"""
        return (
            f"mysql+aiomysql://{self.mysql_business_user}:{self.mysql_business_password}"
            f"@{self.mysql_business_host}:{self.mysql_business_port}"
            f"/{self.mysql_business_database}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    """单例配置（进程内缓存）。"""
    return Settings()


settings = get_settings()
