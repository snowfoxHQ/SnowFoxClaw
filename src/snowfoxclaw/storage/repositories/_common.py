"""Repository 共用：JSON 列的编解码与写字段白名单。

JSON 列在库里叫 ``*_json``，读出来时还原成字段清单里的原名（``values``、``consent`` 等），
上层服务只面对 ``fields.md`` 的字段名，不需要知道列名后缀。
"""

from __future__ import annotations

import copy
import json
import sqlite3
from typing import Any


def dumps(value: Any) -> str:
    """紧凑且不转义中文，便于直接在 sqlite3 CLI 里看。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return copy.deepcopy(default)
    return json.loads(raw)


def decode_row(row: sqlite3.Row, json_defaults: dict[str, Any]) -> dict[str, Any]:
    """把一行转成字段清单口径的 dict，并解码 JSON 列。"""
    data: dict[str, Any] = dict(row)
    for column, default in json_defaults.items():
        field = column.removesuffix("_json")
        data[field] = loads(data.pop(column, None), default)
    return data


def check_fields(payload: dict[str, Any], allowed: frozenset[str], where: str) -> None:
    """写操作只接受白名单字段，拼错字段名必须报错而不是被静默忽略。"""
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{where} 不支持的字段：{sorted(unknown)}")
