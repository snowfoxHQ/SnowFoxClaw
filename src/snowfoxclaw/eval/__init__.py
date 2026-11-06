"""评估：用例集、断言引擎与执行器。"""

from snowfoxclaw.eval.cases import (
    CaseSet,
    EvalCaseError,
    MemoryCase,
    PersonaCase,
    load_cases,
)
from snowfoxclaw.eval.checks import check
from snowfoxclaw.eval.runner import (
    CaseOutcome,
    Report,
    load_replies,
    run_memory_cases,
    run_persona_cases,
)

__all__ = [
    "CaseOutcome",
    "CaseSet",
    "EvalCaseError",
    "MemoryCase",
    "PersonaCase",
    "Report",
    "check",
    "load_cases",
    "load_replies",
    "run_memory_cases",
    "run_persona_cases",
]
