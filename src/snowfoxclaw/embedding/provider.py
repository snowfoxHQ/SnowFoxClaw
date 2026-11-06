"""EmbeddingProvider 协议与维度契约（architecture.md 8.5）。

业务代码只依赖这个协议，不直连任何模型。维度不一致必须启动期失败，
因为 dim 已经写进库表结构，降级成「先跑起来」只会把错误推到检索阶段才发作。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class EmbeddingDimensionError(ValueError):
    """provider 声明的维度与配置或实际输出不一致。"""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """文本向量化抽象。"""

    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def assert_dim(provider: EmbeddingProvider, expected: int, *, sample: str = "维度自检") -> None:
    """启动期校验：声明维度与实际输出都必须等于配置维度。"""
    if expected < 1:
        raise EmbeddingDimensionError(f"配置维度非法：{expected}")

    declared = getattr(provider, "dim", None)
    if declared != expected:
        raise EmbeddingDimensionError(
            f"embedding 维度不一致：provider 声明 {declared}，配置要求 {expected}"
        )

    vectors = provider.embed([sample])
    if len(vectors) != 1:
        raise EmbeddingDimensionError(f"embed 返回条数 {len(vectors)} 与输入 1 不符")

    produced = len(vectors[0])
    if produced != expected:
        raise EmbeddingDimensionError(
            f"embedding 维度不一致：实际输出 {produced}，配置要求 {expected}"
        )
