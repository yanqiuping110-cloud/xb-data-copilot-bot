"""
动态数据权限：EffectivePolicy 加载与 Prompt 摘要（第 13 周 · §11.6）。

配置驱动：代码只认 dimension_code + table_name + column_name，不写死业务列名。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext, UserRole
from app.policy.role_policy import PolicyError
from app.policy.scope_repository import ScopeRepository
from app.sql.whitelist import get_allowed_tables
from config.settings import Settings


@dataclass
class EffectivePolicy:
    """单次问数请求的有效数据范围策略。"""

    data_grants: dict[str, list[Any]] = field(default_factory=dict)
    table_bindings: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    allowed_tables: frozenset[str] = field(default_factory=frozenset)
    denied_columns: dict[str, frozenset[str]] = field(default_factory=dict)
    scope_sql_hints: str = ""
    is_admin_bypass: bool = False
    active_scopes: dict[str, Any] = field(default_factory=dict)
    grants_hash: str = ""

    def is_enabled(self) -> bool:
        """非 bypass 且存在 grant 约束时为严格模式。"""
        return not self.is_admin_bypass


def build_scope_prompt_sections(policy: EffectivePolicy | None) -> str:
    """拼装可信策略块：数据范围、可见表、禁止字段。"""
    if policy is None or policy.is_admin_bypass:
        if policy and policy.is_admin_bypass:
            tables = ", ".join(sorted(policy.allowed_tables)[:30])
            return (
                "【数据范围】超管 bypass：可查已注册表白名单内全部数据\n"
                f"【可见表】{tables or '（无）'}\n"
            )
        return ""

    parts: list[str] = []
    if policy.scope_sql_hints:
        parts.append(f"【数据范围】\n{policy.scope_sql_hints}")
    if policy.allowed_tables:
        parts.append(f"【可见表】{', '.join(sorted(policy.allowed_tables))}")
    denied_lines: list[str] = []
    for table, cols in sorted(policy.denied_columns.items()):
        if cols:
            denied_lines.append(f"{table}: {', '.join(sorted(cols))}")
    if denied_lines:
        parts.append("【禁止字段】\n" + "\n".join(f"- {line}" for line in denied_lines))
    return "\n".join(parts)


def _compute_grants_hash(policy: EffectivePolicy) -> str:
    payload = {
        "grants": policy.data_grants,
        "tables": sorted(policy.allowed_tables),
        "denied": {k: sorted(v) for k, v in policy.denied_columns.items()},
        "scopes": policy.active_scopes,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _build_scope_hints(
    data_grants: dict[str, list[Any]],
    table_bindings: dict[str, list[tuple[str, str]]],
    active_scopes: dict[str, Any],
) -> str:
    """按绑定列动态生成 Prompt 提示，无硬编码列名。"""
    if not data_grants:
        return "无行级授权"
    lines: list[str] = []
    for dim_code, values in sorted(data_grants.items()):
        val_preview = ", ".join(str(v) for v in values[:8])
        if len(values) > 8:
            val_preview += "…"
        active = active_scopes.get(dim_code)
        active_part = f"；当前上下文={active}" if active is not None else ""
        binding_cols = sorted(
            {col for bindings in table_bindings.values() for d, col in bindings if d == dim_code}
        )
        col_hint = f"（绑定列：{', '.join(binding_cols)}）" if binding_cols else ""
        lines.append(f"- 维度 {dim_code}{col_hint}：允许值 IN ({val_preview}){active_part}")
    lines.append("- 多维度同时授权时 WHERE 条件须 AND 组合")
    lines.append("- 不得查询 grant 列表外的维度取值")
    return "\n".join(lines)


async def load_effective_policy(
    session: AsyncSession,
    ctx: UserContext,
    *,
    settings: Settings,
    global_whitelist: frozenset[str] | None = None,
) -> EffectivePolicy | None:
    """
    加载用户有效数据权限。

    `POLICY_DATA_SCOPE_ENABLED=false` 时返回 None（沿用全局白名单 + sch_id Flag）。
    ADMIN 默认 bypass；其余角色无 grant 时 Fail-closed。
    """
    if not settings.policy_data_scope_enabled:
        return None

    whitelist = global_whitelist or get_allowed_tables()
    repo = ScopeRepository(session)

    if ctx.role == UserRole.ADMIN:
        policy = EffectivePolicy(
            data_grants={},
            table_bindings=await repo.load_table_bindings(),
            allowed_tables=whitelist,
            denied_columns=await repo.load_denied_columns(ctx.user_id),
            is_admin_bypass=True,
            active_scopes=dict(ctx.active_scopes or {}),
        )
        policy.grants_hash = _compute_grants_hash(policy)
        return policy

    data_grants = await repo.load_data_grants(ctx.user_id)
    table_grants = await repo.load_table_grants(ctx.user_id)
    bindings = await repo.load_table_bindings()
    denied = await repo.load_denied_columns(ctx.user_id)

    if not data_grants and settings.policy_default_deny:
        raise PolicyError("NO_DATA_SCOPE", "无数据授权，无法问数")

    if table_grants:
        allowed = frozenset(t for t in table_grants if t in whitelist)
    else:
        allowed = frozenset() if settings.policy_default_deny else whitelist

    if settings.policy_default_deny and not allowed:
        raise PolicyError("NO_DATA_SCOPE", "无表级授权，无法问数")

    active_scopes = dict(ctx.active_scopes or {})
    for dim_code, values in data_grants.items():
        if dim_code in active_scopes:
            av = active_scopes[dim_code]
            if av not in values:
                raise PolicyError(
                    "SCOPE_FORBIDDEN",
                    f"当前上下文维度 {dim_code}={av} 不在授权范围内",
                )

    policy = EffectivePolicy(
        data_grants=data_grants,
        table_bindings=bindings,
        allowed_tables=allowed,
        denied_columns=denied,
        scope_sql_hints=_build_scope_hints(data_grants, bindings, active_scopes),
        is_admin_bypass=False,
        active_scopes=active_scopes,
    )
    policy.grants_hash = _compute_grants_hash(policy)
    return policy
