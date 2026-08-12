"""
开源 Demo · Fixture 问数短路。

LLM_MODE=fixture 时：匹配预置问句 → 执行样例 SQL → 返回表格与解读。
无需云端 Key / Embedding；供 make demo-smoke 与 AI Agent 盲测。
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.schemas.ask import AskRequest, AskResponse
from app.sql.executor import execute_readonly
from config.settings import Settings, ROOT_DIR


def _repo_root(settings: Settings) -> Path:
    if settings.demo_root.strip():
        return Path(settings.demo_root).resolve()
    # backend/config → parents[2] = repo root when running from source;
    # in Docker image ROOT_DIR is /app, demo mounted at DEMO_ROOT.
    return ROOT_DIR.parent if (ROOT_DIR.parent / "demo").is_dir() else ROOT_DIR


def _questions_path(settings: Settings) -> Path:
    return _repo_root(settings) / "demo" / "profiles" / "_shared" / "questions.json"


def load_fixture_questions(settings: Settings) -> list[dict]:
    path = _questions_path(settings)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("questions") or [])


def _normalize(q: str) -> str:
    s = q.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def match_fixture(question: str, settings: Settings) -> dict | None:
    qn = _normalize(question)
    for item in load_fixture_questions(settings):
        candidates = [
            str(item.get("text") or ""),
            str(item.get("text_zh") or ""),
            str(item.get("id") or ""),
        ]
        for c in candidates:
            if not c:
                continue
            cn = _normalize(c)
            if qn == cn or cn in qn or qn in cn:
                return item
    return None


def _format_answer(template: str, columns: list[str], rows: list[list]) -> str:
    mapping: dict[str, str] = {}
    if rows and columns:
        for i, col in enumerate(columns):
            if i < len(rows[0]):
                mapping[col] = str(rows[0][i])
    try:
        return template.format(**mapping)
    except Exception:
        return template


async def handle_fixture_ask(
    body: AskRequest,
    ctx: UserContext,
    copilot_session: AsyncSession,
    settings: Settings,
) -> AskResponse:
    """Fixture 短路：命中预置问句则执行 SQL；否则返回友好提示。"""
    _ = ctx, copilot_session
    started = time.perf_counter()
    trace_id = body.trace_id or str(uuid.uuid4())
    matched = match_fixture(body.question, settings)
    if matched is None:
        known = [str(q.get("text") or q.get("text_zh") or "") for q in load_fixture_questions(settings)]
        hints = " | ".join(x for x in known if x)[:500]
        return AskResponse(
            trace_id=trace_id,
            session_id=body.session_id,
            status="error",
            degrade_level=3,
            error_code="FIXTURE_UNKNOWN_QUESTION",
            error_message=(
                "LLM_MODE=fixture: question not in demo presets. "
                f"Try one of: {hints}. Or set LLM_MODE=openai with a real API key."
            ),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    sql = str(matched.get("sql") or "").strip()
    try:
        columns, rows = await execute_readonly(sql, max_rows=settings.sql_default_limit)
    except Exception as exc:  # noqa: BLE001 — demo path: surface to client
        return AskResponse(
            trace_id=trace_id,
            session_id=body.session_id,
            status="error",
            degrade_level=2,
            sql=sql,
            error_code="FIXTURE_SQL_FAILED",
            error_message=f"Fixture SQL failed: {exc}",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    answer = _format_answer(
        str(matched.get("answer_template") or "OK"),
        columns,
        rows,
    )
    return AskResponse(
        trace_id=trace_id,
        session_id=body.session_id,
        status="ok",
        degrade_level=0,
        sql=sql,
        columns=columns,
        rows=rows,
        answer=answer,
        latency_ms=int((time.perf_counter() - started) * 1000),
        assembly_mode="fixture",
    )
