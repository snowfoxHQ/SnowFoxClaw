"""本地 HTTP 服务。

M0-8 跑通骨架，M0-4 把外部接口契约冻结成 ``api/openapi.yaml``（由 ``foxclaw openapi`` 生成）。
业务实现分别落在 W1-1 / W1-2 / W1-5 / W2-5 / W2-7 / W3-2，在此之前所有业务接口一律返回 501，
避免桩被误当成可用接口。
"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, FastAPI, HTTPException, Query

from snowfoxclaw import __version__
from snowfoxclaw.api.models import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    EvalRunRequest,
    EvalRunResponse,
    MemoryList,
    MemoryType,
    PersonaProfile,
    PersonaUpdate,
    PreferenceCreate,
    PreferenceDomain,
    PreferenceItem,
    PreferenceList,
    PreferencePatch,
    WorkingContext,
)

__all__ = ["create_app", "app"]

_STUB_RESPONSES: dict[int | str, dict[str, object]] = {
    501: {"model": ErrorResponse, "description": "该里程碑尚未实现"}
}


def _stub(milestone: str) -> NoReturn:
    raise HTTPException(
        status_code=501,
        detail={"error": "not_implemented", "milestone": milestone},
    )


def create_app() -> FastAPI:
    """构造应用实例。测试用工厂，生产用模块级 ``app``。"""
    application = FastAPI(
        title="SnowFoxClaw",
        version=__version__,
        description="个人 Agent 智能体，住在你设备里的狐狸。仅监听 127.0.0.1，无鉴权。",
        servers=[{"url": "http://127.0.0.1:8765", "description": "本地回环地址"}],
    )

    @application.get("/healthz", tags=["ops"], summary="存活检查")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    api = APIRouter(prefix="/v1")

    @api.post(
        "/chat",
        response_model=ChatResponse,
        responses=_STUB_RESPONSES,
        tags=["chat"],
        summary="发送一轮消息",
    )
    def chat(payload: ChatRequest) -> ChatResponse:
        _stub("W1-5")

    @api.get(
        "/persona",
        response_model=PersonaProfile,
        responses=_STUB_RESPONSES,
        tags=["persona"],
        summary="读取当前激活人格",
    )
    def get_persona() -> PersonaProfile:
        _stub("W1-1")

    @api.put(
        "/persona",
        response_model=PersonaProfile,
        responses=_STUB_RESPONSES,
        tags=["persona"],
        summary="更新人格并升版本",
    )
    def put_persona(payload: PersonaUpdate) -> PersonaProfile:
        _stub("W1-1")

    @api.get(
        "/preferences",
        response_model=PreferenceList,
        responses=_STUB_RESPONSES,
        tags=["preferences"],
        summary="列出偏好",
    )
    def list_preferences(domain: PreferenceDomain | None = None) -> PreferenceList:
        _stub("W1-2")

    @api.post(
        "/preferences",
        response_model=PreferenceItem,
        responses=_STUB_RESPONSES,
        tags=["preferences"],
        summary="新建偏好",
    )
    def create_preference(payload: PreferenceCreate) -> PreferenceItem:
        _stub("W1-2")

    @api.patch(
        "/preferences/{pref_id}",
        response_model=PreferenceItem,
        responses=_STUB_RESPONSES,
        tags=["preferences"],
        summary="修改偏好",
    )
    def patch_preference(pref_id: str, payload: PreferencePatch) -> PreferenceItem:
        _stub("W1-2")

    @api.delete(
        "/preferences/{pref_id}",
        responses=_STUB_RESPONSES,
        tags=["preferences"],
        summary="删除偏好",
    )
    def delete_preference(pref_id: str) -> None:
        _stub("W1-2")

    @api.get(
        "/memories",
        response_model=MemoryList,
        responses=_STUB_RESPONSES,
        tags=["memories"],
        summary="检索记忆",
    )
    def list_memories(
        query: Annotated[str | None, Query(max_length=500)] = None,
        memory_type: Annotated[MemoryType | None, Query(alias="type")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> MemoryList:
        _stub("W2-7")

    @api.delete(
        "/memories/{id}",
        responses=_STUB_RESPONSES,
        tags=["memories"],
        summary="删除记忆",
    )
    def delete_memory(id: str) -> None:
        _stub("W2-7")

    @api.get(
        "/sessions/{session_id}/context",
        response_model=WorkingContext,
        responses=_STUB_RESPONSES,
        tags=["context"],
        summary="读取工作上下文",
    )
    def get_context(session_id: str) -> WorkingContext:
        _stub("W2-5")

    @api.post(
        "/eval/run",
        response_model=EvalRunResponse,
        responses=_STUB_RESPONSES,
        tags=["eval"],
        summary="运行评估用例",
    )
    def run_eval(payload: EvalRunRequest) -> EvalRunResponse:
        _stub("W3-2")

    application.include_router(api)
    return application


app = create_app()
