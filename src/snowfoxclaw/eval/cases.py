"""评估用例加载与结构校验（M0-3）。

用例是契约，不是散落的对话记录：每条都必须带可判定断言，断言类型必须被
:mod:`snowfoxclaw.eval.checks` 认识，否则跑完只能靠人眼看，等于没有评估。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CASES_PATH = Path(__file__).resolve().parents[3] / "eval" / "cases.yaml"

ASSERTION_TYPES = frozenset(
    {"contains", "not_contains", "max_chars", "min_chars", "regex", "not_regex"}
)
_LENGTH_TYPES = frozenset({"max_chars", "min_chars"})
_REGEX_TYPES = frozenset({"regex", "not_regex"})
_SENSITIVITIES = frozenset({"low", "medium", "high"})

PERSONA_CATEGORIES = frozenset(
    {"address", "tone", "verbosity", "boundary", "taboo", "cross_session", "values"}
)
MEMORY_CATEGORIES = frozenset(
    {"recall", "ranking", "sensitivity", "delete", "filter", "quota", "empty", "cross_session"}
)
_EXPECT_KEYS = frozenset({"retrieved", "not_retrieved", "top1", "min_count", "max_count"})

MIN_PERSONA_CASES = 20
MIN_MEMORY_CASES = 10


class EvalCaseError(ValueError):
    """用例文件缺失、字段非法或数量不足。"""


@dataclass(frozen=True)
class Assertion:
    type: str
    value: str | int


@dataclass(frozen=True)
class PersonaCase:
    id: str
    category: str
    persona: str
    profile: Mapping[str, Any]
    message: str
    history: tuple[str, ...]
    expect: tuple[Assertion, ...]


@dataclass(frozen=True)
class MemorySetup:
    id: str
    text: str
    type: str = "fact"
    sensitivity: str = "low"
    importance: float = 0.5
    session_id: str = "sess_eval01"


@dataclass(frozen=True)
class MemoryCase:
    id: str
    category: str
    memories: tuple[MemorySetup, ...]
    delete: tuple[str, ...]
    query: str
    top_k: int
    filters: Mapping[str, Any]
    expect: Mapping[str, Any]


@dataclass(frozen=True)
class CaseSet:
    version: int
    personas: Mapping[str, Mapping[str, Any]]
    persona_cases: tuple[PersonaCase, ...]
    memory_cases: tuple[MemoryCase, ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvalCaseError(message)


def _parse_assertion(case_id: str, raw: Any) -> Assertion:
    _require(isinstance(raw, dict), f"{case_id}: 断言必须是映射")
    kind = str(raw.get("type", ""))
    _require(kind in ASSERTION_TYPES, f"{case_id}: 未知断言类型 {kind!r}")
    value = raw.get("value")
    _require(value is not None, f"{case_id}: 断言 {kind} 缺少 value")

    if kind in _LENGTH_TYPES:
        _require(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f"{case_id}: {kind} 的 value 必须是非负整数",
        )
        return Assertion(type=kind, value=int(value))

    text = str(value)
    _require(text != "", f"{case_id}: 断言 {kind} 的 value 不能为空")
    if kind in _REGEX_TYPES:
        try:
            re.compile(text)
        except re.error as exc:
            raise EvalCaseError(f"{case_id}: 正则无法编译 {text!r}（{exc}）") from exc
    return Assertion(type=kind, value=text)


def _parse_persona_case(case_id: str, raw: Any, personas: Mapping[str, Any]) -> PersonaCase:
    _require(isinstance(raw, dict), f"{case_id}: 用例必须是映射")

    category = str(raw.get("category", ""))
    _require(category in PERSONA_CATEGORIES, f"{case_id}: 未知人格用例类别 {category!r}")

    persona = str(raw.get("persona", ""))
    _require(persona in personas, f"{case_id}: 引用了不存在的 persona {persona!r}")

    message = raw.get("message")
    _require(isinstance(message, str) and message.strip() != "", f"{case_id}: message 不能为空")

    history = raw.get("history") or []
    _require(isinstance(history, list), f"{case_id}: history 必须是列表")
    _require(
        all(isinstance(turn, str) and turn.strip() for turn in history),
        f"{case_id}: history 元素必须是非空字符串",
    )

    assertions = raw.get("expect") or []
    _require(isinstance(assertions, list) and assertions, f"{case_id}: expect 不能为空")
    parsed = tuple(_parse_assertion(case_id, item) for item in assertions)

    return PersonaCase(
        id=case_id,
        category=category,
        persona=persona,
        profile=personas[persona],
        message=message,
        history=tuple(history),
        expect=parsed,
    )


def _parse_memory_setup(case_id: str, raw: Any) -> MemorySetup:
    _require(isinstance(raw, dict), f"{case_id}: memories 元素必须是映射")

    memory_id = raw.get("id")
    text = raw.get("text")
    _require(isinstance(memory_id, str) and memory_id, f"{case_id}: memories 缺少 id")
    _require(isinstance(text, str) and text, f"{case_id}: memories 缺少 text")

    sensitivity = str(raw.get("sensitivity", "low"))
    _require(sensitivity in _SENSITIVITIES, f"{case_id}: 未知敏感级 {sensitivity!r}")

    try:
        importance = float(raw.get("importance", 0.5))
    except (TypeError, ValueError) as exc:
        raise EvalCaseError(f"{case_id}: importance 必须是数字") from exc
    _require(0.0 <= importance <= 1.0, f"{case_id}: importance 必须落在 [0,1]")

    return MemorySetup(
        id=memory_id,
        text=text,
        type=str(raw.get("type", "fact")),
        sensitivity=sensitivity,
        importance=importance,
        session_id=str(raw.get("session_id", "sess_eval01")),
    )


def _parse_memory_case(case_id: str, raw: Any) -> MemoryCase:
    _require(isinstance(raw, dict), f"{case_id}: 用例必须是映射")

    category = str(raw.get("category", ""))
    _require(category in MEMORY_CATEGORIES, f"{case_id}: 未知记忆用例类别 {category!r}")

    raw_memories = raw.get("memories") or []
    _require(isinstance(raw_memories, list), f"{case_id}: memories 必须是列表")
    memories = tuple(_parse_memory_setup(case_id, item) for item in raw_memories)
    known_ids = {item.id for item in memories}
    _require(len(known_ids) == len(memories), f"{case_id}: memories 内 id 重复")

    raw_delete = raw.get("delete") or []
    _require(isinstance(raw_delete, list), f"{case_id}: delete 必须是列表")
    delete = tuple(str(item) for item in raw_delete)
    _require(
        all(item in known_ids for item in delete),
        f"{case_id}: delete 引用了 memeries 中不存在的 id",
    )

    query = raw.get("query")
    _require(isinstance(query, str) and query.strip() != "", f"{case_id}: query 不能为空")

    top_k = raw.get("top_k", 5)
    _require(
        isinstance(top_k, int) and not isinstance(top_k, bool) and top_k >= 1,
        f"{case_id}: top_k 必须是 ≥1 的整数",
    )

    filters = raw.get("filters") or {}
    _require(isinstance(filters, dict), f"{case_id}: filters 必须是映射")

    expect = raw.get("expect") or {}
    _require(isinstance(expect, dict) and expect, f"{case_id}: expect 不能为空")
    unknown = set(expect) - _EXPECT_KEYS
    _require(not unknown, f"{case_id}: 未知 expect 键 {sorted(unknown)}")

    for key in ("retrieved", "not_retrieved"):
        value = expect.get(key)
        if value is None:
            continue
        _require(isinstance(value, list), f"{case_id}: {key} 必须是列表")
        _require(
            all(isinstance(item, str) and item in known_ids for item in value),
            f"{case_id}: {key} 引用了 memories 中不存在的 id",
        )

    top1 = expect.get("top1")
    if top1 is not None:
        _require(top1 in known_ids, f"{case_id}: top1 引用了 memories 中不存在的 id")

    for key in ("min_count", "max_count"):
        value = expect.get(key)
        if value is None:
            continue
        _require(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f"{case_id}: {key} 必须是非负整数",
        )

    low, high = expect.get("min_count"), expect.get("max_count")
    if low is not None and high is not None:
        _require(low <= high, f"{case_id}: min_count 不能大于 max_count")

    return MemoryCase(
        id=case_id,
        category=category,
        memories=memories,
        delete=delete,
        query=query,
        top_k=top_k,
        filters=filters,
        expect=expect,
    )


def load_cases(path: Path | str | None = None) -> CaseSet:
    """加载并校验用例集。任一环节不合法都抛 EvalCaseError，不做部分加载。"""
    target = Path(path) if path is not None else DEFAULT_CASES_PATH
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise EvalCaseError(f"用例文件不存在：{target}") from exc

    data = yaml.safe_load(raw) or {}
    _require(isinstance(data, dict), "用例文件顶层必须是映射")

    version = data.get("version")
    _require(version == 1, f"不支持的用例版本：{version!r}，当前只认 1")

    personas = data.get("personas") or {}
    _require(isinstance(personas, dict), "personas 必须是映射")

    raw_persona_cases = data.get("persona_cases") or []
    raw_memory_cases = data.get("memory_cases") or []
    _require(isinstance(raw_persona_cases, list), "persona_cases 必须是列表")
    _require(isinstance(raw_memory_cases, list), "memory_cases 必须是列表")

    persona_cases: list[PersonaCase] = []
    memory_cases: list[MemoryCase] = []
    seen: set[str] = set()

    for raw_case in raw_persona_cases:
        _require(isinstance(raw_case, dict), "persona_cases 元素必须是映射")
        case_id = raw_case.get("id")
        _require(isinstance(case_id, str) and case_id, "persona_cases 元素缺少 id")
        _require(case_id not in seen, f"用例 id 重复：{case_id}")
        seen.add(case_id)
        persona_cases.append(_parse_persona_case(case_id, raw_case, personas))

    for raw_case in raw_memory_cases:
        _require(isinstance(raw_case, dict), "memory_cases 元素必须是映射")
        case_id = raw_case.get("id")
        _require(isinstance(case_id, str) and case_id, "memory_cases 元素缺少 id")
        _require(case_id not in seen, f"用例 id 重复：{case_id}")
        seen.add(case_id)
        memory_cases.append(_parse_memory_case(case_id, raw_case))

    _require(
        len(persona_cases) >= MIN_PERSONA_CASES,
        f"人格用例至少 {MIN_PERSONA_CASES} 条，当前 {len(persona_cases)} 条",
    )
    _require(
        len(memory_cases) >= MIN_MEMORY_CASES,
        f"记忆用例至少 {MIN_MEMORY_CASES} 条，当前 {len(memory_cases)} 条",
    )

    return CaseSet(
        version=version,
        personas=personas,
        persona_cases=tuple(persona_cases),
        memory_cases=tuple(memory_cases),
    )
