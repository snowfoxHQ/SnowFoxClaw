"""敏感信息检测规则（M0-2）。

只做规则可判定的部分：结构化凭证、强特征号段、显式密钥。
语义类风险（住址、病史、财务状况）依赖上下文，正则无法可靠判定，
交由 :mod:`snowfoxclaw.memory.extractor` 的摘要链路与用户显式确认处理，
边界说明见同目录 ``data_class.md``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "Finding",
    "Sensitivity",
    "max_sensitivity",
    "redact",
    "scan",
]


class Sensitivity(str, Enum):
    """敏感级，与 ``docs/architecture.md`` 5.6 保持一致。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_LEVEL_ORDER = {Sensitivity.LOW: 0, Sensitivity.MEDIUM: 1, Sensitivity.HIGH: 2}


@dataclass(frozen=True)
class Finding:
    """一次命中。``start``/``end`` 为半开区间，便于直接切片替换。"""

    kind: str
    start: int
    end: int
    sensitivity: Sensitivity


@dataclass(frozen=True)
class _Rule:
    kind: str
    pattern: re.Pattern[str]
    sensitivity: Sensitivity
    checksum: str | None = None


_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK = "10X98765432"

_RULES: tuple[_Rule, ...] = (
    _Rule(
        kind="id_card",
        pattern=re.compile(r"(?<![0-9A-Za-z])(\d{17}[\dXx])(?![0-9A-Za-z])"),
        sensitivity=Sensitivity.HIGH,
        checksum="cn_id",
    ),
    _Rule(
        kind="bank_card",
        pattern=re.compile(r"(?<!\d)(\d{16,19})(?!\d)"),
        sensitivity=Sensitivity.HIGH,
        checksum="luhn",
    ),
    _Rule(
        kind="phone",
        pattern=re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)"),
        sensitivity=Sensitivity.HIGH,
    ),
    _Rule(
        kind="api_key",
        pattern=re.compile(
            r"(?:sk-[A-Za-z0-9]{16,}"
            r"|gh[pousr]_[A-Za-z0-9]{20,}"
            r"|AKIA[0-9A-Z]{16}"
            r"|(?i:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{16,}))"
        ),
        sensitivity=Sensitivity.HIGH,
    ),
    _Rule(
        kind="password",
        pattern=re.compile(r"(?:密码|口令|password|passwd|pwd)\s*(?:是|为|[:=：])\s*(\S{4,})"),
        sensitivity=Sensitivity.HIGH,
    ),
    _Rule(
        kind="email",
        pattern=re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        sensitivity=Sensitivity.MEDIUM,
    ),
)


def _cn_id_valid(value: str) -> bool:
    digits = value[:17]
    if not digits.isdigit():
        return False
    total = sum(int(d) * w for d, w in zip(digits, _ID_WEIGHTS, strict=True))
    return value[-1].upper() == _ID_CHECK[total % 11]


def _luhn_valid(value: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(value)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def scan(text: str) -> list[Finding]:
    """返回所有命中，按位置升序。重叠命中只保留最先出现的那个。"""
    if not text:
        return []

    findings: list[Finding] = []
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            value = match.group(0)
            if rule.checksum == "cn_id" and not _cn_id_valid(value):
                continue
            if rule.checksum == "luhn" and not _luhn_valid(value):
                continue
            findings.append(
                Finding(
                    kind=rule.kind,
                    start=match.start(),
                    end=match.end(),
                    sensitivity=rule.sensitivity,
                )
            )

    findings.sort(key=lambda f: (f.start, -(f.end - f.start)))
    result: list[Finding] = []
    for item in findings:
        if result and item.start < result[-1].end:
            continue
        result.append(item)
    return result


def max_sensitivity(text: str) -> Sensitivity:
    """文本中命中的最高敏感级；无命中视为 ``LOW``。"""
    findings = scan(text)
    if not findings:
        return Sensitivity.LOW
    return max((f.sensitivity for f in findings), key=lambda s: _LEVEL_ORDER[s])


def redact(text: str, placeholder: str = "[REDACTED:{kind}]") -> str:
    """把命中片段替换为占位符，用于落库前脱敏与日志输出。"""
    findings = scan(text)
    if not findings:
        return text

    parts: list[str] = []
    cursor = 0
    for finding in findings:
        parts.append(text[cursor : finding.start])
        parts.append(placeholder.format(kind=finding.kind))
        cursor = finding.end
    parts.append(text[cursor:])
    return "".join(parts)
