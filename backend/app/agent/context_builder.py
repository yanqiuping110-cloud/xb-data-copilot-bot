"""
多阶段召回后的合并、过滤与 LLM 上下文拼装。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.example_ranker import rank_curated_examples_for_prompt
from app.ask.semantic_repository import SemanticRepository
from app.core.context import UserContext
from app.meta.effective import effective_description
from app.meta.repository import ColumnMetaRow, MetaRepository, RelationRow, TableMetaRow, parse_alias_json
from app.policy.role_policy import build_llm_sql_generation_constraints, build_role_context_header
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
    收集候选表上 filter 角色字段的默认过滤说明。

    运营在 description_manual 中维护「默认 status=1」等口径时，此处单独注入 Prompt。
    """
    hints: list[str] = []
    for table_name in table_names:
        table = await repo.find_table_by_name(table_name)
        if not table:
            continue
        cols = await repo.list_columns(table.id)
        for col in cols:
            if col.status != 1 or col.column_role != "filter":
                continue
            desc = effective_description(col.description_manual, col.column_comment_auto)
            if not desc:
                continue
            hints.append(f"- 使用 {table_name} 时：{col.column_name} — {desc}")
    return hints


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
    es_table_recall = any(t.recall_mode == "es_vector" for t in merged.recalled_tables)

    for t in merged.recalled_tables:
        if not _is_allowed_table(t.table_name):
            continue
        if es_table_recall and t.score < settings.table_recall_score_min:
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
    """在候选表内筛选 Prompt 字段（recall_enabled + 召回得分 + JOIN 键/角色必留）。"""
    rels = relations if relations is not None else await repo.list_relations()
    table_set = set(merged.table_names)
    join_keys = _join_key_columns(rels, table_set)
    recalled_scores = {(c.table_name, c.column_name): c.score for c in merged.columns}

    prompt_columns: dict[str, list[str]] = {}
    for table_name in merged.table_names:
        table = await repo.find_table_by_name(table_name)
        if not table or table.status != 1:
            continue
        cols = await repo.list_columns(table.id)
        scored: list[tuple[float, str, ColumnMetaRow]] = []

        for col in cols:
            if col.status != 1:
                continue
            score = recalled_scores.get((table_name, col.column_name), 0.0)
            is_join_key = (table_name, col.column_name) in join_keys
            is_enabled = col.recall_enabled == 1

            if not is_enabled and not is_join_key:
                continue

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
    sem_repo = SemanticRepository(copilot_session)
    allowed = sorted(get_allowed_tables())
    cfg = settings or get_settings()
    example_top_k = cfg.curated_example_top_k
    example_min_score = cfg.curated_example_min_score

    parts: list[str] = [
        build_role_context_header(ctx, settings=cfg),
        "",
    ]
    if memory_prompt_text:
        parts.append(memory_prompt_text)
        parts.append("")

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
            desc = effective_description(table.description_manual, table.table_comment_auto)
            line = f"- {table.table_name}"
            if desc:
                line += f"：{desc}"
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
                col_map[table.table_name] = await meta_repo.get_column_map(table.id)

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
                    desc = effective_description(col.description_manual, col.column_comment_auto)
                    item = col.column_name
                    if desc:
                        item += f"({desc})"
                    aliases = parse_alias_json(col.alias_json)
                    if aliases:
                        item += f"[{','.join(aliases)}]"
                    col_parts.append(item)
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

    examples = await sem_repo.list_sql_examples()
    ranked = rank_curated_examples_for_prompt(
        question,
        ctx,
        examples,
        top_k=example_top_k,
        min_score=example_min_score,
    )
    if ranked:
        parts.append("【相似样例 SQL（仅供参考，勿照搬若不符合问句）】")
        for ex, relevance in ranked:
            parts.append(f"问法示例：{ex.question_pattern}（相关度={relevance}）")
            parts.append(f"SQL：{ex.sql_text[:500]}")
            parts.append("")

    parts.append("【生成约束】")
    parts.extend(build_llm_sql_generation_constraints(ctx, settings=cfg))

    return "\n".join(parts)


def _format_tool_observations(observations: list[dict], *, max_chars: int = 4000) -> list[str]:
    """将 Agent 工具观察格式化为 Prompt 段落。"""
    lines: list[str] = ["【Agent 工具观察】"]
    used = len(lines[0])
    for obs in observations[:12]:
        tool = obs.get("tool")
        result = obs.get("result") or {}
        args = obs.get("args") or {}
        if result.get("error"):
            line = f"- {tool}({args}): 错误 {result.get('error')} {result.get('message', '')}"
        elif tool == "run_probe_sql":
            cols = result.get("columns") or []
            rows = result.get("rows") or []
            line = f"- run_probe_sql: 列={cols} 样例行={rows[:3]}"
        elif "columns" in result and isinstance(result["columns"], list):
            cols = result["columns"][:8]
            line = f"- describe_table({args.get('table')}): {cols}"
        elif "relations" in result:
            rels = (result.get("relations") or [])[:4]
            line = f"- list_relations: {rels}"
        elif "path" in result:
            line = f"- get_join_path: {result.get('path')}"
        elif "metrics" in result:
            line = f"- search_metrics: count={result.get('count', len(result.get('metrics') or []))}"
        elif "values" in result:
            line = f"- search_field_values: count={result.get('count', len(result.get('values') or []))}"
        else:
            line = f"- {tool}: count={result.get('count', 'ok')}"
        if used + len(line) > max_chars:
            lines.append("- …（观察截断）")
            break
        lines.append(line)
        used += len(line)
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
    if memory_prompt_text:
        parts.extend([memory_prompt_text, ""])

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
            parts.append("【候选表字段（仅可使用下列列名）】")
            meta_repo = MetaRepository(copilot_session)
            for table_name in merged.table_names[:6]:
                names = merged.prompt_columns.get(table_name, [])
                if names:
                    parts.append(f"- {table_name}: {', '.join(names[:15])}")
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
        parts.extend(_format_tool_observations(observations))
        parts.append("")

    parts.append(f"【用户问句】{question}")
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
