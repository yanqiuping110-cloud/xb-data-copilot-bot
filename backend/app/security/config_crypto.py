"""
系统配置密钥加解密（API Key / 业务库密码）。

Fernet；密钥优先 CONFIG_CRYPTO_KEY，否则由 JWT_SECRET 派生。
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from config.settings import Settings, get_settings


def _fernet(settings: Settings | None = None) -> Fernet:
    s = settings or get_settings()
    raw = (s.config_crypto_key or "").strip()
    if raw:
        # 允许直接填 url-safe base64 Fernet key，或任意口令字符串
        try:
            return Fernet(raw.encode("utf-8") if isinstance(raw, str) else raw)
        except Exception:
            digest = hashlib.sha256(raw.encode("utf-8")).digest()
            return Fernet(base64.urlsafe_b64encode(digest))
    digest = hashlib.sha256(s.jwt_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str, settings: Settings | None = None) -> str:
    """明文 → Fernet token 字符串。"""
    text = plaintext or ""
    return _fernet(settings).encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str | None, settings: Settings | None = None) -> str:
    """密文 → 明文；空或解密失败返回空串。"""
    if not ciphertext:
        return ""
    try:
        return _fernet(settings).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
