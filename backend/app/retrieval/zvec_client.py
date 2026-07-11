"""
Zvec 客户端：问数 collection 索引、向量+全文混合召回（RRF rerank）。
"""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any

import zvec
from zvec.model.param.query import Fts, Query

from config.settings import Settings

_ID_FIELDS: dict[str, str] = {
    "table": "table_id",
    "column": "column_id",
    "metric": "metric_id",
    "value": "field_value_id",
    "code_artifact": "artifact_id",
    "sql_example": "example_id",
}


def _fts_field() -> zvec.FieldSchema:
    return zvec.FieldSchema(
        name="search_text",
        data_type=zvec.DataType.STRING,
        nullable=True,
        index_param=zvec.FtsIndexParam(
            tokenizer_name="jieba",
            filters=["lowercase"],
        ),
    )


def _string_field(name: str, *, indexed: bool = False, nullable: bool = True) -> zvec.FieldSchema:
    index_param = zvec.InvertIndexParam() if indexed else None
    return zvec.FieldSchema(
        name=name,
        data_type=zvec.DataType.STRING,
        nullable=nullable,
        index_param=index_param,
    )


def _int_field(name: str, *, indexed: bool = False) -> zvec.FieldSchema:
    index_param = zvec.InvertIndexParam() if indexed else None
    return zvec.FieldSchema(
        name=name,
        data_type=zvec.DataType.INT64,
        nullable=True,
        index_param=index_param,
    )


def _vector_schema(dims: int) -> zvec.VectorSchema:
    return zvec.VectorSchema(
        name="embedding",
        data_type=zvec.DataType.VECTOR_FP32,
        dimension=dims,
        index_param=zvec.HnswIndexParam(metric_type=zvec.MetricType.COSINE),
    )


def _schema_for_suffix(suffix: str, dims: int) -> zvec.CollectionSchema:
    if suffix == "table":
        fields = [
            _fts_field(),
            _int_field("table_id", indexed=True),
            _string_field("table_name", indexed=True),
            _string_field("table_role"),
            _string_field("biz_domain"),
        ]
    elif suffix == "column":
        fields = [
            _fts_field(),
            _int_field("column_id", indexed=True),
            _int_field("table_id"),
            _string_field("table_name", indexed=True),
            _string_field("column_name"),
            _string_field("column_role"),
        ]
    elif suffix == "metric":
        fields = [
            _fts_field(),
            _int_field("metric_id", indexed=True),
            _string_field("metric_code"),
            _string_field("metric_name"),
            _string_field("relevant_tables"),
        ]
    elif suffix == "code_artifact":
        fields = [
            _fts_field(),
            _int_field("artifact_id", indexed=True),
            _int_field("repo_id"),
            _string_field("artifact_type"),
            _string_field("title"),
            _string_field("summary_text"),
            _string_field("tables_json"),
        ]
    elif suffix == "sql_example":
        fields = [
            _fts_field(),
            _int_field("example_id", indexed=True),
            _string_field("question_pattern"),
            _string_field("description"),
            _string_field("role_scope"),
        ]
    elif suffix == "value":
        fields = [
            _fts_field(),
            _int_field("field_value_id", indexed=True),
            _int_field("column_id"),
            _string_field("table_name", indexed=True),
            _string_field("column_name", indexed=True),
            _string_field("value_text"),
            _string_field("display_label"),
        ]
        return zvec.CollectionSchema(name=f"ask_{suffix}", fields=fields, vectors=[])
    else:
        fields = [_fts_field()]

    return zvec.CollectionSchema(
        name=f"ask_{suffix}",
        fields=fields,
        vectors=[_vector_schema(dims)],
    )


def _escape_filter_string(value: str) -> str:
    return value.replace("'", "''")


def build_table_name_filter(table_names: set[str] | None) -> str | None:
    """构造 column 召回用的 table_name IN 过滤表达式。"""
    if not table_names:
        return None
    quoted = ", ".join(f"'{_escape_filter_string(name)}'" for name in sorted(table_names))
    return f"table_name in ({quoted})"


