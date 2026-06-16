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

    # ---------- Embedding（OpenAI 兼容，本机多为 Ollama，与 LLM 可同 base）----------
    embedding_api_base: str = Field(
        default="http://127.0.0.1:11434/v1",
        alias="EMBEDDING_API_BASE",
    )
    embedding_api_key: str = Field(default="ollama", alias="EMBEDDING_API_KEY")
    embedding_model: str = Field(
        default="qwen3-embedding:4b",
        alias="EMBEDDING_MODEL",
    )
    embedding_dims: int = Field(
        default=2560,
        alias="EMBEDDING_DIMS",
        description="向量维度（无数据 embed 时建索引占位；qwen3-embedding:4b 多为 2560）",
    )

    # ---------- MySQL：智慧业务库（只读账号）----------
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
    elasticsearch_index_prefix: str = Field(
        default="copilot_ask_",
        alias="ELASTICSEARCH_INDEX_PREFIX",
    )
    recall_top_k_table: int = Field(default=20, alias="RECALL_TOP_K_TABLE")
    recall_top_k_column: int = Field(default=15, alias="RECALL_TOP_K_COLUMN")
    recall_top_k_metric: int = Field(default=5, alias="RECALL_TOP_K_METRIC")
    recall_top_k_value: int = Field(default=10, alias="RECALL_TOP_K_VALUE")
    max_tables_in_prompt: int = Field(default=10, alias="MAX_TABLES_IN_PROMPT")
    max_columns_per_table: int = Field(default=15, alias="MAX_COLUMNS_PER_TABLE")
    table_recall_score_min: float = Field(default=0.7, alias="TABLE_RECALL_SCORE_MIN")
    recall_keyword_fallback: bool = Field(default=True, alias="RECALL_KEYWORD_FALLBACK")
    recall_columns_enabled: bool = Field(
        default=False,
        alias="RECALL_COLUMNS_ENABLED",
        description="是否启用 ES/关键词字段召回；关闭时仅按召回表从元数据加载 Prompt 字段",
    )
    curated_example_top_k: int = Field(
        default=5,
        alias="CURATED_EXAMPLE_TOP_K",
        description="注入 LLM Prompt 的 L1 样例软参考最大条数",
    )
    curated_example_min_score: int = Field(
        default=1,
        alias="CURATED_EXAMPLE_MIN_SCORE",
        description="L1 样例软参考最低相关性得分，低于此值不注入 Prompt",
    )

    # ---------- Agent Plan + 工具（第 7 周 · §11.7）----------
    policy_sch_id_enabled: bool = Field(
        default=False,
        alias="POLICY_SCH_ID_ENABLED",
        description="问数 SQL 是否启用 sch_id 注入/校验；development 默认关闭以便调试复杂 SQL",
    )
    agent_plan_enabled: bool = Field(
        default=True,
        alias="AGENT_PLAN_ENABLED",
        description="是否在 build_llm_context 后执行 plan_question（L1 高分可跳过）",
    )
    plan_l1_fast_path_score: int = Field(
        default=12,
        alias="PLAN_L1_FAST_PATH_SCORE",
        description="L1 样例得分 ≥ 此值时跳过 Plan，走原 generate_sql（与 example_ranker 全规则命中加成一致）",
    )
    agent_loop_enabled: bool = Field(
        default=True,
        alias="AGENT_LOOP_ENABLED",
        description="复杂问句是否在 plan_question 后进入 ReAct agent_loop",
    )
    agent_multi_sql_enabled: bool = Field(
        default=True,
        alias="AGENT_MULTI_SQL_ENABLED",
        description="复杂问句 Agent 路径是否按 plan 分步生成并执行多条 SQL，再 assemble_result 拼表",
    )
    agent_max_steps: int = Field(
        default=6,
        alias="AGENT_MAX_STEPS",
        description="单轮 ask 最大 Agent tool 调用次数",
    )
    agent_max_correct: int = Field(
        default=3,
        alias="AGENT_MAX_CORRECT",
        description="correct_sql / verify 触发的最大修正次数（第 9 周默认 3）",
    )
    verify_answer_enabled: bool = Field(
        default=True,
        alias="VERIFY_ANSWER_ENABLED",
        description="execute_sql 后是否执行 verify_answer 语义验证",
    )
    verify_answer_llm_enabled: bool = Field(
        default=False,
        alias="VERIFY_ANSWER_LLM_ENABLED",
        description="启发式验证失败时是否调用 LLM 二次确认",
    )
    format_answer_llm_enabled: bool = Field(
        default=True,
        alias="FORMAT_ANSWER_LLM_ENABLED",
        description="复杂 Agent 路径是否用 LLM 生成可读摘要",
    )
    recall_top_k_code: int = Field(
        default=5,
        alias="RECALL_TOP_K_CODE",
        description="代码 artifact ES 召回 Top-K",
    )
    code_knowledge_enabled: bool = Field(
        default=True,
        alias="CODE_KNOWLEDGE_ENABLED",
        description="是否启用 Git 代码知识图谱召回与 Agent 工具",
    )
    agent_probe_timeout_sec: int = Field(
        default=3,
        alias="AGENT_PROBE_TIMEOUT_SEC",
        description="run_probe_sql 业务库执行超时（秒）",
    )
    graph_recursion_limit: int = Field(
        default=64,
        alias="GRAPH_RECURSION_LIMIT",
        description="LangGraph 单轮 ask 最大节点步数（复杂 Agent 路径需高于默认 25）",
    )
    verify_max_correct: int = Field(
        default=1,
        alias="VERIFY_MAX_CORRECT",
        description="verify_answer 失败后最多触发的 correct_sql 次数（与校验失败共用 correct_sql_count 预算）",
    )

    # ---------- Agent Memory（第 6 周）----------
    memory_enabled: bool = Field(default=True, alias="MEMORY_ENABLED")
    session_memory_enabled: bool = Field(default=True, alias="SESSION_MEMORY_ENABLED")
    user_preference_enabled: bool = Field(default=True, alias="USER_PREFERENCE_ENABLED")
    memory_prompt_max_chars: int = Field(default=2000, alias="MEMORY_PROMPT_MAX_CHARS")
    session_memory_max_turns: int = Field(default=3, alias="SESSION_MEMORY_MAX_TURNS")
    session_max_per_user: int = Field(default=20, alias="SESSION_MAX_PER_USER")
    session_evict_policy: str = Field(default="oldest", alias="SESSION_EVICT_POLICY")
    session_ui_turn_limit: int = Field(default=30, alias="SESSION_UI_TURN_LIMIT")

    # ---------- 动态数据权限（第 13 周 · §11.6）----------
    policy_data_scope_enabled: bool = Field(
        default=False,
        alias="POLICY_DATA_SCOPE_ENABLED",
        description="是否启用配置驱动 DataScope；关闭时沿用全局表白名单",
    )
    policy_default_deny: bool = Field(
        default=True,
        alias="POLICY_DEFAULT_DENY",
        description="DataScope 开启时无 grant 是否默认拒绝问数",
    )
    policy_cache_ttl_sec: int = Field(default=60, alias="POLICY_CACHE_TTL_SEC")

    # ---------- Prompt Injection 防护（第 13 周 · §11.9）----------
    prompt_boundary_enabled: bool = Field(default=True, alias="PROMPT_BOUNDARY_ENABLED")
    prompt_sanitize_recall_enabled: bool = Field(
        default=True, alias="PROMPT_SANITIZE_RECALL_ENABLED"
    )
    prompt_injection_log_enabled: bool = Field(
        default=True, alias="PROMPT_INJECTION_LOG_ENABLED"
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
