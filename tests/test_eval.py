"""M0-3：评估用例集、断言引擎与执行器。"""

from __future__ import annotations

from pathlib import Path

import pytest

from snowfoxclaw.eval.cases import (
    MIN_MEMORY_CASES,
    MIN_PERSONA_CASES,
    Assertion,
    EvalCaseError,
    load_cases,
)
from snowfoxclaw.eval.checks import check
from snowfoxclaw.eval.runner import load_replies, run_memory_cases, run_persona_cases

CASES = Path(__file__).resolve().parents[1] / "eval" / "cases.yaml"


def test_caseset_meets_quota():
    cases = load_cases(CASES)
    assert len(cases.persona_cases) >= MIN_PERSONA_CASES
    assert len(cases.memory_cases) >= MIN_MEMORY_CASES


def test_persona_categories_cover_required_aspects():
    categories = {case.category for case in load_cases(CASES).persona_cases}
    assert {"address", "tone", "boundary", "taboo", "cross_session"} <= categories


def test_persona_cases_reference_known_personas():
    cases = load_cases(CASES)
    for case in cases.persona_cases:
        assert case.persona in cases.personas
        assert case.profile["display_name"]


def test_memory_cases_pass_against_reference_index():
    report = run_memory_cases(load_cases(CASES).memory_cases)
    assert report.ok, report.summary()


def test_missing_replies_count_as_failure():
    cases = load_cases(CASES)
    report = run_persona_cases(cases.persona_cases, {})
    assert report.passed == 0
    assert report.failed == len(cases.persona_cases)
    assert report.outcomes[0].failures == ("没有提供回复",)


def test_check_supports_every_assertion_type():
    assertions = [
        Assertion("contains", "小狐"),
        Assertion("not_contains", "您"),
        Assertion("max_chars", 10),
        Assertion("min_chars", 2),
        Assertion("regex", "小狐"),
        Assertion("not_regex", "[!！]"),
    ]
    assert check("小狐在这", assertions) == []


def test_check_reports_each_violation():
    failures = check("您好好", [Assertion("contains", "小狐"), Assertion("not_contains", "您")])
    assert failures == ["缺少必需内容：'小狐'", "出现禁止内容：'您'"]


def test_check_enforces_length_bounds():
    assert check("短", [Assertion("min_chars", 5)]) == ["回复过短：1 < 5"]
    assert check("很长的一句话", [Assertion("max_chars", 2)]) == ["回复过长：6 > 2"]


def test_load_replies_reads_jsonl(tmp_path: Path):
    path = tmp_path / "replies.jsonl"
    path.write_text(
        '\n{"case_id": "p01", "reply": "我是小狐"}\n{"case_id": "p02", "reply": "好"}\n',
        encoding="utf-8",
    )
    replies = load_replies(path)
    assert replies == {"p01": "我是小狐", "p02": "好"}


def test_load_replies_rejects_incomplete_row(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"reply": "缺 case_id"}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_replies(path)


def test_report_summary_shape():
    report = run_memory_cases(load_cases(CASES).memory_cases)
    summary = report.summary()
    assert summary["failed"] == 0
    assert summary["total"] == summary["passed"]
    assert summary["failures"] == {}


def test_missing_cases_file_is_error(tmp_path: Path):
    with pytest.raises(EvalCaseError):
        load_cases(tmp_path / "nope.yaml")


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "cases.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_unknown_assertion_type_rejected(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
personas: {a: {display_name: 小狐}}
persona_cases:
  - id: p01
    category: tone
    persona: a
    message: 你好
    expect:
      - {type: sounds_good, value: 是}
""",
    )
    with pytest.raises(EvalCaseError, match="未知断言类型"):
        load_cases(path)


def test_unknown_persona_reference_rejected(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
personas: {a: {display_name: 小狐}}
persona_cases:
  - id: p01
    category: tone
    persona: nobody
    message: 你好
    expect:
      - {type: contains, value: 小狐}
""",
    )
    with pytest.raises(EvalCaseError, match="不存在的 persona"):
        load_cases(path)


def test_duplicate_case_id_rejected(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
personas: {a: {display_name: 小狐}}
persona_cases:
  - {id: p01, category: tone, persona: a, message: 你好, expect: [{type: contains, value: 小狐}]}
  - {id: p01, category: tone, persona: a, message: 再见, expect: [{type: contains, value: 小狐}]}
""",
    )
    with pytest.raises(EvalCaseError, match="id 重复"):
        load_cases(path)


def test_insufficient_case_count_rejected(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
personas: {a: {display_name: 小狐}}
persona_cases:
  - {id: p01, category: tone, persona: a, message: 你好, expect: [{type: contains, value: 小狐}]}
memory_cases: []
""",
    )
    with pytest.raises(EvalCaseError, match="至少"):
        load_cases(path)


def test_memory_expect_rejects_unknown_id(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
personas: {}
persona_cases: []
memory_cases:
  - id: m01
    category: recall
    memories: [{id: mem_a, text: 甲}]
    query: 甲
    expect: {retrieved: [mem_missing]}
""",
    )
    with pytest.raises(EvalCaseError, match="不存在的 id"):
        load_cases(path)
