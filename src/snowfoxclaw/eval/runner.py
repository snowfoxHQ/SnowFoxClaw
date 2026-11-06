"""评估执行（M0-3）。

人格用例需要外部注入回复（W3-2 接真实模型），记忆用例现在就能对着
:class:`~snowfoxclaw.memory.retriever.InMemoryIndex` 跑，不依赖任何模型。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowfoxclaw.embedding.mock import MockEmbedding
from snowfoxclaw.embedding.provider import EmbeddingProvider
from snowfoxclaw.eval.cases import MemoryCase, PersonaCase
from snowfoxclaw.eval.checks import check
from snowfoxclaw.memory.retriever import InMemoryIndex, MemoryItem


@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class Report:
    outcomes: tuple[CaseOutcome, ...]

    @property
    def passed(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.passed)

    @property
    def failed(self) -> int:
        return len(self.outcomes) - self.passed

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def summary(self) -> dict[str, Any]:
        return {
            "total": len(self.outcomes),
            "passed": self.passed,
            "failed": self.failed,
            "failures": {
                outcome.case_id: list(outcome.failures)
                for outcome in self.outcomes
                if not outcome.passed
            },
        }


def load_replies(path: Path | str) -> dict[str, str]:
    """读 JSONL，每行 ``{"case_id": "p01", "reply": "..."}``。"""
    replies: dict[str, str] = {}
    text = Path(path).read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"第 {line_no} 行不是合法 JSON：{exc}") from exc
        case_id = row.get("case_id")
        reply = row.get("reply")
        if not case_id or not isinstance(reply, str):
            raise ValueError(f"第 {line_no} 行缺少 case_id 或 reply")
        replies[str(case_id)] = reply
    return replies


def run_persona_cases(cases: Sequence[PersonaCase], replies: Mapping[str, str]) -> Report:
    outcomes: list[CaseOutcome] = []
    for case in cases:
        reply = replies.get(case.id)
        if reply is None:
            outcomes.append(CaseOutcome(case.id, False, ("没有提供回复",)))
            continue
        failures = check(reply, case.expect)
        outcomes.append(CaseOutcome(case.id, not failures, tuple(failures)))
    return Report(tuple(outcomes))


def run_memory_cases(
    cases: Sequence[MemoryCase], provider: EmbeddingProvider | None = None
) -> Report:
    outcomes = []
    for case in cases:
        failures = _run_memory_case(case, provider)
        outcomes.append(CaseOutcome(case.id, not failures, tuple(failures)))
    return Report(tuple(outcomes))


def _run_memory_case(case: MemoryCase, provider: EmbeddingProvider | None) -> list[str]:
    index = InMemoryIndex(provider or MockEmbedding(dim=32))
    for setup in case.memories:
        index.upsert(
            MemoryItem(
                id=setup.id,
                text=setup.text,
                metadata={
                    "session_id": setup.session_id,
                    "type": setup.type,
                    "sensitivity": setup.sensitivity,
                    "importance": setup.importance,
                },
            )
        )
    if case.delete:
        index.delete(list(case.delete))

    results = index.search(case.query, top_k=case.top_k, filters=dict(case.filters) or None)
    ids = [item.id for item in results]

    failures: list[str] = []
    for expected in case.expect.get("retrieved", []):
        if expected not in ids:
            failures.append(f"未召回 {expected}（实际 {ids}）")
    for forbidden in case.expect.get("not_retrieved", []):
        if forbidden in ids:
            failures.append(f"不该召回 {forbidden}（实际 {ids}）")

    top1 = case.expect.get("top1")
    if top1 is not None and (not ids or ids[0] != top1):
        failures.append(f"首条应是 {top1}，实际 {ids[:1]}")

    min_count = case.expect.get("min_count")
    if min_count is not None and len(ids) < min_count:
        failures.append(f"结果过少：{len(ids)} < {min_count}")
    max_count = case.expect.get("max_count")
    if max_count is not None and len(ids) > max_count:
        failures.append(f"结果过多：{len(ids)} > {max_count}")

    return failures
