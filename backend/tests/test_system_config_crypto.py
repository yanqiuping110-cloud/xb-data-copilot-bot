"""系统配置加解密与 runtime resolve 单测（不依赖 MySQL）。"""

from __future__ import annotations

from types import SimpleNamespace

from app.security.config_crypto import decrypt_secret, encrypt_secret
from app.system.models import ResolvedBusinessDsn, ResolvedLlmConfig
from app.system.runtime_config import (
    invalidate_runtime_cache,
    resolve_business_dsn,
    resolve_chat_llm,
    resolve_embedding,
    resolve_sql_max_rows,
)


def _settings(**kwargs):
    base = {
        "jwt_secret": "test-jwt-secret-for-crypto-unit",
        "config_crypto_key": "",
        "llm_api_base": "http://llm.test/v1",
        "llm_api_key": "k-llm",
        "llm_model": "chat-model",
        "llm_timeout_sec": 60,
        "llm_thinking_enabled": False,
        "llm_reasoning_effort": "high",
        "embedding_api_base": "http://emb.test/v1",
        "embedding_api_key": "k-emb",
        "embedding_model": "emb-model",
        "embedding_dims": 128,
        "mysql_business_host": "127.0.0.1",
        "mysql_business_port": 3306,
        "mysql_business_user": "ro",
        "mysql_business_password": "pw",
        "mysql_business_database": "biz",
        "sql_max_rows": 100,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_config_crypto_roundtrip():
    settings = _settings()
    token = encrypt_secret("secret-value", settings)
    assert token != "secret-value"
    assert decrypt_secret(token, settings) == "secret-value"


def test_config_crypto_empty():
    settings = _settings()
    assert decrypt_secret(None, settings) == ""
    assert decrypt_secret("", settings) == ""


def test_resolve_falls_back_to_env_when_cache_empty():
    invalidate_runtime_cache()
    settings = _settings()
    chat = resolve_chat_llm(settings)
    assert isinstance(chat, ResolvedLlmConfig)
    assert chat.source == "env"
    assert chat.api_base == "http://llm.test/v1"
    assert chat.model == "chat-model"

    emb = resolve_embedding(settings)
    assert emb.source == "env"
    assert emb.model == "emb-model"
    assert emb.embedding_dims == 128

    biz = resolve_business_dsn(settings)
    assert isinstance(biz, ResolvedBusinessDsn)
    assert biz.source == "env"
    assert biz.database == "biz"
    assert "mysql+aiomysql://" in biz.sqlalchemy_url

    assert resolve_sql_max_rows(settings) == 100
