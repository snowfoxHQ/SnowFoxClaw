"""M0-1b：JSON Schema 与 schema/fields.md 的一致性校验。

覆盖 fields.md 第 7 节列的六项，任何一项失败都说明契约与实现脱节。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import FormatChecker, ValidationError, validate

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "src" / "snowfoxclaw" / "schema"
FIELDS_MD = SCHEMA_DIR / "fields.md"

TS = "2026-11-07T10:00:00Z"

# (锚点名, 文件名, $defs 内的名字或 None)
TABLES = [
    ("persona_profile", "persona.json", None),
    ("response_style", "persona.json", "response_style"),
    ("preference_item", "preference.json", None),
    ("preference_superseded", "preference.json", "superseded_value"),
    ("episodic_memory", "episodic.json", None),
    ("consent", "episodic.json", "consent"),
    ("working_context", "working_context.json", None),
    ("conversation_turn", "conversation_turn.json", None),
    ("used_context", "conversation_turn.json", "used_context"),
    ("memory_ref", "conversation_turn.json", "memory_ref"),
    ("tokens", "conversation_turn.json", "tokens"),
]


def parse_table(name: str) -> dict[str, bool]:
    """从 fields.md 的锚点后取出第一张表，返回 {字段: 是否必填}。"""
    text = FIELDS_MD.read_text(encoding="utf-8")
    marker = f"<!-- table: {name} -->"
    assert marker in text, f"fields.md 缺少锚点 {marker}"
    rest = text.split(marker, 1)[1]

    rows: list[str] = []
    for line in rest.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            rows.append(stripped)
        elif rows and stripped:
            break

    assert len(rows) >= 3, f"{name} 表格至少需要表头、分隔行和一行数据"
    result: dict[str, bool] = {}
    for line in rows[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        assert len(cells) >= 3, f"{name} 表格列数不足：{line}"
        field = cells[0].strip("`")
        result[field] = cells[2] == "是"
    return result


def load_schema(filename: str) -> dict:
    return json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))


def node_of(schema: dict, def_name: str | None) -> dict:
    return schema if def_name is None else schema["$defs"][def_name]


def check(instance: dict, filename: str) -> None:
    validate(instance, load_schema(filename), format_checker=FormatChecker())


def persona() -> dict:
    return {
        "id": "persona_default",
        "version": 1,
        "display_name": "狐狸",
        "tone": "温和但直接",
        "verbosity": "medium",
        "language": "zh-CN",
        "created_at": TS,
        "updated_at": TS,
        "source": "user_confirmed",
    }


def preference() -> dict:
    return {
        "id": "pref_abc123",
        "domain": "schedule",
        "key": "提醒时间",
        "value": "晚上11点",
        "value_type": "time",
        "confidence": 1.0,
        "sensitivity": "low",
        "source": "user_explicit",
        "created_at": TS,
    }


def episodic(sensitivity: str = "low") -> dict:
    item = {
        "id": "mem_abc123",
        "session_id": "sess_abc123",
        "ts": TS,
        "type": "fact",
        "summary": "用户习惯在晚上工作",
        "importance": 0.6,
        "confidence": 0.8,
        "sensitivity": sensitivity,
    }
    if sensitivity == "high":
        item["consent"] = {"confirmed_by": "user", "confirmed_at": TS, "channel": "cli"}
    return item


def context() -> dict:
    return {
        "session_id": "sess_abc123",
        "ttl": "2h",
        "updated_at": TS,
        "expires_at": TS,
    }


def turn(role: str = "assistant") -> dict:
    return {
        "id": "turn_abc123",
        "session_id": "sess_abc123",
        "ts": TS,
        "role": role,
        "content": "好的，我记下了。",
        "persona_version": 1,
        "used_context": {
            "persona_version": 1,
            "preferences_used": ["pref_abc123"],
            "memories_used": [{"id": "mem_abc123", "sensitivity": "low"}],
        },
        "tokens": {"prompt": 10, "completion": 5},
    }


def test_all_tables_declared():
    """fields.md 里的 schema 表格锚点必须都被校验覆盖。"""
    text = FIELDS_MD.read_text(encoding="utf-8")
    declared = {
        line.split("<!-- table:", 1)[1].split("-->", 1)[0].strip()
        for line in text.splitlines()
        if line.strip().startswith("<!-- table:")
    }
    assert declared == {name for name, _, _ in TABLES}


@pytest.mark.parametrize(("table", "filename", "def_name"), TABLES)
def test_field_names_match(table: str, filename: str, def_name: str | None):
    parsed = parse_table(table)
    props = node_of(load_schema(filename), def_name)["properties"]
    assert set(parsed) == set(props), f"{table} 字段集与 {filename} 不一致"


@pytest.mark.parametrize(("table", "filename", "def_name"), TABLES)
def test_required_match(table: str, filename: str, def_name: str | None):
    parsed = parse_table(table)
    required = set(node_of(load_schema(filename), def_name).get("required", []))
    for field, is_required in parsed.items():
        assert (field in required) == is_required, f"{table}.{field} 必填标记不一致"


def test_unique_constraint_declared():
    schema = load_schema("preference.json")
    assert schema["x-unique"] == [["domain", "key"]]
    assert {"domain", "key"} <= set(schema["required"])


def test_timestamp_requires_timezone():
    check(persona(), "persona.json")
    broken = persona()
    broken["created_at"] = "2026-11-07T10:00:00"
    with pytest.raises(ValidationError):
        check(broken, "persona.json")


def test_unknown_field_rejected():
    payload = persona()
    payload["nick_name"] = "多余字段"
    with pytest.raises(ValidationError):
        check(payload, "persona.json")


def test_high_memory_requires_consent():
    check(episodic("high"), "episodic.json")

    payload = episodic("high")
    del payload["consent"]
    with pytest.raises(ValidationError):
        check(payload, "episodic.json")


def test_user_turn_rejects_used_context():
    user_turn = turn("user")
    user_turn["used_context"] = None
    check(user_turn, "conversation_turn.json")

    user_turn["used_context"] = turn()["used_context"]
    with pytest.raises(ValidationError):
        check(user_turn, "conversation_turn.json")


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        ("persona.json", persona()),
        ("preference.json", preference()),
        ("episodic.json", episodic()),
        ("conversation_turn.json", turn()),
        ("working_context.json", context()),
    ],
)
def test_valid_instances_pass(filename: str, payload: dict):
    check(payload, filename)


def test_used_context_json_roundtrip():
    original = turn()
    restored = json.loads(json.dumps(original, ensure_ascii=False))
    assert restored == original
    check(restored, "conversation_turn.json")
