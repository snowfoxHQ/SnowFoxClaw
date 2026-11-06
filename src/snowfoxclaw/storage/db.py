"""SQLite 连接、迁移执行与时间/ID 工具。

两条硬约定：

- 连接一律开 WAL 与 ``foreign_keys``，避免单写多读互斥和悬空引用。
- 迁移在单个事务里逐条执行，全部成功后才写 ``meta.schema_version``。中途失败整批回滚，
  不会留下「表建了一半、版本号已升」的半成品库——这种库下次启动会被当成已迁移，最难排查。
"""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from snowfoxclaw.storage.migrations import MIGRATIONS, SCHEMA_VERSION

SCHEMA_VERSION_KEY = "schema_version"


class StorageError(RuntimeError):
    """库版本或结构与程序预期不符。"""


def utc_now() -> str:
    """统一 UTC、带 ``Z`` 后缀，与 fields.md 0 节的时间约定一致。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    """``前缀_`` + 6 位小写十六进制，例如 ``mem_a3f19c``。"""
    return f"{prefix}_{secrets.token_hex(3)}"


class Database:
    """数据库句柄。短连接：每次操作借一个连接，事务结束即归还。"""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def schema_version(conn: sqlite3.Connection) -> int:
    """当前库版本；``meta`` 表还不存在时视为 0。"""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
    ).fetchone()
    if exists is None:
        return 0
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (SCHEMA_VERSION_KEY,)).fetchone()
    return int(row["value"]) if row is not None else 0


def migrate(database: Database) -> int:
    """把库升级到 ``SCHEMA_VERSION``，返回升级后的版本。可重复执行。"""
    with database.connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        current = schema_version(conn)
        if current > SCHEMA_VERSION:
            # 老程序打开新库会静默读到缺列的表，必须在入口拦住
            raise StorageError(
                f"库版本 {current} 高于程序支持的 {SCHEMA_VERSION}，请升级 snowfoxclaw"
            )
        for migration in MIGRATIONS:
            if migration.version <= current:
                continue
            for statement in migration.statements:
                conn.execute(statement)
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (SCHEMA_VERSION_KEY, str(migration.version)),
            )
        return schema_version(conn)


def open_database(path: Path | str) -> Database:
    """建库并迁移到最新版本，给服务启动与测试共用。"""
    database = Database(path)
    migrate(database)
    return database
