"""PersonaService：人格的读、写、版本、激活。

三条规则来自 fields.md 第 1 节，服务层不提供绕过口：

- **只增不改**：任何「改人格」都写新行，历史版本一字不动；
- **激活必须 user_confirmed**：`create(source="imported")` 能入库但不能生效；
- **回滚 = 复制旧内容写新版本**，`active_version` 永远指向最新，绝不回指旧版本。

校验规则与 `schema/persona.json` 逐条对应，由 `tests/test_persona_service.py` 用
jsonschema 反查：服务接受的输出必须过 schema，服务拒绝的输入也必须是 schema 拒绝的。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from snowfoxclaw.storage import Database, StorageError, utc_now
from snowfoxclaw.storage.repositories.persona import PersonaRepository

# 首次启动没有库记录时的人格。它只是「可用」，不等于「用户确认」，source 记为 default
DEFAULT_PERSONA: dict[str, Any] = {
    "display_name": "小狐",
    "tone": "直接、平实，先说结论，不堆形容词，不说教",
    "verbosity": "medium",
    "language": "zh-CN",
    "values": ["先给结论再解释", "不确定就直说不知道"],
    "boundaries": ["不替用户做不可逆的决定", "不假装记得没有记录过的事"],
    "taboos": ["亲爱的", "宝贝"],
    "response_style": {"emoji": "none"},
}

_PATCHABLE = (
    "display_name",
    "tone",
    "verbosity",
    "language",
    "values",
    "boundaries",
    "taboos",
    "response_style",
)
_ARRAY_FIELDS = ("values", "boundaries", "taboos")
_VERBOSITIES = frozenset({"short", "medium", "long"})
_EMOJIS = frozenset({"none", "few", "normal"})
_SOURCES = frozenset({"user_confirmed", "imported", "default"})
# BCP-47 的宽松校验：语言标签不是自由文本，写错会让下游按语言选模板失效
_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


class PersonaError(ValueError):
    """人格内容不合 schema。"""


class PersonaNotFound(PersonaError):
    """请求的版本不存在。"""


def _validate(payload: dict[str, Any]) -> None:
    display_name = payload.get("display_name")
    if not isinstance(display_name, str) or not 1 <= len(display_name) <= 32:
        raise PersonaError("display_name 必须是 1–32 字符的字符串")

    tone = payload.get("tone")
    if not isinstance(tone, str) or not 1 <= len(tone) <= 200:
        raise PersonaError("tone 必须是 1–200 字符的字符串")

    if payload.get("verbosity") not in _VERBOSITIES:
        raise PersonaError(f"verbosity 必须是 {sorted(_VERBOSITIES)} 之一")

    language = payload.get("language")
    if not isinstance(language, str) or not _LANGUAGE_RE.match(language):
        raise PersonaError(f"language 必须是 BCP-47 标签，收到 {language!r}")

    for field in _ARRAY_FIELDS:
        items = payload.get(field, [])
        if not isinstance(items, list) or len(items) > 20:
            raise PersonaError(f"{field} 必须是最多 20 项的数组")
        for item in items:
            if not isinstance(item, str) or len(item) > 100:
                raise PersonaError(f"{field} 的每一项必须是 ≤100 字符的字符串")

    style = payload.get("response_style", {})
    if not isinstance(style, dict):
        raise PersonaError("response_style 必须是对象")
    extra = set(style) - {"format", "emoji"}
    if extra:
        raise PersonaError(f"response_style 不支持的字段：{sorted(extra)}")
    fmt = style.get("format")
    if fmt is not None and (not isinstance(fmt, str) or len(fmt) > 200):
        raise PersonaError("response_style.format 必须是 ≤200 字符的字符串")
    if "emoji" in style and style["emoji"] not in _EMOJIS:
        raise PersonaError(f"response_style.emoji 必须是 {sorted(_EMOJIS)} 之一")


class PersonaService:
    def __init__(
        self,
        database: Database,
        *,
        now: Callable[[], str] = utc_now,
    ) -> None:
        self._repo = PersonaRepository(database)
        self._now = now

    def get_active(self) -> dict[str, Any]:
        """当前人格。

        解析顺序：``meta.persona.active_version`` → 最新的 user_confirmed → 最新的 default
        → 惰性创建默认人格。``imported`` 版本不参与兜底，否则一次导入就会悄悄改掉人格。
        """
        version = self._repo.active_version()
        if version is not None:
            record = self._repo.get(version)
            if record is None:
                # meta 指向不存在的版本说明库被改坏，静默兜底会让 used_context 永远对不上
                raise StorageError(f"active_version={version} 指向不存在的人格版本")
            return record

        for candidate in reversed(self._repo.list_versions()):
            record = self._repo.get(candidate)
            if record is not None and record["source"] in {"user_confirmed", "default"}:
                return record
        return self._write(DEFAULT_PERSONA, source="default")

    def get(self, version: int) -> dict[str, Any]:
        record = self._repo.get(version)
        if record is None:
            raise PersonaNotFound(f"人格版本 {version} 不存在")
        return record

    def latest(self) -> dict[str, Any]:
        version = self._repo.latest_version()
        if version == 0:
            return self.get_active()
        return self.get(version)

    def history(self) -> list[dict[str, Any]]:
        """全部历史版本，新 → 旧。回滚界面和 used_context 排障都要用。"""
        records = [self._repo.get(version) for version in reversed(self._repo.list_versions())]
        return [record for record in records if record is not None]

    def is_confirmed(self) -> bool:
        """当前生效的人格是否经过用户确认。"""
        version = self._repo.active_version()
        if version is None:
            return False
        record = self._repo.get(version)
        return record is not None and record["source"] == "user_confirmed"

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
    ) -> dict[str, Any]:
        """写入新版本。``source=user_confirmed`` 才自动激活。"""
        if source not in _SOURCES:
            raise PersonaError(f"source 必须是 {sorted(_SOURCES)} 之一")
        payload = {
            "display_name": display_name,
            "tone": tone,
            "verbosity": verbosity,
            "language": language,
            "values": list(values or []),
            "boundaries": list(boundaries or []),
            "taboos": list(taboos or []),
            "response_style": dict(response_style or {}),
        }
        return self._write(payload, source=source)

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        """在生效版本之上打补丁，写新版本并激活。下一轮对话立即生效。"""
        if not changes:
            raise PersonaError("update 至少需要一个字段")
        unknown = set(changes) - set(_PATCHABLE)
        if unknown:
            raise PersonaError(f"不支持修改的字段：{sorted(unknown)}")

        base = self.get_active()
        payload = {field: base[field] for field in _PATCHABLE}
        payload.update(changes)
        return self._write(payload, source="user_confirmed")

    def activate(self, version: int) -> dict[str, Any]:
        record = self.get(version)
        self._repo.set_active_version(version)  # 仓库层还会再拦一次非 user_confirmed
        return record

    def rollback(self, version: int) -> dict[str, Any]:
        """回滚到旧内容，但落成 ``version = 最新 + 1`` 的新行。"""
        source = self.get(version)
        payload = {field: source[field] for field in _PATCHABLE}
        return self._write(payload, source="user_confirmed")

    def _write(self, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
        _validate(payload)
        record = self._repo.create(
            display_name=payload["display_name"],
            tone=payload["tone"],
            verbosity=payload["verbosity"],
            language=payload["language"],
            values=list(payload["values"]),
            boundaries=list(payload["boundaries"]),
            taboos=list(payload["taboos"]),
            response_style=dict(payload["response_style"]),
            source=source,
            now=self._now(),
        )
        if source == "user_confirmed":
            self._repo.set_active_version(record["version"])
        return record
