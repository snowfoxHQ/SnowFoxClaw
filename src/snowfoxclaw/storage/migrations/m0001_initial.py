"""0001：初始表结构。

与 ``schema/fields.md`` 的 5 张核心表一一对应。已发布的迁移不允许回头修改，
需要变更就新增 0002；否则老库升不上来，迁移就失去意义。

数组/对象字段统一落 JSON TEXT 列（``*_json``），不拆关联表——第一阶段只按主键
或 session 读，拆表只会多一层 join。
"""

from __future__ import annotations

VERSION = 1
NAME = "initial"

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS persona_profile (
        id                  TEXT    NOT NULL,
        version             INTEGER NOT NULL CHECK (version >= 1),
        display_name        TEXT    NOT NULL CHECK (length(display_name) BETWEEN 1 AND 32),
        tone                TEXT    NOT NULL CHECK (length(tone) BETWEEN 1 AND 200),
        verbosity           TEXT    NOT NULL DEFAULT 'medium'
                                    CHECK (verbosity IN ('short', 'medium', 'long')),
        language            TEXT    NOT NULL DEFAULT 'zh-CN',
        values_json         TEXT    NOT NULL DEFAULT '[]',
        boundaries_json     TEXT    NOT NULL DEFAULT '[]',
        taboos_json         TEXT    NOT NULL DEFAULT '[]',
        response_style_json TEXT    NOT NULL DEFAULT '{}',
        created_at          TEXT    NOT NULL,
        updated_at          TEXT    NOT NULL,
        source              TEXT    NOT NULL
                                    CHECK (source IN ('user_confirmed', 'imported', 'default')),
        PRIMARY KEY (id, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS preference_item (
        id                     TEXT  PRIMARY KEY,
        domain                 TEXT  NOT NULL
                                     CHECK (domain IN (
                                         'schedule', 'communication', 'writing', 'general'
                                     )),
        "key"                  TEXT  NOT NULL
                                     CHECK (length("key") BETWEEN 1 AND 64 AND "key" = trim("key")),
        value                  TEXT  NOT NULL CHECK (length(value) BETWEEN 1 AND 500),
        value_type             TEXT  NOT NULL DEFAULT 'text'
                                     CHECK (value_type IN ('text', 'number', 'time', 'bool')),
        confidence             REAL  NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
        sensitivity            TEXT  NOT NULL
                                     CHECK (sensitivity IN ('low', 'medium', 'high')),
        source                 TEXT  NOT NULL
                                     CHECK (source IN ('user_explicit', 'inferred')),
        created_at             TEXT  NOT NULL,
        last_used_at           TEXT,
        superseded_values_json TEXT  NOT NULL DEFAULT '[]',
        UNIQUE (domain, "key")
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS episodic_memory (
        id             TEXT    PRIMARY KEY,
        session_id     TEXT    NOT NULL,
        ts             TEXT    NOT NULL,
        type           TEXT    NOT NULL
                               CHECK (type IN ('event', 'fact', 'preference_evidence', 'task')),
        summary        TEXT    NOT NULL CHECK (length(summary) BETWEEN 1 AND 500),
        entities_json  TEXT    NOT NULL DEFAULT '[]',
        raw_ref        TEXT,
        embedding_ref  TEXT,
        importance     REAL    NOT NULL DEFAULT 0.5 CHECK (importance BETWEEN 0.0 AND 1.0),
        confidence     REAL    NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
        sensitivity    TEXT    NOT NULL CHECK (sensitivity IN ('low', 'medium', 'high')),
        consent_json   TEXT,
        expires_at     TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_episodic_session_ts
        ON episodic_memory (session_id, ts)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_episodic_importance
        ON episodic_memory (importance DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_episodic_expires_at
        ON episodic_memory (expires_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_episodic_embedding_ref
        ON episodic_memory (embedding_ref)
    """,
    """
    CREATE TABLE IF NOT EXISTS working_context (
        session_id           TEXT PRIMARY KEY,
        task_goal            TEXT CHECK (task_goal IS NULL OR length(task_goal) <= 300),
        active_entities_json TEXT NOT NULL DEFAULT '[]',
        open_questions_json  TEXT NOT NULL DEFAULT '[]',
        recent_turns_json    TEXT NOT NULL DEFAULT '[]',
        ttl                  TEXT NOT NULL DEFAULT '2h',
        updated_at           TEXT NOT NULL,
        expires_at           TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_working_context_expires_at
        ON working_context (expires_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_turn (
        id                TEXT    PRIMARY KEY,
        session_id        TEXT    NOT NULL,
        ts                TEXT    NOT NULL,
        role              TEXT    NOT NULL CHECK (role IN ('user', 'assistant')),
        content           TEXT    NOT NULL CHECK (length(content) <= 32768),
        persona_version   INTEGER NOT NULL CHECK (persona_version >= 1),
        used_context_json TEXT,
        tokens_json       TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_turn_session_ts
        ON conversation_turn (session_id, ts)
    """,
)
