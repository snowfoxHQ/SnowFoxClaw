"""迁移注册表。

版本号单调递增，每个版本一个模块；``MIGRATIONS`` 的顺序即执行顺序。
``SCHEMA_VERSION`` 必须等于最后一个版本的 ``VERSION``，由 ``tests/test_storage.py``
校验——漏注册一个迁移，线上库就会永远缺表。

文件名带 ``m`` 前缀是 Python 的硬限制：模块名必须是合法标识符，``0001_initial`` 不能 import。
"""

from __future__ import annotations

from dataclasses import dataclass

from snowfoxclaw.storage.migrations import m0001_initial


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=m0001_initial.VERSION,
        name=m0001_initial.NAME,
        statements=m0001_initial.STATEMENTS,
    ),
)

SCHEMA_VERSION = MIGRATIONS[-1].version

__all__ = ["MIGRATIONS", "SCHEMA_VERSION", "Migration"]
