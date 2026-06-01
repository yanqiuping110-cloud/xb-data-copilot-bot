"""
密码哈希与校验（bcrypt）。

库表只存 password_hash，禁止明文密码入库或写日志。
"""

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """注册/重置密码时使用。"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """登录时校验。"""
    return pwd_context.verify(plain, hashed)
