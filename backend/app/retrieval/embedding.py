"""
OpenAI 兼容 Embedding 客户端（本机多为 Ollama）。

连接优先来自管理台默认 embedding 模型，否则回退 env。
"""

from __future__ import annotations

import httpx

from app.system.runtime_config import resolve_embedding
from config.settings import Settings


class EmbeddingClient:
    """批量向量化文本。"""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._dims: int | None = None

    @property
    def dims(self) -> int | None:
        """首次 embed 后可知向量维度。"""
        return self._dims

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """调用 /v1/embeddings，返回与输入等长的向量列表。"""
        if not texts:
            return []

        cfg = resolve_embedding(self._settings)
        url = f"{cfg.api_base.rstrip('/')}/embeddings"
        headers = {"Authorization": f"Bearer {cfg.api_key or 'ollama'}"}
        payload = {
            "model": cfg.model,
            "input": texts,
        }
        timeout = httpx.Timeout(cfg.timeout_sec)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
        vectors: list[list[float]] = []
        for item in items:
            vec = item.get("embedding")
            if not isinstance(vec, list):
                raise ValueError("Embedding 响应缺少 embedding 字段")
            vectors.append([float(v) for v in vec])

        if vectors and self._dims is None:
            self._dims = len(vectors[0])
        return vectors
