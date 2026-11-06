"""本地 HTTP 服务（M0-8 空壳）。

第一阶段只暴露 ``/healthz``，用于验证服务骨架与依赖可用。
业务接口在 W1-5 之后逐步挂载，路由定义见 ``docs/architecture.md`` 6.2。
"""

from __future__ import annotations

from fastapi import FastAPI

from snowfoxclaw import __version__

__all__ = ["create_app", "app"]


def create_app() -> FastAPI:
    """构造应用实例。测试用工厂，生产用模块级 ``app``。"""
    application = FastAPI(
        title="SnowFoxClaw",
        version=__version__,
        description="个人 Agent 智能体，住在你设备里的狐狸",
    )

    @application.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return application


app = create_app()
