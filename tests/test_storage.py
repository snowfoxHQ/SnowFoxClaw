"""W1-3：SQLite 存储层与迁移。

断言重点不在「能存能取」，而在库里那些不可绕过的约束：版本只追加、``(domain,key)`` 唯一、
``high`` 必须带 consent、过期不物理删除、删 turn 不级联删记忆。
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from snowfoxclaw.storage import (
    SCHEMA_VERSION,
    EpisodicRepository,
    PersonaRepository,
    PreferenceRepository,
    StorageError,
    TurnRepository,
    WorkingContextRepository,
    new_id,
    open_database,
    schema_version,
)
from snowfoxclaw.storage.db import Database, migrate
from snowfoxclaw.storage.migrations import MIGRATIONS
from snowfoxclaw.storage.repositories.conversation import parse_duration

NOW = "2026-11-07T10:00:00Z"


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    return open_database(tmp_path / "snowfoxclaw.db")


@pytest.fixture()
def personas(db: Database) -> PersonaRepository:
    return PersonaRepository(db)


@pytest.fixture()
def preferences(db: Database) -> PreferenceRepository:
    return PreferenceRepository(db)


@pytest.fixture()
def memories(db: Database) -> EpisodicRepository:
    return EpisodicRepository(db)


@pytest.fixture()
def turns(db: Database) -> TurnRepository:
    return TurnRepository(db)


# ---------- 迁移 ----------


def test_open_database_creates_all_tables(db: Database):
    with db.connect() as conn:
        names = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        version = schema_version(conn)

    assert version == SCHEMA_VERSION
    assert {
        "meta",
        "persona_profile",
        "preference_item",
        "episodic_memory",
        "working_context",
        "conversation_turn",
    } <= names


def test_migrate_is_idempotent(db: Database):
    assert migrate(db) == SCHEMA_VERSION
    assert migrate(db) == SCHEMA_VERSION


def test_newer_database_rejected(db: Database):
    """老程序打开新库必须失败，否则会静默读到缺列的表。"""
    with db.connect() as conn:
        conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", ("999",))

    with pytest.raises(StorageError, match="高于程序支持"):
        migrate(db)


def test_migration_registry_is_ordered():
    versions = [migration.version for migration in MIGRATIONS]
    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)
    assert SCHEMA_VERSION == versions[-1]


def test_new_id_shape():
    identifier = new_id("mem")
    assert re.fullmatch(r"mem_[0-9a-f]{6}", identifier)


# ---------- 人格 ----------


def test_persona_versions_append_only(personas: PersonaRepository):
    first = personas.create(display_name="小狐", tone="直接", now=NOW)
    second = personas.create(display_name="小狐", tone="更直接", now=NOW)

    assert (first["version"], second["version"]) == (1, 2)
    assert personas.latest_version() == 2
    assert personas.list_versions() == [1, 2]
    assert personas.get(1)["tone"] == "直接"


def test_persona_json_columns_roundtrip(personas: PersonaRepository):
    record = personas.create(
        display_name="小狐",
        tone="直接",
        values=["不说教"],
        taboos=["亲爱的"],
        response_style={"format": "先结论", "emoji": "none"},
        now=NOW,
    )
    assert record["values"] == ["不说教"]
    assert record["taboos"] == ["亲爱的"]
    assert record["response_style"] == {"format": "先结论", "emoji": "none"}
    assert record["boundaries"] == []
    assert record["source"] == "user_confirmed"


def test_persona_activation_requires_user_confirmed(personas: PersonaRepository):
    personas.create(display_name="小狐", tone="直接", source="default", now=NOW)
    with pytest.raises(StorageError, match="不能激活"):
        personas.set_active_version(1)

    personas.create(display_name="小狐", tone="直接", source="user_confirmed", now=NOW)
    personas.set_active_version(2)
    assert personas.active_version() == 2


def test_persona_activation_of_missing_version_rejected(personas: PersonaRepository):
    with pytest.raises(StorageError, match="没有版本"):
        personas.set_active_version(7)


def test_persona_invalid_verbosity_rejected(personas: PersonaRepository):
    with pytest.raises(ValueError, match="verbosity"):
        personas.create(display_name="小狐", tone="直接", verbosity="verbose")


def test_persona_display_name_length_enforced_by_db(personas: PersonaRepository):
    with pytest.raises(sqlite3.IntegrityError):
        personas.create(display_name="呼" * 33, tone="直接")


# ---------- 偏好 ----------


def test_preference_unique_domain_key(preferences: PreferenceRepository):
    preferences.create(domain="schedule", key="提醒时间", value="八点", confidence=1.0)
    with pytest.raises(sqlite3.IntegrityError):
        preferences.create(domain="schedule", key="提醒时间", value="九点", confidence=1.0)

    # 同 key 不同 domain 是两条
    other = preferences.create(domain="writing", key="提醒时间", value="九点", confidence=1.0)
    assert other["domain"] == "writing"


def test_preference_key_whitespace_rejected(preferences: PreferenceRepository):
    with pytest.raises(sqlite3.IntegrityError):
        preferences.create(domain="general", key=" 提醒时间 ", value="八点", confidence=1.0)


def test_preference_update_and_touch(preferences: PreferenceRepository):
    record = preferences.create(
        domain="schedule", key="提醒时间", value="八点", confidence=1.0, created_at=NOW
    )
    updated = preferences.update(record["id"], value="九点", superseded_values=[])
    assert updated is not None and updated["value"] == "九点"

    assert preferences.touch(record["id"], at="2026-11-07T11:00:00Z") is True
    assert preferences.get(record["id"])["last_used_at"] == "2026-11-07T11:00:00Z"


def test_preference_unknown_update_field_rejected(preferences: PreferenceRepository):
    record = preferences.create(domain="general", key="语气", value="简短", confidence=0.5)
    with pytest.raises(ValueError, match="不支持的字段"):
        preferences.update(record["id"], tone="温柔")


def test_preference_superseded_history_capped(preferences: PreferenceRepository):
    record = preferences.create(domain="general", key="语气", value="简短", confidence=0.5)
    history = [{"value": f"旧值{i}", "confidence": 0.5, "superseded_at": NOW} for i in range(6)]
    with pytest.raises(ValueError, match="最多 5 条"):
        preferences.update(record["id"], superseded_values=history)


def test_preference_delete(preferences: PreferenceRepository):
    record = preferences.create(domain="general", key="语气", value="简短", confidence=0.5)
    assert preferences.delete(record["id"]) is True
    assert preferences.get(record["id"]) is None
    assert preferences.delete(record["id"]) is False


# ---------- 记忆 ----------


def test_high_sensitivity_requires_consent(memories: EpisodicRepository):
    with pytest.raises(ValueError, match="consent"):
        memories.create(session_id="sess_abc123", summary="身份证在抽屉", sensitivity="high")

    record = memories.create(
        session_id="sess_abc123",
        summary="身份证在抽屉",
        sensitivity="high",
        consent={"confirmed_by": "user", "confirmed_at": NOW, "channel": "cli"},
    )
    assert record["consent"]["channel"] == "cli"


def test_high_sensitivity_upgrade_requires_consent(memories: EpisodicRepository):
    record = memories.create(session_id="sess_abc123", summary="住址在 A 区")
    with pytest.raises(ValueError, match="consent"):
        memories.update(record["id"], sensitivity="high")


def test_expired_memory_skipped_but_not_deleted(memories: EpisodicRepository):
    expired = memories.create(
        session_id="sess_abc123", summary="过期的会面", expires_at="2026-11-07T09:00:00Z"
    )
    alive = memories.create(session_id="sess_abc123", summary="仍在进行的会面")

    active_ids = {row["id"] for row in memories.list_active(now=NOW)}
    assert alive["id"] in active_ids
    assert expired["id"] not in active_ids
    assert memories.list_expired(now=NOW) == [expired["id"]]
    # 过期不等于删除：仍能按 id 取回
    assert memories.get(expired["id"]) is not None


def test_memory_list_by_session(memories: EpisodicRepository):
    memories.create(session_id="sess_aaa111", summary="A 会话的事")
    memories.create(session_id="sess_bbb222", summary="B 会话的事")

    rows = memories.list_by_session("sess_aaa111")
    assert [row["summary"] for row in rows] == ["A 会话的事"]


# ---------- 对话轮 ----------


def test_user_turn_cannot_carry_used_context(turns: TurnRepository):
    with pytest.raises(ValueError, match="used_context"):
        turns.append(
            session_id="sess_abc123",
            role="user",
            content="你好",
            persona_version=1,
            used_context={"persona_version": 1, "preferences_used": [], "memories_used": []},
        )


def test_assistant_turn_roundtrips_used_context(turns: TurnRepository):
    used = {
        "persona_version": 2,
        "preferences_used": ["pref_abc123"],
        "memories_used": [{"id": "mem_abc123", "sensitivity": "high"}],
    }
    record = turns.append(
        session_id="sess_abc123",
        role="assistant",
        content="我是小狐",
        persona_version=2,
        used_context=used,
        tokens={"prompt": 12, "completion": 8},
    )
    assert record["used_context"] == used
    assert record["tokens"] == {"prompt": 12, "completion": 8}
    # JSON 列名不外泄，上层只看到字段清单里的名字
    assert "used_context_json" not in record


def test_turn_history_returns_latest_in_order(turns: TurnRepository):
    for hour in range(5):
        turns.append(
            session_id="sess_abc123",
            role="user",
            content=f"第{hour}轮",
            persona_version=1,
            ts=f"2026-11-07T1{hour}:00:00Z",
        )

    latest = turns.list_by_session("sess_abc123", limit=2)
    assert [row["content"] for row in latest] == ["第3轮", "第4轮"]


def test_turn_update_only_allows_context_fields(turns: TurnRepository):
    record = turns.append(session_id="sess_abc123", role="user", content="你好", persona_version=1)
    with pytest.raises(ValueError, match="不支持的字段"):
        turns.update(record["id"], content="改过的正文")


def test_deleting_turn_nulls_memory_raw_ref(turns: TurnRepository, memories: EpisodicRepository):
    turn = turns.append(
        session_id="sess_abc123", role="user", content="我下周去成都", persona_version=1
    )
    memory = memories.create(session_id="sess_abc123", summary="用户下周去成都", raw_ref=turn["id"])

    assert turns.delete(turn["id"]) is True
    assert memories.get(memory["id"]) is not None
    assert memories.get(memory["id"])["raw_ref"] is None


# ---------- 工作上下文 ----------


def test_working_context_derives_expires_at(db: Database):
    contexts = WorkingContextRepository(db)
    record = contexts.upsert(session_id="sess_abc123", task_goal="写迁移", ttl="2h", updated_at=NOW)

    assert record["ttl"] == "2h"
    assert record["updated_at"] == NOW
    assert record["expires_at"] == "2026-11-07T12:00:00Z"


def test_working_context_recent_turns_fifo(db: Database):
    contexts = WorkingContextRepository(db)
    contexts.upsert(session_id="sess_abc123", recent_turns=[f"turn_{i:06d}" for i in range(25)])

    record = contexts.get("sess_abc123")
    assert len(record["recent_turns"]) == 20
    assert record["recent_turns"][0] == "turn_000005"


def test_working_context_push_turn_keeps_other_fields(db: Database):
    contexts = WorkingContextRepository(db)
    contexts.upsert(
        session_id="sess_abc123", task_goal="写迁移", active_entities=["SQLite"], updated_at=NOW
    )
    record = contexts.push_turn("sess_abc123", "turn_abc123", ttl="1h")

    assert record["task_goal"] == "写迁移"
    assert record["active_entities"] == ["SQLite"]
    assert record["recent_turns"] == ["turn_abc123"]
    assert record["ttl"] == "1h"


def test_working_context_purge_expired(db: Database):
    contexts = WorkingContextRepository(db)
    contexts.upsert(session_id="sess_old111", ttl="30m", updated_at="2026-11-07T08:00:00Z")
    contexts.upsert(session_id="sess_new222", ttl="2h", updated_at=NOW)

    assert contexts.purge_expired(now=NOW) == 1
    assert contexts.get("sess_old111") is None
    assert contexts.get("sess_new222") is not None


@pytest.mark.parametrize("bad", ["", "2", "0h", "2hours", "h2"])
def test_parse_duration_rejects_invalid(bad: str):
    with pytest.raises(ValueError, match="ttl"):
        parse_duration(bad)
