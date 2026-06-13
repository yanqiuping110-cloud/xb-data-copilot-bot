"""
代码 artifact LLM 摘要 enrichment（§11.8.2 · 第 11 周）。

用法:
  python scripts/enrich_code_artifacts.py --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm_sql import build_llm
from app.code.index_text import build_code_search_text
from app.code.repository import CodeKnowledgeRepository
from app.db.copilot import get_session_factory
from config.settings import get_settings


async def _enrich(limit: int) -> int:
    settings = get_settings()
    llm = build_llm(settings)
    factory = get_session_factory()
    async with factory() as session:
        repo = CodeKnowledgeRepository(session)
        rows = await repo.list_artifacts(limit=limit)
        updated = 0
        for row in rows:
            if row.summary_text and len(row.summary_text) > 80:
                continue
            tables = []
            if row.tables_json:
                try:
                    tables = json.loads(row.tables_json)
                except json.JSONDecodeError:
                    tables = []
            snippet = (row.raw_snippet or row.title)[:2000]
            system = "你是业务报表口径分析助手。根据代码片段输出 JSON：{\"summary\":\"一句话业务口径\",\"dimensions\":[\"维度1\"]}"
            user = f"标题：{row.title}\n类型：{row.artifact_type}\n片段：{snippet}"
            try:
                resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
                content = resp.content if isinstance(resp.content, str) else str(resp.content)
                parsed = json.loads(content[content.index("{") : content.rindex("}") + 1])
                summary = str(parsed.get("summary") or row.title)
                dims = parsed.get("dimensions") or []
                dims_json = json.dumps(dims, ensure_ascii=False) if dims else None
                search_text = build_code_search_text(
                    title=row.title,
                    summary_text=summary,
                    tables=tables if isinstance(tables, list) else [],
                    artifact_type=row.artifact_type,
                )
                await repo.update_artifact_summary(
                    row.id,
                    summary_text=summary,
                    dimensions_json=dims_json,
                    search_text=search_text,
                )
                updated += 1
                print(f"[OK] artifact={row.id}")
            except Exception as exc:
                print(f"[SKIP] artifact={row.id} {exc}")
        print(f"已 enrichment {updated}/{len(rows)} 条")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    return asyncio.run(_enrich(args.limit))


if __name__ == "__main__":
    sys.exit(main())
