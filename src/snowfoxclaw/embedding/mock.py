"""测试与 CI 用的确定性向量实现。

用 sha256 派生种子而不是内置 hash()：后者带进程级盐，同一段文本换个进程就变值，
测试会因为「顺序无关」的排序断言而随机失败。
"""

from __future__ import annotations

import hashlib
import math
import random


class MockEmbedding:
    """按文本内容确定生成的伪向量，同文本恒等，可复现召回排序。"""

    def __init__(self, dim: int = 512) -> None:
        if dim < 1:
            raise ValueError("dim 必须是正整数")
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        raw = [rng.uniform(-1.0, 1.0) for _ in range(self.dim)]
        norm = math.sqrt(sum(value * value for value in raw)) or 1.0
        return [value / norm for value in raw]
