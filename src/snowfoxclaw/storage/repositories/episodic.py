"""EpisodicMemory 仓库。

两条来自 fields.md 第 3 节的硬规则，放在仓库层而不是服务层：

- ``sensitivity = high`` 必须带 ``consent``，没有确认留痕就不许写。
- 过期（``expires_at`` 已过）只是检索时跳过，**不物理删除**——删了就无法回答「当时记住了什么」。
"""

from __future__ import annotations

from typing import Any

from snowfoxclaw.storage.db import Database, new_id, utc_now
from snowfoxclaw.storage.repositories._common import check_fields, decode_row, dumps

_UPDATE_FIELDS = frozenset(
    {
        "summary",
        "entities",
        "importance",
        "confidence",
        "sensitivity",
        "consent",
        "expires_at",
        "embedding_ref",
        "raw_ref",
    }
)
_JSON_DEFAULTS: dict[str, Any] = {"entities_json": [], "consent_json": None}
_COLUMNS = {
    "summary": "summary",
    "importance": "importance",
    "confidence": "confidence",
    "sensitivity": "sensitivity",
    "expires_at": "expires_at",
    "embedding_ref": "embedding_ref",
    "raw_ref": "raw_ref",
}


def _require_consent(sensitivity: str, consent: dict[str, Any] | None) -> None:
    if sensitivity == "high" and consent is None:
        raise ValueError("sensitivity=high 的记忆必须带 consent 确认留痕")


class EpisodicRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    def create(
        self,
        *,
        session_id: str,
        summary: str,
        memory_type: str = "fact",
        entities: list[str] | None = None,
        importance: float = 0.5,
        confidence: float = 1.0,
        sensitivity: str = "low",
        consent: dict[str, Any] | None = None,
        expires_at: str | None = None,
        raw_ref: str | None = None,
        embedding_ref: str | None = None,
        memory_id: str | None = None,
        ts: str | None = None,
    ) -> dict[str, Any]:
        _require_consent(sensitivity, consent)
        identifier = memory_id or new_id("mem")

        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO episodic_memory (id, session_id, ts, type, summary, entities_json,"
                " raw_ref, embedding_ref, importance, confidence, sensitivity, consent_json,"
                " expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    session_id,
                    ts or utc_now(),
                    memory_type,
                    summary,
                    dumps(list(entities or [])),
                    raw_ref,
                    embedding_ref,
                    importance,
                    confidence,
                    sensitivity,
                    None if consent is None else dumps(consent),
                    expires_at,
                ),
            )
        record = self.get(identifier)
        if record is None:  # pragma: no cover
            raise RuntimeError(f"memory {identifier} 写入后读取失败")
        return record

    def get(self, memory_id: str) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM episodic_memory WHERE id = ?", (memory_id,)
            ).fetchone()
        return None if row is None else decode_row(row, _JSON_DEFAULTS)

    def update(self, memory_id: str, **fields: Any) -> dict[str, Any] | None:
        check_fields(fields, _UPDATE_FIELDS, f"episodic.update({memory_id})")
        if not fields:
            return self.get(memory_id)

        current = self.get(memory_id)
        if current is None:
            return None
        _require_consent(
            fields.get("sensitivity", current["sensitivity"]),
            fields.get("consent", current["consent"]),
        )

        assignments: list[str] = []
        params: list[Any] = []
        for name, value in fields.items():
            if name == "entities":
                assignments.append("entities_json = ?")
                params.append(dumps(list(value or [])))
            elif name == "consent":
                assignments.append("consent_json = ?")
                params.append(None if value is None else dumps(value))
            else:
                assignments.append(f"{_COLUMNS[name]} = ?")
                params.append(value)
        params.append(memory_id)

        with self._db.connect() as conn:
            conn.execute(
                f"UPDATE episodic_memory SET {', '.join(assignments)} WHERE id = ?", tuple(params)
            )
        return self.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        with self._db.connect() as conn:
            cursor = conn.execute("DELETE FROM episodic_memory WHERE id = ?", (memory_id,))
            return cursor.rowcount > 0

    def list_by_session(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM episodic_memory WHERE session_id = ? ORDER BY ts LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [decode_row(row, _JSON_DEFAULTS) for row in rows]

    def list_active(
        self, *, session_id: str | None = None, now: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        """检索候选：跳过已过期项，可按会话过滤。"""
        sql = "SELECT * FROM episodic_memory WHERE (expires_at IS NULL OR expires_at > ?)"
        params: list[Any] = [now or utc_now()]
        if session_id is not None:
            sql += " AND session_id = ?"
            params.append(session_id)
        sql += " ORDER BY ts LIMIT ?"
        params.append(limit)
        with self._db.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [decode_row(row, _JSON_DEFAULTS) for row in rows]

    def list_expired(self, now: str | None = None) -> list[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT id FROM episodic_memory WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (now or utc_now(),),
            ).fetchall()
        return [row["id"] for row in rows]

    def null_raw_ref(self, turn_id: str) -> int:
        """删 turn 时调用：把引用它的记忆 ``raw_ref`` 置空，记忆本身保留（已脱敏且独立成立）。"""
        with self._db.connect() as conn:
            cursor = conn.execute(
                "UPDATE episodic_memory SET raw_ref = NULL WHERE raw_ref = ?", (turn_id,)
            )
            return cursor.rowcount

    def count(self) -> int:
        with self._db.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM episodic_memory").fetchone()
        return int(row["n"])
