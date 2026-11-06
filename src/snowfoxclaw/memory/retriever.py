"""MemoryRetriever 协议与内存参考实现（architecture.md 6.3）。

协议在 M0 冻结：上层只依赖这三个方法，W2 的 LocalIndex 与可选 VecRecallAdapter
各自实现，替换后端不改调用点。adapter 只做「存、删、查」，人格、偏好、工作上下文的
语义一律不进来。

high 敏感记忆的默认不召回规则也落在这一层，因为它必须对所有后端生效：删除
`filters["sensitivity"] == "high"` 就召回不到，显式要求时最多 1 条。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from snowfoxclaw.embedding.provider import EmbeddingDimensionError, EmbeddingProvider

HIGH_SENSITIVITY_QUOTA = 1


@dataclass
class MemoryItem:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None


@dataclass(frozen=True)
class RetrievedItem:
    id: str
    text: str
    score: float
    metadata: dict[str, Any]


@runtime_checkable
class MemoryRetriever(Protocol):
    def upsert(self, item: MemoryItem) -> str: ...

    def delete(self, ids: list[str]) -> None: ...

    def search(
        self, query: str, top_k: int, filters: dict | None = None
    ) -> list[RetrievedItem]: ...


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


class InMemoryIndex:
    """协议参考实现：证明契约可满足，同时充当单测后端。

    生产路径是 SQLite + 本地向量的 LocalIndex（W2），这里不做持久化。
    """

    def __init__(
        self, provider: EmbeddingProvider, high_sensitivity_quota: int = HIGH_SENSITIVITY_QUOTA
    ) -> None:
        if high_sensitivity_quota < 0:
            raise ValueError("high_sensitivity_quota 不能为负")
        self._provider = provider
        self._quota = high_sensitivity_quota
        self._items: dict[str, MemoryItem] = {}

    def __len__(self) -> int:
        return len(self._items)

    def upsert(self, item: MemoryItem) -> str:
        embedding = item.embedding
        if embedding is None:
            embedding = self._provider.embed([item.text])[0]
        if len(embedding) != self._provider.dim:
            raise EmbeddingDimensionError(
                f"{item.id} 的向量维度 {len(embedding)} 与 provider.dim {self._provider.dim} 不一致"
            )
        # 复制一份，避免调用方之后改原对象把索引里的数据带坏
        self._items[item.id] = MemoryItem(
            id=item.id,
            text=item.text,
            metadata=dict(item.metadata),
            embedding=list(embedding),
        )
        return item.id

    def delete(self, ids: list[str]) -> None:
        for item_id in ids:
            self._items.pop(item_id, None)

    def search(self, query: str, top_k: int, filters: dict | None = None) -> list[RetrievedItem]:
        if top_k <= 0 or not self._items:
            return []

        effective = dict(filters or {})
        wants_high = effective.get("sensitivity") == "high"
        candidates = [
            item for item in self._items.values() if self._matches(item, effective, wants_high)
        ]
        if not candidates:
            return []

        query_vector = self._provider.embed([query])[0]
        scored = [(_cosine(query_vector, item.embedding or []), item) for item in candidates]
        # 同分按 id 升序，保证不同进程、不同插入顺序下结果一致
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))

        limited = scored[: self._quota] if wants_high else scored
        return [
            RetrievedItem(id=item.id, text=item.text, score=score, metadata=dict(item.metadata))
            for score, item in limited[:top_k]
        ]

    @staticmethod
    def _matches(item: MemoryItem, filters: dict, wants_high: bool) -> bool:
        if item.metadata.get("sensitivity") == "high" and not wants_high:
            return False
        return all(item.metadata.get(key) == value for key, value in filters.items())