class AskZvecClient:
    """问数 Zvec collection 操作（进程内持久化）。"""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._data_dir = settings.zvec_data_path
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._open_handles: dict[str, Any] = {}

    @property
    def index_prefix(self) -> str:
        return self._settings.zvec_index_prefix

    def collection_path(self, suffix: str) -> Path:
        return self._data_dir / f"{self.index_prefix}{suffix}"

    def index_name(self, suffix: str) -> str:
        return f"{self.index_prefix}{suffix}"

    def _suffix_from_index(self, index: str) -> str:
        prefix = self.index_prefix
        if index.startswith(prefix):
            return index[len(prefix) :]
        return index

    async def close(self) -> None:
        self._open_handles.clear()

    async def ping(self) -> bool:
        try:
            await self._run(self._data_dir.mkdir, parents=True, exist_ok=True)
            return True
        except Exception:
            return False

    async def recreate_vector_index(self, suffix: str, dims: int) -> str:
        name = self.index_name(suffix)
        await self._run(self._recreate_collection, suffix, dims)
        return name

    async def recreate_value_index(self, suffix: str) -> str:
        name = self.index_name(suffix)
        await self._run(self._recreate_collection, suffix, 0)
        return name

    async def bulk_index(self, index: str, docs: list[dict]) -> int:
        if not docs:
            return 0
        suffix = self._suffix_from_index(index)
        return await self._run(self._bulk_index_sync, suffix, docs)

    async def search_vector(
        self,
        suffix: str,
        query_vector: list[float],
        *,
        top_k: int,
        query_text: str | None = None,
        filter_expr: str | None = None,
    ) -> list[dict]:
        return await self._run(
            self._search_vector_sync,
            suffix,
            query_vector,
            top_k,
            query_text,
            filter_expr,
        )

    async def search_fulltext(
        self,
        suffix: str,
        query_text: str,
        *,
        top_k: int,
    ) -> list[dict]:
        return await self._run(self._search_fulltext_sync, suffix, query_text, top_k)

    async def _run(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    def _recreate_collection(self, suffix: str, dims: int) -> None:
        path = self.collection_path(suffix)
        self._open_handles.pop(suffix, None)
        if path.exists():
            try:
                col = zvec.open(str(path))
                col.destroy()
            except Exception:
                pass
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)

        schema = _schema_for_suffix(suffix, dims or self._settings.embedding_dims)
        collection = zvec.create_and_open(path=str(path), schema=schema)
        self._open_handles[suffix] = collection

    def _get_collection(self, suffix: str):
        if suffix in self._open_handles:
            return self._open_handles[suffix]
        path = self.collection_path(suffix)
        if not path.exists():
            return None
        collection = zvec.open(str(path))
        self._open_handles[suffix] = collection
        return collection

    def _doc_id(self, suffix: str, doc: dict) -> str:
        id_field = _ID_FIELDS.get(suffix)
        if id_field and id_field in doc:
            return f"{suffix}_{doc[id_field]}"
        raw = doc.get("search_text") or suffix
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", str(raw))[:48]
        return f"{suffix}_{slug}"

    def _to_zvec_doc(self, suffix: str, doc: dict) -> zvec.Doc:
        payload = dict(doc)
        embedding = payload.pop("embedding", None)
        fields: dict[str, Any] = {}
        for key, value in payload.items():
            if value is None:
                continue
            if isinstance(value, (int, float, str, bool)):
                fields[key] = value
            else:
                fields[key] = str(value)
        vectors: dict[str, list[float]] = {}
        if embedding is not None:
            vectors["embedding"] = [float(v) for v in embedding]
        return zvec.Doc(id=self._doc_id(suffix, doc), fields=fields, vectors=vectors)

    @staticmethod
    def _insert_ok(status: Any) -> bool:
        if getattr(status, "ok", False):
            return True
        code_attr = getattr(status, "code", None)
        if callable(code_attr):
            try:
                return int(code_attr()) == 0
            except Exception:
                return False
        return int(code_attr or 1) == 0

    def _bulk_index_sync(self, suffix: str, docs: list[dict]) -> int:
        collection = self._get_collection(suffix)
        if collection is None:
            return 0
        zvec_docs = [self._to_zvec_doc(suffix, doc) for doc in docs]
        statuses = collection.insert(zvec_docs)
        if not isinstance(statuses, list):
            statuses = [statuses]
        success = sum(1 for status in statuses if self._insert_ok(status))
        collection.optimize()
        return success

    def _hits_to_dicts(self, hits: list[Any]) -> list[dict]:
        results: list[dict] = []
        for hit in hits or []:
            row = dict(getattr(hit, "fields", None) or {})
            row["_score"] = float(getattr(hit, "score", 0.0) or 0.0)
            results.append(row)
        return results

    def _search_vector_sync(
        self,
        suffix: str,
        query_vector: list[float],
        top_k: int,
        query_text: str | None,
        filter_expr: str | None,
    ) -> list[dict]:
        collection = self._get_collection(suffix)
        if collection is None:
            return []

        use_hybrid = (
            self._settings.recall_hybrid_rerank
            and query_text
            and query_text.strip()
        )
        fetch_k = top_k
        if use_hybrid:
            mult = max(1, self._settings.recall_rerank_fetch_multiplier)
            fetch_k = max(top_k * mult, top_k)

        if use_hybrid:
            hits = collection.query(
                topk=fetch_k,
                queries=[
                    Query(field_name="embedding", vector=query_vector),
                    Query(
                        field_name="search_text",
                        fts=Fts(match_string=query_text.strip()),
                    ),
                ],
                filter=filter_expr,
                reranker=zvec.RrfReRanker(
                    rank_constant=self._settings.recall_rrf_rank_constant,
                ),
            )
            hits = (hits or [])[:top_k]
        else:
            hits = collection.query(
                queries=Query(field_name="embedding", vector=query_vector),
                topk=top_k,
                filter=filter_expr,
            )
        return self._hits_to_dicts(hits)

    def _search_fulltext_sync(self, suffix: str, query_text: str, top_k: int) -> list[dict]:
        collection = self._get_collection(suffix)
        if collection is None or not query_text.strip():
            return []
        hits = collection.query(
            queries=Query(
                field_name="search_text",
                fts=Fts(match_string=query_text.strip()),
            ),
            topk=top_k,
        )
        return self._hits_to_dicts(hits)
