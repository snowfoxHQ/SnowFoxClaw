"""meta 表：库级键值。

只存两种东西：``schema_version``（由 db.migrate 写入）与随库走的少量状态，
例如 ``persona.active_version``。不拿它当缓存用。
"""

from __future__ import annotations

from snowfoxclaw.storage.db import Database


class MetaRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    def get(self, key: str, default: str | None = None) -> str | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else default

    def set(self, key: str, value: str) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def delete(self, key: str) -> bool:
        with self._db.connect() as conn:
            cursor = conn.execute("DELETE FROM meta WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def all(self) -> dict[str, str]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT key, value FROM meta ORDER BY key").fetchall()
        return {row["key"]: row["value"] for row in rows}
