"""PreferenceItem 仓库：``(domain, key)`` 唯一。

冲突怎么合并（显式覆盖推断、推断只留候选）是 W1-2 的决策，这里只提供原语：
取、写、改、删，以及 ``superseded_values`` 的 5 条环形约束。
"""

from __future__ import annotations

from typing import Any

from snowfoxclaw.storage.db import Database, new_id, utc_now
from snowfoxclaw.storage.repositories._common import check_fields, decode_row, dumps

MAX_SUPERSEDED = 5
_UPDATE_FIELDS = frozenset(
    {"value", "value_type", "confidence", "sensitivity", "last_used_at", "superseded_values"}
)
_JSON_DEFAULTS: dict[str, Any] = {"superseded_values_json": []}
_COLUMNS = {
    "value": "value",
    "value_type": "value_type",
    "confidence": "confidence",
    "sensitivity": "sensitivity",
    "last_used_at": "last_used_at",
}


class PreferenceRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    def create(
        self,
        *,
        domain: str,
        key: str,
        value: str,
        confidence: float,
        value_type: str = "text",
        sensitivity: str = "low",
        source: str = "user_explicit",
        pref_id: str | None = None,
        created_at: str | None = None,
        superseded_values: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        identifier = pref_id or new_id("pref")
        stamp = created_at or utc_now()
        history = list(superseded_values or [])
        if len(history) > MAX_SUPERSEDED:
            raise ValueError(f"superseded_values 最多 {MAX_SUPERSEDED} 条，收到 {len(history)} 条")

        with self._db.connect() as conn:
            conn.execute(
                'INSERT INTO preference_item (id, domain, "key", value, value_type, confidence,'
                " sensitivity, source, created_at, last_used_at, superseded_values_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
                (
                    identifier,
                    domain,
                    key,
                    value,
                    value_type,
                    confidence,
                    sensitivity,
                    source,
                    stamp,
                    dumps(history),
                ),
            )
        record = self.get(identifier)
        if record is None:  # pragma: no cover
            raise RuntimeError(f"preference {identifier} 写入后读取失败")
        return record

    def get(self, pref_id: str) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM preference_item WHERE id = ?", (pref_id,)).fetchone()
        return None if row is None else decode_row(row, _JSON_DEFAULTS)

    def get_by_key(self, domain: str, key: str) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute(
                'SELECT * FROM preference_item WHERE domain = ? AND "key" = ?', (domain, key)
            ).fetchone()
        return None if row is None else decode_row(row, _JSON_DEFAULTS)

    def list(self, domain: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM preference_item"
        params: tuple[Any, ...] = ()
        if domain is not None:
            sql += " WHERE domain = ?"
            params = (domain,)
        sql += ' ORDER BY domain, "key"'
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [decode_row(row, _JSON_DEFAULTS) for row in rows]

    def update(self, pref_id: str, **fields: Any) -> dict[str, Any] | None:
        check_fields(fields, _UPDATE_FIELDS, f"preference.update({pref_id})")
        if not fields:
            return self.get(pref_id)

        assignments: list[str] = []
        params: list[Any] = []
        for name, value in fields.items():
            if name == "superseded_values":
                history = list(value or [])
                if len(history) > MAX_SUPERSEDED:
                    raise ValueError(
                        f"superseded_values 最多 {MAX_SUPERSEDED} 条，收到 {len(history)} 条"
                    )
                assignments.append("superseded_values_json = ?")
                params.append(dumps(history))
            else:
                assignments.append(f"{_COLUMNS[name]} = ?")
                params.append(value)
        params.append(pref_id)

        with self._db.connect() as conn:
            cursor = conn.execute(
                f"UPDATE preference_item SET {', '.join(assignments)} WHERE id = ?",
                tuple(params),
            )
            updated = cursor.rowcount > 0
        return self.get(pref_id) if updated else None

    def touch(self, pref_id: str, at: str | None = None) -> bool:
        """被组装进上下文时刷新 last_used_at，用于后续排序。"""
        with self._db.connect() as conn:
            cursor = conn.execute(
                "UPDATE preference_item SET last_used_at = ? WHERE id = ?",
                (at or utc_now(), pref_id),
            )
            return cursor.rowcount > 0

    def delete(self, pref_id: str) -> bool:
        with self._db.connect() as conn:
            cursor = conn.execute("DELETE FROM preference_item WHERE id = ?", (pref_id,))
            return cursor.rowcount > 0

    def count(self) -> int:
        with self._db.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM preference_item").fetchone()
        return int(row["n"])
