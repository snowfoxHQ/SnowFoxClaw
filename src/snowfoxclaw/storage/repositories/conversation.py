"""会话侧仓库：ConversationTurn 与 WorkingContext。

``expires_at`` 一律由 ``updated_at + ttl`` 派生后落库。只存 ttl 的话清理任务要逐行解析
duration；只存 expires_at 则丢掉「这个上下文为什么活 2 小时」。两者都存（fields.md 第 4 节）。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from snowfoxclaw.storage.db import Database, new_id, utc_now
from snowfoxclaw.storage.repositories._common import check_fields, decode_row, dumps

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_DURATION_RE = re.compile(r"^([1-9]\d*)([smhd])$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
MAX_RECENT_TURNS = 20
MAX_ACTIVE_ENTITIES = 20
MAX_OPEN_QUESTIONS = 10
_ROLES = frozenset({"user", "assistant"})


def parse_duration(text: str) -> timedelta:
    match = _DURATION_RE.match(text)
    if match is None:
        raise ValueError(f"ttl 形式非法：{text!r}，应为 30m / 2h / 1d")
    return timedelta(seconds=int(match.group(1)) * _UNIT_SECONDS[match.group(2)])


def expires_at_for(updated_at: str, ttl: str) -> str:
    try:
        base = datetime.strptime(updated_at, _ISO_FORMAT)
    except ValueError as exc:
        raise ValueError(f"时间必须是 {_ISO_FORMAT} 格式：{updated_at!r}") from exc
    return (base + parse_duration(ttl)).strftime(_ISO_FORMAT)


_TURN_UPDATE_FIELDS = frozenset({"used_context", "tokens"})
_TURN_JSON: dict[str, Any] = {"used_context_json": None, "tokens_json": None}


class TurnRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    def append(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        persona_version: int,
        used_context: dict[str, Any] | None = None,
        tokens: dict[str, Any] | None = None,
        turn_id: str | None = None,
        ts: str | None = None,
    ) -> dict[str, Any]:
        if role not in _ROLES:
            raise ValueError(f"role 不支持 {role!r}")
        if role == "user" and used_context is not None:
            # fields.md 第 5 节：user 轮的 used_context 必须为 null
            raise ValueError("user 轮的 used_context 必须为 null")

        identifier = turn_id or new_id("turn")
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO conversation_turn (id, session_id, ts, role, content, persona_version,"
                " used_context_json, tokens_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    session_id,
                    ts or utc_now(),
                    role,
                    content,
                    persona_version,
                    None if used_context is None else dumps(used_context),
                    None if tokens is None else dumps(tokens),
                ),
            )
        record = self.get(identifier)
        if record is None:  # pragma: no cover
            raise RuntimeError(f"turn {identifier} 写入后读取失败")
        return record

    def get(self, turn_id: str) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversation_turn WHERE id = ?", (turn_id,)
            ).fetchone()
        return None if row is None else decode_row(row, _TURN_JSON)

    def list_by_session(
        self, session_id: str, limit: int = 20, before_ts: str | None = None
    ) -> list[dict[str, Any]]:
        """取最近 ``limit`` 轮，按时间升序返回——组装上下文时直接可用。"""
        sql = "SELECT * FROM conversation_turn WHERE session_id = ?"
        params: list[Any] = [session_id]
        if before_ts is not None:
            sql += " AND ts < ?"
            params.append(before_ts)
        sql += " ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)

        with self._db.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [decode_row(row, _TURN_JSON) for row in reversed(rows)]

    def update(self, turn_id: str, **fields: Any) -> dict[str, Any] | None:
        """只允许补写 used_context / tokens；正文与角色是历史事实，不给改。"""
        check_fields(fields, _TURN_UPDATE_FIELDS, f"turn.update({turn_id})")
        if not fields:
            return self.get(turn_id)

        assignments: list[str] = []
        params: list[Any] = []
        for name, value in fields.items():
            assignments.append(f"{name}_json = ?")
            params.append(None if value is None else dumps(value))
        params.append(turn_id)

        with self._db.connect() as conn:
            cursor = conn.execute(
                f"UPDATE conversation_turn SET {', '.join(assignments)} WHERE id = ?", tuple(params)
            )
            updated = cursor.rowcount > 0
        return self.get(turn_id) if updated else None

    def delete(self, turn_id: str) -> bool:
        """删 turn 时把引用它的记忆 ``raw_ref`` 置空，不级联删除记忆（fields.md 第 3 节）。"""
        with self._db.connect() as conn:
            conn.execute("UPDATE episodic_memory SET raw_ref = NULL WHERE raw_ref = ?", (turn_id,))
            cursor = conn.execute("DELETE FROM conversation_turn WHERE id = ?", (turn_id,))
            return cursor.rowcount > 0

    def count(self) -> int:
        with self._db.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM conversation_turn").fetchone()
        return int(row["n"])


_CONTEXT_JSON: dict[str, Any] = {
    "active_entities_json": [],
    "open_questions_json": [],
    "recent_turns_json": [],
}


class WorkingContextRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    def upsert(
        self,
        *,
        session_id: str,
        task_goal: str | None = None,
        active_entities: list[str] | None = None,
        open_questions: list[str] | None = None,
        recent_turns: list[str] | None = None,
        ttl: str = "2h",
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        stamp = updated_at or utc_now()
        expires = expires_at_for(stamp, ttl)

        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO working_context (session_id, task_goal, active_entities_json,"
                " open_questions_json, recent_turns_json, ttl, updated_at, expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(session_id) DO UPDATE SET"
                " task_goal = excluded.task_goal,"
                " active_entities_json = excluded.active_entities_json,"
                " open_questions_json = excluded.open_questions_json,"
                " recent_turns_json = excluded.recent_turns_json,"
                " ttl = excluded.ttl, updated_at = excluded.updated_at,"
                " expires_at = excluded.expires_at",
                (
                    session_id,
                    task_goal,
                    dumps(list(active_entities or [])[:MAX_ACTIVE_ENTITIES]),
                    dumps(list(open_questions or [])[:MAX_OPEN_QUESTIONS]),
                    # FIFO：保留最近 20 条，丢最旧的
                    dumps(list(recent_turns or [])[-MAX_RECENT_TURNS:]),
                    ttl,
                    stamp,
                    expires,
                ),
            )
        record = self.get(session_id)
        if record is None:  # pragma: no cover
            raise RuntimeError(f"working_context {session_id} 写入后读取失败")
        return record

    def push_turn(self, session_id: str, turn_id: str, *, ttl: str = "2h") -> dict[str, Any]:
        """只追加一轮引用，其余字段沿用当前值。"""
        current = self.get(session_id)
        recent = list(current["recent_turns"]) if current is not None else []
        recent.append(turn_id)
        return self.upsert(
            session_id=session_id,
            task_goal=None if current is None else current["task_goal"],
            active_entities=[] if current is None else current["active_entities"],
            open_questions=[] if current is None else current["open_questions"],
            recent_turns=recent,
            ttl=ttl,
        )

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM working_context WHERE session_id = ?", (session_id,)
            ).fetchone()
        return None if row is None else decode_row(row, _CONTEXT_JSON)

    def delete(self, session_id: str) -> bool:
        with self._db.connect() as conn:
            cursor = conn.execute("DELETE FROM working_context WHERE session_id = ?", (session_id,))
            return cursor.rowcount > 0

    def purge_expired(self, now: str | None = None) -> int:
        with self._db.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM working_context WHERE expires_at <= ?", (now or utc_now(),)
            )
            return cursor.rowcount

    def count(self) -> int:
        with self._db.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM working_context").fetchone()
        return int(row["n"])
