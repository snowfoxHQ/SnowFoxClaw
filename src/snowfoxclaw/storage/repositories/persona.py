"""PersonaProfile 仓库：只追加版本，不回改历史行。

回滚 = 复制旧版本内容写一行 ``version + 1``（fields.md 第 1 节）。因此这里**没有 update**：
一旦提供「修改第 N 版」，used_context 回读就会指向一段被篡改的历史。
"""

from __future__ import annotations

from typing import Any

from snowfoxclaw.storage.db import Database, StorageError, utc_now
from snowfoxclaw.storage.repositories._common import decode_row, dumps
from snowfoxclaw.storage.repositories.meta import MetaRepository

ACTIVE_VERSION_KEY = "persona.active_version"
PROFILE_ID = "persona_default"
_VERBOSITIES = frozenset({"short", "medium", "long"})
_SOURCES = frozenset({"user_confirmed", "imported", "default"})
_JSON_DEFAULTS: dict[str, Any] = {
    "values_json": [],
    "boundaries_json": [],
    "taboos_json": [],
    "response_style_json": {},
}


class PersonaRepository:
    def __init__(self, database: Database) -> None:
        self._db = database
        self._meta = MetaRepository(database)

    def create(
        self,
        *,
        display_name: str,
        tone: str,
        verbosity: str = "medium",
        language: str = "zh-CN",
        values: list[str] | None = None,
        boundaries: list[str] | None = None,
        taboos: list[str] | None = None,
        response_style: dict[str, Any] | None = None,
        source: str = "user_confirmed",
        version: int | None = None,
        profile_id: str = PROFILE_ID,
        now: str | None = None,
    ) -> dict[str, Any]:
        if verbosity not in _VERBOSITIES:
            raise ValueError(f"verbosity 不支持 {verbosity!r}")
        if source not in _SOURCES:
            raise ValueError(f"source 不支持 {source!r}")
        stamp = now or utc_now()

        with self._db.connect() as conn:
            if version is None:
                # 取号与插入同一连接，避免两个请求同时拿到同一个最大值
                row = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 AS next"
                    " FROM persona_profile WHERE id = ?",
                    (profile_id,),
                ).fetchone()
                version = int(row["next"])
            conn.execute(
                "INSERT INTO persona_profile (id, version, display_name, tone, verbosity, language,"
                " values_json, boundaries_json, taboos_json, response_style_json,"
                " created_at, updated_at, source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    profile_id,
                    version,
                    display_name,
                    tone,
                    verbosity,
                    language,
                    dumps(list(values or [])),
                    dumps(list(boundaries or [])),
                    dumps(list(taboos or [])),
                    dumps(dict(response_style or {})),
                    stamp,
                    stamp,
                    source,
                ),
            )

        record = self.get(version, profile_id)
        if record is None:  # pragma: no cover - 插入成功却查不到说明连接或事务有问题
            raise StorageError(f"persona {profile_id} v{version} 写入后读取失败")
        return record

    def get(self, version: int, profile_id: str = PROFILE_ID) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM persona_profile WHERE id = ? AND version = ?",
                (profile_id, version),
            ).fetchone()
        return None if row is None else decode_row(row, _JSON_DEFAULTS)

    def latest_version(self, profile_id: str = PROFILE_ID) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS latest FROM persona_profile WHERE id = ?",
                (profile_id,),
            ).fetchone()
        return int(row["latest"])

    def list_versions(self, profile_id: str = PROFILE_ID) -> list[int]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT version FROM persona_profile WHERE id = ? ORDER BY version",
                (profile_id,),
            ).fetchall()
        return [int(row["version"]) for row in rows]

    def active_version(self) -> int | None:
        raw = self._meta.get(ACTIVE_VERSION_KEY)
        return None if raw is None else int(raw)

    def set_active_version(self, version: int, profile_id: str = PROFILE_ID) -> None:
        record = self.get(version, profile_id)
        if record is None:
            raise StorageError(f"persona {profile_id} 没有版本 {version}")
        if record["source"] != "user_confirmed":
            # fields.md 1 节：非 user_confirmed 不激活。放在仓库层，服务层就绕不过去
            raise StorageError(f"persona v{version} 的 source={record['source']}，不能激活")
        self._meta.set(ACTIVE_VERSION_KEY, str(version))

    def count(self, profile_id: str = PROFILE_ID) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM persona_profile WHERE id = ?", (profile_id,)
            ).fetchone()
        return int(row["n"])
