"""确定性断言引擎（M0-3）。

只做字符串层面可判定的检查。语义类判断（「有没有安慰到位」）不进来自动打分：
硬塞规则只会得到虚假的通过率，那类比人工抽检更危险。
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from snowfoxclaw.eval.cases import Assertion


def check(reply: str, assertions: Sequence[Assertion]) -> list[str]:
    """返回失败描述列表，空列表表示全部通过。"""
    failures: list[str] = []
    for assertion in assertions:
        detail = _evaluate(reply, assertion)
        if detail is not None:
            failures.append(detail)
    return failures


def _evaluate(reply: str, assertion: Assertion) -> str | None:
    kind = assertion.type
    value = assertion.value

    if kind == "contains" and str(value) not in reply:
        return f"缺少必需内容：{value!r}"
    if kind == "not_contains" and str(value) in reply:
        return f"出现禁止内容：{value!r}"
    if kind == "max_chars" and len(reply) > int(value):
        return f"回复过长：{len(reply)} > {value}"
    if kind == "min_chars" and len(reply) < int(value):
        return f"回复过短：{len(reply)} < {value}"
    if kind == "regex" and re.search(str(value), reply) is None:
        return f"未匹配期望模式：{value!r}"
    if kind == "not_regex" and re.search(str(value), reply) is not None:
        return f"命中禁止模式：{value!r}"
    return None
