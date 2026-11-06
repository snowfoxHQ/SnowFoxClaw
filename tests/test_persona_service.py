"""W1-1：PersonaService。

两类断言：

- 行为：惰性默认、更新即生效、回滚写新行、导入不生效；
- 对齐：服务产出必须能过 `schema/persona.json`，服务拒绝的输入 schema 也拒绝。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from snowfoxclaw.persona import DEFAULT_PERSONA, PersonaError, PersonaNotFound, PersonaService
from snowfoxclaw.storage import StorageError, open_database

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "snowfoxclaw" / "schema" / "persona.json"
)


@pytest.fixture()
def service(tmp_path: Path) -> PersonaService:
    database = open_database(tmp_path / "snowfoxclaw.db")
    return PersonaService(database, now=lambda: "2026-11-07T10:00:00Z")


def _persona_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _assert_matches_schema(record: dict[str, Any]) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(record, _persona_schema())


# ---------- 读取与惰性默认 ----------


def test_first_read_creates_default_persona(service: PersonaService):
    record = service.get_active()

    assert record["id"] == "persona_default"
    assert record["version"] == 1
    assert record["source"] == "default"
    assert record["display_name"] == DEFAULT_PERSONA["display_name"]
    # 默认人格只是「可用」，不能冒充用户确认过的版本
    assert service.is_confirmed() is False
    _assert_matches_schema(record)


def test_second_read_does_not_create_another_version(service: PersonaService):
    service.get_active()
    service.get_active()
    assert [row["version"] for row in service.history()] == [1]


def test_get_missing_version_raises(service: PersonaService):
    with pytest.raises(PersonaNotFound):
        service.get(9)


def test_broken_active_pointer_is_not_silently_ignored(service: PersonaService, tmp_path: Path):
    service.get_active()
    database = open_database(tmp_path / "snowfoxclaw.db")
    from snowfoxclaw.storage.repositories.meta import MetaRepository

    MetaRepository(database).set("persona.active_version", "42")

    with pytest.raises(StorageError, match="指向不存在"):
        PersonaService(database).get_active()


# ---------- 写入与激活 ----------


def test_confirmed_create_activates(service: PersonaService):
    service.get_active()
    record = service.create(display_name="小狐", tone="更直接", verbosity="short")

    assert record["version"] == 2
    assert record["source"] == "user_confirmed"
    assert service.is_confirmed() is True
    assert service.get_active()["version"] == 2
    assert service.get_active()["verbosity"] == "short"


def test_imported_create_does_not_change_active(service: PersonaService):
    service.get_active()
    service.create(display_name="小狐", tone="导入的", source="imported")

    assert service.get_active()["version"] == 1
    assert service.get_active()["tone"] == DEFAULT_PERSONA["tone"]
    assert service.is_confirmed() is False


def test_update_only_touches_given_fields(service: PersonaService):
    service.create(display_name="小狐", tone="原语气", taboos=["亲爱的"])
    record = service.update({"display_name": "阿狐"})

    assert record["version"] == 2
    assert record["display_name"] == "阿狐"
    assert record["tone"] == "原语气"
    assert record["taboos"] == ["亲爱的"]
    # 上一版原样保留
    assert service.get(1)["display_name"] == "小狐"


def test_update_rejects_unknown_field(service: PersonaService):
    service.get_active()
    with pytest.raises(PersonaError, match="不支持修改"):
        service.update({"is_active": True})


def test_update_rejects_empty_changes(service: PersonaService):
    service.get_active()
    with pytest.raises(PersonaError, match="至少需要一个字段"):
        service.update({})


def test_activate_older_confirmed_version(service: PersonaService):
    service.create(display_name="小狐", tone="第一版")
    service.create(display_name="小狐", tone="第二版")

    service.activate(1)

    assert service.get_active()["version"] == 1
    assert service.get_active()["tone"] == "第一版"
    # 回指旧版本是允许的（用户主动切回），但版本号没有新增
    assert [row["version"] for row in service.history()] == [2, 1]


def test_activate_imported_version_rejected(service: PersonaService):
    service.get_active()
    imported = service.create(display_name="小狐", tone="导入的", source="imported")

    with pytest.raises(StorageError, match="不能激活"):
        service.activate(imported["version"])


# ---------- 回滚 ----------


def test_rollback_writes_new_version_instead_of_rewinding(service: PersonaService):
    service.create(display_name="小狐", tone="第一版", taboos=["亲爱的"])
    service.create(display_name="小狐", tone="第二版")

    rolled = service.rollback(1)

    assert rolled["version"] == 3
    assert rolled["tone"] == "第一版"
    assert rolled["taboos"] == ["亲爱的"]
    assert service.get_active()["version"] == 3
    # 旧版本一字未改
    assert service.get(1)["tone"] == "第一版"
    assert service.get(2)["tone"] == "第二版"


def test_rollback_to_missing_version_raises(service: PersonaService):
    service.get_active()
    with pytest.raises(PersonaNotFound):
        service.rollback(7)


def test_versions_stay_monotonic_after_repeated_rollback(service: PersonaService):
    service.create(display_name="小狐", tone="A")
    service.create(display_name="小狐", tone="B")
    service.rollback(1)
    service.rollback(2)

    assert [row["version"] for row in service.history()] == [4, 3, 2, 1]


# ---------- 与 JSON Schema 对齐 ----------


@pytest.mark.parametrize(
    "payload",
    [
        {"display_name": "呼" * 33, "tone": "直接"},
        {"display_name": "小狐", "tone": "直" * 201},
        {"display_name": "小狐", "tone": "直接", "verbosity": "verbose"},
        {"display_name": "小狐", "tone": "直接", "language": "中文"},
        {"display_name": "小狐", "tone": "直接", "values": ["值"] * 21},
        {"display_name": "小狐", "tone": "直接", "taboos": ["讳" * 101]},
        {"display_name": "小狐", "tone": "直接", "response_style": {"emoji": "lots"}},
        {"display_name": "小狐", "tone": "直接", "response_style": {"color": "red"}},
    ],
)
def test_invalid_payload_rejected_and_schema_agrees(service: PersonaService, payload: dict):
    with pytest.raises(PersonaError):
        service.create(**payload)

    # schema 也拒绝同一份输入（补上模型侧必填的元字段）
    jsonschema = pytest.importorskip("jsonschema")
    full = {
        "id": "persona_default",
        "version": 1,
        "created_at": "2026-11-07T10:00:00Z",
        "updated_at": "2026-11-07T10:00:00Z",
        "source": "user_confirmed",
        **payload,
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(full, _persona_schema())


def test_history_records_satisfy_schema(service: PersonaService):
    service.get_active()
    service.update({"tone": "换成更短的句子"})
    for record in service.history():
        _assert_matches_schema(record)
