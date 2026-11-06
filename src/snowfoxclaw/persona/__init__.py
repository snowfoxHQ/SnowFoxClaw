"""人格配置：读写、版本、激活。

对外只暴露 `PersonaService`；`sqlite3` 与 Repository 不越过这一层。
"""

from snowfoxclaw.persona.service import (
    DEFAULT_PERSONA,
    PersonaError,
    PersonaNotFound,
    PersonaService,
)

__all__ = ["DEFAULT_PERSONA", "PersonaError", "PersonaNotFound", "PersonaService"]
