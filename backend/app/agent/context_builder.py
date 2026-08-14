"""
多阶段召回后的合并、过滤与 LLM 上下文拼装。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.meta.effective import effective_description
from app.meta.table_description import (
    table_default_where,
    table_effective_description,
)
from app.meta.glossary_repository import GlossaryRepository
from app.meta.glossary_service import format_glossary_prompt_lines, recall_glossary_for_question
from app.meta.repository import ColumnMetaRow, MetaRepository, RelationRow, TableMetaRow, parse_alias_json
from app.policy.role_policy import build_llm_sql_generation_constraints, build_role_context_header
from app.policy.effective_policy import build_scope_prompt_sections
from app.security.prompt_boundary import sanitize_recall_text
from app.retrieval.hybrid import (
    HybridRecallResult,
    RecalledColumn,
    RecalledFieldValue,
    RecalledMetric,
    RecalledTable,
)
from app.retrieval.unified import boost_tables_by_code_artifacts
from app.sql.whitelist import get_allowed_tables
from config.settings import Settings, get_settings


@dataclass
class MergedRecallContext:
    """合并过滤后的结构化召回上下文。"""

    keywords: list[str]
    recall_mode: str
    recalled_tables: list[RecalledTable] = field(default_factory=list)
    columns: list[RecalledColumn] = field(default_factory=list)
    metrics: list[RecalledMetric] = field(default_factory=list)
    field_values: list[RecalledFieldValue] = field(default_factory=list)
    code_artifacts: list = field(default_factory=list)
    tables: list[TableMetaRow] = field(default_factory=list)
    table_names: list[str] = field(default_factory=list)
    prompt_columns: dict[str, list[str]] = field(default_factory=dict)


def _effective_allowed_table_set(ctx: UserContext) -> frozenset[str]:
    """当前问数有效表白名单（含 EffectivePolicy 收窄）。"""
    policy = getattr(ctx, "effective_policy", None)
    if policy is not None and getattr(policy, "allowed_tables", None):
        return frozenset(policy.allowed_tables)
    return get_allowed_tables()


def _format_sql_literal(value_text: str) -> str:
    """字段取值映射为 SQL 字面量。"""
    text = (value_text or "").strip()
    if not text:
        return "''"
    if text.isdigit():
        return text
    if text.replace(".", "", 1).isdigit():
        return text
    escaped = text.replace("'", "''")
    return f"'{escaped}'"


def _build_field_value_filter_lines(field_values: list[RecalledFieldValue]) -> list[str]:
    """将召回的字段取值转为必须在 WHERE 中使用的过滤说明。"""
    lines: list[str] = []
    for fv in field_values[:10]:
        label = fv.display_label or fv.value_text
        literal = _format_sql_literal(fv.value_text)
        lines.append(
            f"- 问句匹配「{label}」→ 必须过滤 {fv.table_name}.{fv.column_name} = {literal}"
            f"（JOIN 后写为 {{别名}}.{fv.column_name} = {literal}）"
        )
    return lines


async def _collect_default_filter_hints(
    repo: MetaRepository,
    table_names: list[str],
) -> list[str]:
    """
    收集候选表默认过滤说明：表级 default_where + filter 角色字段描述。
    """
    hints: list[str] = []
    for table_name in table_names:
        table = await repo.find_table_by_name(table_name)
        if not table:
            continue
        where = table_default_where(table)
        if where:
            hints.append(f"- 使用 {table_name} 时必须附加 WHERE 条件：{where}")
        cols = await repo.list_recall_columns(table.id)
        for col in cols:
            if col.column_role != "filter":
                continue
            desc = effective_description(col.description_manual, col.column_comment_auto)
            if not desc:
                continue
            hints.append(f"- 使用 {table_name} 时：{col.column_name} — {desc}")
    return hints


def format_memory_reference_prompt(memory_prompt_text: str) -> str:
    """会话记忆降为参考信息，置于 Prompt 末尾且不得覆盖元数据口径。"""
    text = (memory_prompt_text or "").strip()
    if not text:
        return ""
    return (
        "【会话记忆（仅供参考，权重低于知识库召回与元数据 default_where；"
        "不得据此省略表默认过滤或编造用户未提及的条件）】\n"
        f"{text}"
    )


def apply_kb_recall_limits(
    merged: MergedRecallContext,
    settings: Settings,
) -> MergedRecallContext:
    """知识库直出：按召回分排序取 Top 表，不做二次加权筛选。"""
    max_tables = settings.recall_top_k_table
    table_names: list[str] = []
    for t in sorted(merged.recalled_tables, key=lambda x: x.score, reverse=True):
        if not _is_allowed_table(t.table_name):
            continue
        if t.table_name in table_names:
            continue
        table_names.append(t.table_name)
        if len(table_names) >= max_tables:
            break
    merged.table_names = table_names
    allowed_set = set(table_names)
    merged.recalled_tables = [
        t for t in merged.recalled_tables if t.table_name in allowed_set
    ][:max_tables]
    merged.columns = merged.columns[: settings.recall_top_k_column]
    merged.metrics = merged.metrics[: settings.recall_top_k_metric]
    merged.field_values = merged.field_values[: settings.recall_top_k_value]
    return merged


async def build_prompt_columns_from_kb_recall(
    merged: MergedRecallContext,
    repo: MetaRepository,
    settings: Settings,
) -> dict[str, list[str]]:
    """从知识库字段召回组装 Prompt 字段清单（deleted=0 AND status=1 AND recall_enabled=1）。"""
    table_names = merged.table_names
    prompt_columns: dict[str, list[str]] = {name: [] for name in table_names}
    recalled_by_table: dict[str, list[str]] = {}
    for col in merged.columns:
        if col.table_name not in prompt_columns:
            continue
        recalled_by_table.setdefault(col.table_name, []).append(col.column_name)

    rels = await repo.list_relations()
    join_keys = _join_key_columns(rels, set(table_names))

    for table_name in table_names:
        table = await repo.find_table_by_name(table_name)
        if not table or table.status != 1:
            prompt_columns[table_name] = recalled_by_table.get(table_name, [])
            continue
        cols = await repo.list_recall_columns(table.id)
        recall_names = {c.column_name for c in cols}
        must_include: list[str] = []
        scored_names: list[str] = []
        for col in cols:
            is_join = (table_name, col.column_name) in join_keys
            is_must = (
                is_join
                or col.column_role in ("filter", "pk", "fk", "time")
                or col.column_name == table.sch_id_column
            )
            if is_must:
                must_include.append(col.column_name)
            else:
                scored_names.append(col.column_name)

        selected: list[str] = []
        seen: set[str] = set()
        for name in must_include + recalled_by_table.get(table_name, []) + scored_names:
            if name in seen or name not in recall_names:
                continue
            seen.add(name)
            selected.append(name)
            if len(selected) >= settings.max_columns_per_table:
                break
        prompt_columns[table_name] = selected

    return prompt_columns


async def finalize_kb_recall(
    merged: MergedRecallContext,
    repo: MetaRepository,
    settings: Settings,
) -> MergedRecallContext:
    """合并召回后定稿：限流 + 字段清单（替代 filter_tables/columns/metrics 节点）。"""
    merged = apply_kb_recall_limits(merged, settings)
    merged.prompt_columns = await build_prompt_columns_from_kb_recall(merged, repo, settings)
    if merged.code_artifacts:
        merged.recalled_tables = boost_tables_by_code_artifacts(
            merged.recalled_tables,
            merged.code_artifacts,
        )
    return merged


def merge_retrieved_info(recall: HybridRecallResult) -> MergedRecallContext:
    """合并多路召回为统一结构（不做过滤）。"""
    return MergedRecallContext(
        keywords=recall.keywords,
        recall_mode=recall.recall_mode,
        recalled_tables=list(recall.tables),
        columns=list(recall.columns),
        metrics=list(recall.metrics),
        field_values=list(recall.field_values),
        code_artifacts=list(recall.code_artifacts),
    )


def _allowed_table_set() -> frozenset[str]:
    """当前问数白名单（status=1 的 table_meta）。"""
    return get_allowed_tables()


def _is_allowed_table(table_name: str) -> bool:
    return table_name.lower() in _allowed_table_set()


def _filter_relevant_tables_text(relevant_tables: str | None) -> str | None:
    """指标 relevant_tables 中剔除已停用/不在白名单的表。"""
    if not relevant_tables:
        return None
    kept = [
        name.strip()
        for name in relevant_tables.replace(" ", "").split(",")
        if name.strip() and _is_allowed_table(name.strip())
    ]
    return ",".join(kept) if kept else None


def expand_table_names_by_relations(
    table_names: list[str],
    relations: list[RelationRow],
    *,
    max_tables: int,
    allowed: frozenset[str] | None = None,
) -> list[str]:
    """候选表关系扩展：召回主表时自动纳入关联表。"""
    if not table_names or not relations:
        return table_names[:max_tables]

    allowed_set = allowed if allowed is not None else _allowed_table_set()
    seen = set(table_names)
    expanded = list(table_names)
    for name in list(table_names):
        for rel in relations:
            if rel.status != 1:
                continue
            other: str | None = None
            if rel.from_table_name == name:
                other = rel.to_table_name
            elif rel.to_table_name == name:
                other = rel.from_table_name
            if other and other not in seen:
                if other.lower() not in allowed_set:
                    continue
                seen.add(other)
                expanded.append(other)
                if len(expanded) >= max_tables:
                    return expanded[:max_tables]
    return expanded[:max_tables]


def filter_tables(
    merged: MergedRecallContext,
    settings: Settings,
    *,
    relations: list[RelationRow] | None = None,
) -> MergedRecallContext:
    """
    表级召回为主筛选候选表，指标/字段/取值作辅助加权，再关系扩展并截断。
    仅保留问数白名单（status=1）内的表。
    """
    allowed = _allowed_table_set()
    table_scores: dict[str, float] = {}
    vector_table_recall = any(
        t.recall_mode in ("es_vector", "vector", "vector_hybrid") for t in merged.recalled_tables
    )

    for t in merged.recalled_tables:
        if not _is_allowed_table(t.table_name):
            continue
        if vector_table_recall and t.score < settings.table_recall_score_min:
            continue
        table_scores[t.table_name] = max(table_scores.get(t.table_name, 0.0), t.score)

    for metric in merged.metrics:
        if metric.relevant_tables:
            for name in metric.relevant_tables.replace(" ", "").split(","):
                name = name.strip()
                if name and _is_allowed_table(name):
                    table_scores[name] = table_scores.get(name, 0.0) + metric.score * 0.5

    for col in merged.columns:
        if not _is_allowed_table(col.table_name):
            continue
        table_scores[col.table_name] = table_scores.get(col.table_name, 0.0) + col.score * 0.2

    for fv in merged.field_values:
        if not _is_allowed_table(fv.table_name):
            continue
        table_scores[fv.table_name] = table_scores.get(fv.table_name, 0.0) + fv.score * 0.1

    if not table_scores and merged.recalled_tables:
        for t in merged.recalled_tables[: settings.max_tables_in_prompt]:
            if _is_allowed_table(t.table_name):
                table_scores[t.table_name] = t.score

    ranked = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)
    merged.table_names = [name for name, _ in ranked[: settings.recall_top_k_table]]

    if relations:
        merged.table_names = expand_table_names_by_relations(
            merged.table_names,
            relations,
            max_tables=settings.max_tables_in_prompt,
            allowed=allowed,
        )
    else:
        merged.table_names = merged.table_names[: settings.max_tables_in_prompt]

    merged.table_names = [n for n in merged.table_names if _is_allowed_table(n)]

    if merged.code_artifacts:
        merged.recalled_tables = boost_tables_by_code_artifacts(
            merged.recalled_tables,
            merged.code_artifacts,
        )

    return merged


def filter_metrics(merged: MergedRecallContext, *, top_n: int = 5) -> MergedRecallContext:
    """保留得分最高的指标。"""
    merged.metrics = sorted(merged.metrics, key=lambda m: m.score, reverse=True)[:top_n]
    return merged


def _join_key_columns(relations: list[RelationRow], table_names: set[str]) -> set[tuple[str, str]]:
    """候选表在关系定义中出现的 JOIN 键。"""
    keys: set[tuple[str, str]] = set()
    for rel in relations:
        if rel.status != 1:
            continue
        if rel.from_table_name in table_names:
            keys.add((rel.from_table_name, rel.from_column))
        if rel.to_table_name in table_names:
            keys.add((rel.to_table_name, rel.to_column))
    return keys


async def filter_columns_for_prompt(
    merged: MergedRecallContext,
    repo: MetaRepository,
    settings: Settings,
    *,
    relations: list[RelationRow] | None = None,
) -> MergedRecallContext:
    """在候选表内筛选 Prompt 字段（deleted=0 AND status=1 AND recall_enabled=1）。"""
    rels = relations if relations is not None else await repo.list_relations()
    table_set = set(merged.table_names)
    join_keys = _join_key_columns(rels, table_set)
    recalled_scores = {(c.table_name, c.column_name): c.score for c in merged.columns}

    prompt_columns: dict[str, list[str]] = {}
    for table_name in merged.table_names:
        table = await repo.find_table_by_name(table_name)
        if not table or table.status != 1:
            continue
        cols = await repo.list_recall_columns(table.id)
        scored: list[tuple[float, str, ColumnMetaRow]] = []

        for col in cols:
            score = recalled_scores.get((table_name, col.column_name), 0.0)
            is_join_key = (table_name, col.column_name) in join_keys

            if col.column_role in ("pk", "fk", "time", "filter"):
                score += 50.0
            if col.column_name == table.sch_id_column:
                score += 50.0
            if is_join_key:
                score += 100.0
            if col.column_role == "filter":
                score += 100.0

            scored.append((score, col.column_name, col))

        scored.sort(key=lambda x: x[0], reverse=True)
        seen: set[str] = set()
        selected: list[str] = []
        must_include = {
            name
            for _, name, col in scored
            if (table_name, name) in join_keys or col.column_role == "filter"
        }
        for name in sorted(must_include):
            if name not in seen:
                seen.add(name)
                selected.append(name)
        for _, name, _ in scored:
            if name in seen:
                continue
            seen.add(name)
            selected.append(name)
            if len(selected) >= settings.max_columns_per_table:
                break
        prompt_columns[table_name] = selected

    merged.prompt_columns = prompt_columns
    return merged


async def enrich_tables_from_mysql(
    merged: MergedRecallContext,
    repo: MetaRepository,
) -> MergedRecallContext:
    """从 MySQL 补全候选表元数据。"""
    tables: list[TableMetaRow] = []
    for name in merged.table_names:
        row = await repo.find_table_by_name(name)
        if row and row.status == 1:
            tables.append(row)
    merged.tables = tables
    return merged


async def build_llm_context_text(
    question: str,
    merged: MergedRecallContext,
    copilot_session: AsyncSession,
    ctx: UserContext,
    *,
    settings: Settings | None = None,
    memory_prompt_text: str = "",
) -> str:
    """
    将结构化召回结果拼为 generate_sql Prompt 上下文。

    无召回时仍输出表白名单与生成约束。
    """
    meta_repo = MetaRepository(copilot_session)
    cfg = settings or get_settings()
    policy = getattr(ctx, "effective_policy", None)

    parts: list[str] = [
        build_role_context_header(ctx, settings=cfg),
        "",
    ]
    scope_block = build_scope_prompt_sections(policy)
    if scope_block:
        parts.extend([scope_block, ""])
    memory_block = format_memory_reference_prompt(memory_prompt_text)

    if cfg.glossary_recall_enabled:
        try:
            glossary_repo = GlossaryRepository(copilot_session)
            matched = await recall_glossary_for_question(
                glossary_repo,
                question,
                scope_role=ctx.role.value if ctx.role else None,
                top_k=cfg.glossary_recall_top_k,
            )
            parts.extend(
                format_glossary_prompt_lines(
                    matched,
                    sanitize=cfg.prompt_sanitize_recall_enabled,
                )
            )
        except Exception:
            pass

    allowed = sorted(get_allowed_tables())
    if policy is not None:
        allowed = sorted(policy.allowed_tables) if policy.allowed_tables else allowed

    parts.extend(
        [
        f"【召回模式】{merged.recall_mode}",
        f"【问句关键词】{', '.join(merged.keywords) or '（整句）'}",
        "",
        "【允许查询的业务表】",
        ", ".join(allowed) or "（未配置，使用默认表）",
        "",
        ]
    )

    if merged.tables:
        parts.append("【候选表说明（表级召回）】")
        for table in merged.tables:
            desc = table_effective_description(table)
            if desc and cfg.prompt_sanitize_recall_enabled:
                desc, _ = sanitize_recall_text(desc, enabled=True)
            line = f"- {table.table_name}"
            if desc:
                line += f"：{desc}"
            default_where = table_default_where(table)
            if default_where:
                line += f"；默认条件：{default_where}"
            if table.grain:
                line += f"；粒度：{table.grain}"
            line += f"；学校字段：{table.sch_id_column}"
            parts.append(line)
        parts.append("")

        if merged.table_names:
            relations = await meta_repo.list_relations()
            relevant = [
                r
                for r in relations
                if r.status == 1
                and (
                    r.from_table_name in merged.table_names
                    or r.to_table_name in merged.table_names
                )
            ]
            if relevant:
                parts.append("【表关系与 JOIN 提示】")
                for r in relevant[:12]:
                    hint = r.join_hint or f"{r.from_table_name}.{r.from_column} = {r.to_table_name}.{r.to_column}"
                    parts.append(f"- {r.from_table_name} → {r.to_table_name}（{r.relation_type}）：{hint}")
                parts.append("")

        if merged.prompt_columns:
            parts.append("【候选表字段清单（只能使用下列真实列名，禁止编造）】")
            col_map: dict[str, dict[str, ColumnMetaRow]] = {}
            for table in merged.tables:
                col_map[table.table_name] = await meta_repo.get_recall_column_map(table.id)

            for table_name in merged.table_names:
                names = merged.prompt_columns.get(table_name, [])
                if not names:
                    continue
                col_parts: list[str] = []
                by_name = col_map.get(table_name, {})
                for col_name in names:
                    col = by_name.get(col_name)
                    if not col:
                        col_parts.append(col_name)
                        continue
                    col_parts.append(format_column_prompt_item(col_name, col))
                parts.append(f"- {table_name}: {', '.join(col_parts)}")
            parts.append("")

    if merged.recalled_tables:
        parts.append("【相关表（表级召回）】")
        for t in merged.recalled_tables[:10]:
            parts.append(f"- {t.table_name}：{t.search_text[:120]}（score={t.score:.3f}）")
        parts.append("")

    if merged.code_artifacts:
        parts.append("【相关业务接口/报表口径（代码知识）】")
        for art in merged.code_artifacts[:5]:
            summary = (getattr(art, "summary_text", None) or art.search_text)[:200]
            tables_hint = ", ".join(getattr(art, "tables", []) or [])[:120]
            parts.append(
                f"- [{getattr(art, 'artifact_type', 'artifact')}] {art.title}"
                f"（artifact_id={art.artifact_id}，表={tables_hint or '—'}）：{summary}"
            )
        parts.append("")

    if merged.columns:
        parts.append("【相关字段（字段召回）】")
        for col in merged.columns[:15]:
            parts.append(f"- {col.table_name}.{col.column_name}：{col.search_text[:120]}")
        parts.append("")

    if merged.metrics:
        parts.append("【相关指标与口径】")
        for m in merged.metrics:
            line = f"- {m.metric_name}（{m.metric_code}）"
            if m.formula_text:
                line += f"；公式：{m.formula_text}"
            relevant = _filter_relevant_tables_text(m.relevant_tables)
            if relevant:
                line += f"；相关表：{relevant}"
            parts.append(line)
        parts.append("")

    default_filters = await _collect_default_filter_hints(meta_repo, merged.table_names)
    if default_filters:
        parts.append("【表默认过滤条件（查询该表时必须附加到 WHERE，除非用户明确指定其他条件）】")
        parts.extend(default_filters)
        parts.append("")

    if merged.field_values:
        parts.append("【问句匹配的过滤条件（必须在 WHERE 中使用）】")
        parts.extend(_build_field_value_filter_lines(merged.field_values))
        parts.append("")
        parts.append("【字段取值映射（枚举/别名 → 库内值）】")
        for fv in merged.field_values[:10]:
            label = fv.display_label or fv.value_text
            parts.append(f"- {fv.table_name}.{fv.column_name}：「{label}」→ {fv.value_text}")
        parts.append("")

    if memory_block:
        parts.append(memory_block)
        parts.append("")

    parts.append("【生成约束】")
    parts.extend(build_llm_sql_generation_constraints(ctx, settings=cfg))

    return "\n".join(parts)


_AGENT_PROMPT_COLUMNS_MAX_CHARS_PER_TABLE = 1500
_AGENT_TOOL_OBS_MAX_CHARS = 6000


def format_column_prompt_item(
    col_name: str,
    col: ColumnMetaRow | None = None,
) -> str:
    """字段 Prompt 片段：列名(描述)[别名]。"""
    if col is None:
        return col_name
    desc = effective_description(col.description_manual, col.column_comment_auto)
    item = col.column_name
    if desc:
        item += f"({desc})"
    aliases = parse_alias_json(col.alias_json)
    if aliases:
        item += f"[{','.join(aliases)}]"
    return item


def format_prompt_column_line(
    table_name: str,
    column_names: list[str],
    by_name: dict[str, ColumnMetaRow],
    *,
    max_chars: int | None = None,
) -> str:
    """拼装单表字段清单，超出 max_chars 时截断并标注。"""
    limit = max_chars if max_chars is not None else _AGENT_PROMPT_COLUMNS_MAX_CHARS_PER_TABLE
    col_parts: list[str] = []
    used = 0
    prefix = f"- {table_name}: "
    used += len(prefix)
    truncated = False
    for col_name in column_names:
        item = format_column_prompt_item(col_name, by_name.get(col_name))
        sep = ", " if col_parts else ""
        if used + len(sep) + len(item) > limit:
            truncated = True
            break
        col_parts.append(item)
        used += len(sep) + len(item)
    line = prefix + ", ".join(col_parts)
    if truncated:
        line += f" …（共 {len(column_names)} 列，已截断）"
    return line


def _normalize_meta_table_name(name: str) -> str | None:
    """过滤 Java 类名等非库表标识，返回小写表名。"""
    raw = (name or "").strip()
    if not raw:
        return None
    if "." in raw or raw[0].isupper():
        return None
    return raw.lower()


def _pick_candidate_tables(table_names: list[str], *, limit: int = 6) -> list[str]:
    """从召回表名中保留有效候选库表（蛇形命名）。"""
    picked: list[str] = []
    seen: set[str] = set()
    for raw in table_names:
        name = _normalize_meta_table_name(raw)
        if not name or name in seen:
            continue
        seen.add(name)
        picked.append(name)
        if len(picked) >= limit:
            break
    return picked


def _sort_observations_for_prompt(
    observations: list[dict],
    candidate_tables: list[str] | None,
) -> list[dict]:
    """describe_table 观察优先展示候选表。"""
    if not observations or not candidate_tables:
        return observations
    priority = {_normalize_meta_table_name(t): i for i, t in enumerate(candidate_tables)}
    priority = {k: v for k, v in priority.items() if k}

    def sort_key(obs: dict) -> tuple[int, int]:
        if obs.get("tool") != "describe_table":
            return (1, 0)
        table = _normalize_meta_table_name(str((obs.get("args") or {}).get("table") or ""))
        if table in priority:
            return (0, priority[table])
        return (0, 999)

    return sorted(observations, key=sort_key)


def _format_describe_table_observation(table: str, result: dict) -> list[str]:
    """展开 describe_table 结果为多行字段定义。"""
    lines: list[str] = []
    desc = result.get("description")
    header = f"- describe_table({table})"
    if desc:
        header += f" 表说明：{desc}"
    lines.append(header)
    columns = result.get("columns") or []
    for col in columns[:30]:
        if not isinstance(col, dict):
            continue
        name = col.get("name") or "?"
        role = col.get("role")
        ctype = col.get("data_type")
        cdesc = col.get("description")
        aliases = col.get("aliases")
        if aliases is None and col.get("alias_json"):
            aliases = parse_alias_json(col.get("alias_json"))
        parts = [name]
        if ctype:
            parts.append(str(ctype))
        if role:
            parts.append(f"role={role}")
        if cdesc:
            parts.append(str(cdesc))
        if aliases:
            parts.append(f"别名[{','.join(str(a) for a in aliases)}]")
        lines.append(f"    · {' | '.join(parts)}")
    if len(columns) > 30:
        lines.append(f"    · …（另有 {len(columns) - 30} 列）")
    return lines


def _format_tool_observations(
    observations: list[dict],
    *,
    max_chars: int = _AGENT_TOOL_OBS_MAX_CHARS,
    candidate_tables: list[str] | None = None,
) -> list[str]:
    """将 Agent 工具观察格式化为 Prompt 段落。"""
    lines: list[str] = ["【Agent 工具观察】"]
    used = len(lines[0])
    ordered = _sort_observations_for_prompt(observations, candidate_tables)
    for obs in ordered[:12]:
        tool = obs.get("tool")
        result = obs.get("result") or {}
        args = obs.get("args") or {}
        block_lines: list[str] = []
        if result.get("error"):
            block_lines = [
                f"- {tool}({args}): 错误 {result.get('error')} {result.get('message', '')}"
            ]
        elif tool == "run_probe_sql":
            cols = result.get("columns") or []
            rows = result.get("rows") or []
            block_lines = [f"- run_probe_sql: 列={cols} 样例行={rows[:3]}"]
        elif tool == "describe_table" and isinstance(result.get("columns"), list):
            table = str(args.get("table") or result.get("table") or "")
            block_lines = _format_describe_table_observation(table, result)
        elif "relations" in result:
            rels = (result.get("relations") or [])[:4]
            block_lines = [f"- list_relations: {rels}"]
        elif "path" in result:
            block_lines = [f"- get_join_path: {result.get('path')}"]
        elif "metrics" in result:
            block_lines = [
                f"- search_metrics: count={result.get('count', len(result.get('metrics') or []))}"
            ]
        elif "values" in result:
            block_lines = [
                f"- search_field_values: count={result.get('count', len(result.get('values') or []))}"
            ]
        else:
            block_lines = [f"- {tool}: count={result.get('count', 'ok')}"]
        for line in block_lines:
            if used + len(line) + 1 > max_chars:
                lines.append("- …（观察截断）")
                return lines
            lines.append(line)
            used += len(line) + 1
    return lines


async def build_agent_context_text(
    question: str,
    merged: MergedRecallContext | None,
    copilot_session: AsyncSession,
    ctx: UserContext,
    *,
    plan: dict | None = None,
    observations: list[dict] | None = None,
    settings: Settings | None = None,
    memory_prompt_text: str = "",
) -> str:
    """
    Agent 路径专用上下文：种子召回摘要 + plan + 工具观察 + 约束。

    比 build_llm_context_text 更紧凑，避免重复注入全量召回后再叠观察导致 Prompt 膨胀。
    """
    cfg = settings or get_settings()
    allowed = sorted(get_allowed_tables())
    parts: list[str] = [
        build_role_context_header(ctx, settings=cfg),
        "",
    ]
    memory_block = format_memory_reference_prompt(memory_prompt_text)

    parts.extend(
        [
            "【允许查询的业务表】",
            ", ".join(allowed) or "（未配置）",
            "",
        ]
    )

    if merged is not None:
        parts.extend(
            [
                f"【种子召回】模式={merged.recall_mode}；关键词={', '.join(merged.keywords) or '（整句）'}",
                f"候选表：{', '.join(merged.table_names[:8]) or '（无）'}",
            ]
        )
        if merged.metrics:
            parts.append(
                "指标："
                + ", ".join(f"{m.metric_name}({m.metric_code})" for m in merged.metrics[:4])
            )
        if merged.field_values:
            parts.append(
                "过滤取值："
                + ", ".join(
                    f"{v.table_name}.{v.column_name}={v.value_text}"
                    for v in merged.field_values[:5]
                )
            )
        if merged.prompt_columns:
            parts.append("【候选表字段（仅可使用下列列名；括号内为口径，方括号为别名）】")
            meta_repo = MetaRepository(copilot_session)
            col_map: dict[str, dict[str, ColumnMetaRow]] = {}
            for table in merged.tables:
                col_map[table.table_name] = await meta_repo.get_recall_column_map(table.id)
            for table_name in merged.table_names[:6]:
                names = merged.prompt_columns.get(table_name, [])
                if names:
                    parts.append(
                        format_prompt_column_line(
                            table_name,
                            names,
                            col_map.get(table_name, {}),
                        )
                    )
        if merged.code_artifacts:
            parts.append("【相关业务接口/报表口径】")
            for art in merged.code_artifacts[:4]:
                summary = (getattr(art, "summary_text", None) or art.search_text)[:180]
                parts.append(f"- code:artifact:{art.artifact_id} {art.title}：{summary}")
        parts.append("")

    if plan:
        parts.append("【问句规划 plan】")
        parts.append(f"- complexity: {plan.get('complexity')}")
        parts.append(f"- intent: {plan.get('intent')}")
        if plan.get("query_shape"):
            parts.append(f"- query_shape: {plan.get('query_shape')}")
        if plan.get("aggregate_strategy"):
            parts.append(f"- aggregate_strategy: {plan.get('aggregate_strategy')}")
        if plan.get("anchor_table"):
            parts.append(f"- anchor_table: {plan.get('anchor_table')}")
        if plan.get("structure_reason"):
            parts.append(f"- structure_reason: {plan.get('structure_reason')}")
        for step in plan.get("steps") or []:
            goals = step.get("goal") or ""
            tools = ", ".join(step.get("needs_tool") or [])
            agg = step.get("aggregation") or ""
            pivot = step.get("pivot_hint") or ""
            extra = ""
            if agg:
                extra += f" aggregation={agg}"
            if pivot:
                extra += f" pivot={pivot}"
            parts.append(f"  步骤 {step.get('id')}: {goals}" + (f"（工具: {tools}）" if tools else "") + extra)
        parts.append("")

    if observations:
        candidate_tables = merged.table_names if merged is not None else []
        parts.extend(
            _format_tool_observations(observations, candidate_tables=candidate_tables)
        )
        parts.append("")

    parts.append(f"【用户问句】{question}")
    parts.append("")
    if memory_block:
        parts.append(memory_block)
        parts.append("")
    parts.append("【生成约束】")
    parts.extend(build_llm_sql_generation_constraints(ctx, settings=cfg))
    return "\n".join(parts)


def span_detail_from_merged(merged: MergedRecallContext) -> dict:
    """写入 copilot_ask_span 的召回摘要。"""
    return {
        "recall_mode": merged.recall_mode,
        "keywords": merged.keywords,
        "table_recall_count": len(merged.recalled_tables),
        "column_count": len(merged.columns),
        "metric_count": len(merged.metrics),
        "value_count": len(merged.field_values),
        "table_names": merged.table_names,
        "prompt_column_counts": {k: len(v) for k, v in merged.prompt_columns.items()},
        "tables": [
            {"table": t.table_name, "score": t.score, "mode": t.recall_mode}
            for t in merged.recalled_tables[:10]
        ],
        "columns": [
            {"table": c.table_name, "column": c.column_name, "score": c.score, "mode": c.recall_mode}
            for c in merged.columns[:8]
        ],
        "metrics": [
            {"code": m.metric_code, "score": m.score, "mode": m.recall_mode} for m in merged.metrics[:5]
        ],
        "values": [
            {
                "table": v.table_name,
                "column": v.column_name,
                "value": v.value_text,
                "score": v.score,
            }
            for v in merged.field_values[:5]
        ],
        "code_recall_count": len(merged.code_artifacts),
        "code_artifacts": [
            {
                "id": a.artifact_id,
                "title": a.title,
                "score": a.score,
                "type": getattr(a, "artifact_type", ""),
            }
            for a in merged.code_artifacts[:5]
        ],
    }
