"""API 数据模型（M0-4 接口桩）。

字段与 ``schema/*.json`` 对齐，``tests/test_openapi.py`` 会拿两边的 required 集合比对，
避免文档、schema、模型三处各说一套。
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Verbosity(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class Sensitivity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PreferenceDomain(str, Enum):
    SCHEDULE = "schedule"
    COMMUNICATION = "communication"
    WRITING = "writing"
    GENERAL = "general"


class ValueType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    TIME = "time"
    BOOL = "bool"


class MemoryType(str, Enum):
    EVENT = "event"
    FACT = "fact"
    PREFERENCE_EVIDENCE = "preference_evidence"
    TASK = "task"


class ResponseStyle(BaseModel):
    format: str | None = Field(default=None, max_length=200)
    emoji: Literal["none", "few", "normal"] | None = None


class PersonaProfile(BaseModel):
    id: str
    version: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=32)
    tone: str = Field(min_length=1, max_length=200)
    verbosity: Verbosity
    language: str
    values: list[str] = Field(default_factory=list, max_length=20)
    boundaries: list[str] = Field(default_factory=list, max_length=20)
    taboos: list[str] = Field(default_factory=list, max_length=20)
    response_style: ResponseStyle = Field(default_factory=ResponseStyle)
    created_at: str
    updated_at: str
    source: Literal["user_confirmed", "imported", "default"]


class PersonaUpdate(BaseModel):
    """PUT 请求体：不含 id / version / 时间戳，那些由服务端管。"""

    display_name: str = Field(min_length=1, max_length=32)
    tone: str = Field(min_length=1, max_length=200)
    verbosity: Verbosity = Verbosity.MEDIUM
    language: str = "zh-CN"
    values: list[str] = Field(default_factory=list, max_length=20)
    boundaries: list[str] = Field(default_factory=list, max_length=20)
    taboos: list[str] = Field(default_factory=list, max_length=20)
    response_style: ResponseStyle = Field(default_factory=ResponseStyle)


class MemoryRef(BaseModel):
    id: str
    sensitivity: Sensitivity


class UsedContext(BaseModel):
    persona_version: int = Field(ge=1)
    preferences_used: list[str] = Field(default_factory=list)
    memories_used: list[MemoryRef] = Field(default_factory=list)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=32000)


class ChatResponse(BaseModel):
    reply: str
    used_context: UsedContext


class SupersededValue(BaseModel):
    value: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    superseded_at: str


class PreferenceItem(BaseModel):
    id: str
    domain: PreferenceDomain
    key: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=500)
    value_type: ValueType
    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: Sensitivity
    source: Literal["user_explicit", "inferred"]
    created_at: str
    last_used_at: str | None = None
    superseded_values: list[SupersededValue] = Field(default_factory=list, max_length=5)


class PreferenceCreate(BaseModel):
    domain: PreferenceDomain
    key: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=500)
    value_type: ValueType = ValueType.TEXT
    sensitivity: Sensitivity = Sensitivity.LOW
    source: Literal["user_explicit", "inferred"] = "user_explicit"


class PreferencePatch(BaseModel):
    value: str | None = Field(default=None, min_length=1, max_length=500)
    value_type: ValueType | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    sensitivity: Sensitivity | None = None


class PreferenceList(BaseModel):
    items: list[PreferenceItem]
    total: int = Field(ge=0)


class Consent(BaseModel):
    confirmed_by: Literal["user"]
    confirmed_at: str
    channel: Literal["cli", "api"]


class MemoryItem(BaseModel):
    id: str
    session_id: str
    ts: str
    type: MemoryType
    summary: str = Field(min_length=1, max_length=500)
    entities: list[str] = Field(default_factory=list, max_length=20)
    raw_ref: str | None = None
    embedding_ref: str | None = None
    importance: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: Sensitivity
    consent: Consent | None = None
    expires_at: str | None = None


class MemoryList(BaseModel):
    items: list[MemoryItem]
    total: int = Field(ge=0)


class WorkingContext(BaseModel):
    session_id: str
    task_goal: str | None = Field(default=None, max_length=300)
    active_entities: list[str] = Field(default_factory=list, max_length=20)
    open_questions: list[str] = Field(default_factory=list, max_length=10)
    recent_turns: list[str] = Field(default_factory=list, max_length=20)
    ttl: str
    updated_at: str
    expires_at: str


class EvalRunRequest(BaseModel):
    """不传 case_ids 表示跑全部用例。"""

    case_ids: list[str] | None = None


class EvalRunResponse(BaseModel):
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    failures: dict[str, list[str]] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    milestone: str | None = None
