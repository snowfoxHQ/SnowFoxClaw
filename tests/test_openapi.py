"""M0-4：OpenAPI 契约与路由桩。

契约文件由 ``foxclaw openapi`` 从应用生成，这里做三件事：
防止文件和实现漂移、钉住架构 6.2 要求的最小接口面、确认桩不允许被当成可用接口。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

import snowfoxclaw
from snowfoxclaw.api.server import create_app
from snowfoxclaw.cli import main

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "api" / "openapi.yaml"
SCHEMA_DIR = ROOT / "src" / "snowfoxclaw" / "schema"

REQUIRED_ENDPOINTS = {
    ("/healthz", "get"),
    ("/v1/chat", "post"),
    ("/v1/persona", "get"),
    ("/v1/persona", "put"),
    ("/v1/preferences", "get"),
    ("/v1/preferences", "post"),
    ("/v1/preferences/{pref_id}", "patch"),
    ("/v1/preferences/{pref_id}", "delete"),
    ("/v1/memories", "get"),
    ("/v1/memories/{id}", "delete"),
    ("/v1/sessions/{session_id}/context", "get"),
    ("/v1/eval/run", "post"),
}

STUBS: list[tuple[str, str, dict[str, Any] | None]] = [
    ("post", "/v1/chat", {"session_id": "sess_abc123", "message": "你好"}),
    ("get", "/v1/persona", None),
    ("put", "/v1/persona", {"display_name": "小狐", "tone": "直接"}),
    ("get", "/v1/preferences", None),
    (
        "post",
        "/v1/preferences",
        {"domain": "schedule", "key": "提醒时间", "value": "早上八点"},
    ),
    ("patch", "/v1/preferences/pref_abc123", {"value": "早上九点"}),
    ("delete", "/v1/preferences/pref_abc123", None),
    ("get", "/v1/memories", None),
    ("delete", "/v1/memories/mem_abc123", None),
    ("get", "/v1/sessions/sess_abc123/context", None),
    ("post", "/v1/eval/run", {}),
]


def load_contract() -> dict[str, Any]:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def test_contract_matches_running_app():
    """契约文件必须等于应用当前导出的文档，改了路由就得重新导出。"""
    assert load_contract() == create_app().openapi()


def test_contract_declares_required_endpoints():
    paths = load_contract()["paths"]
    declared = {(path, method) for path, operations in paths.items() for method in operations}
    assert REQUIRED_ENDPOINTS <= declared


def test_contract_version_matches_package():
    contract = load_contract()
    assert contract["openapi"].startswith("3.1")
    assert contract["info"]["version"] == snowfoxclaw.__version__


def test_contract_only_exposes_loopback():
    """架构 6.2：服务只监听 127.0.0.1，第一阶段不支持对外暴露。"""
    urls = [server["url"] for server in load_contract()["servers"]]
    assert urls == ["http://127.0.0.1:8765"]


def test_every_operation_is_documented():
    paths = load_contract()["paths"]
    for path, operations in paths.items():
        for method, operation in operations.items():
            label = f"{method.upper()} {path}"
            assert operation.get("operationId"), f"{label} 缺少 operationId"
            assert operation.get("summary"), f"{label} 缺少 summary"
            assert operation.get("tags"), f"{label} 缺少 tags"
            assert "200" in operation["responses"], f"{label} 缺少 200 响应"


@pytest.mark.parametrize(("method", "path", "payload"), STUBS)
def test_business_endpoints_are_explicit_stubs(
    method: str, path: str, payload: dict[str, Any] | None
):
    with TestClient(create_app()) as client:
        response = client.request(method.upper(), path, json=payload)

    assert response.status_code == 501
    detail = response.json()["detail"]
    assert detail["error"] == "not_implemented"
    assert detail["milestone"]


@pytest.mark.parametrize(
    ("schema_file", "model_name"),
    [
        ("persona.json", "PersonaProfile"),
        ("preference.json", "PreferenceItem"),
        ("episodic.json", "MemoryItem"),
        ("working_context.json", "WorkingContext"),
    ],
)
def test_api_models_cover_schema_required_fields(schema_file: str, model_name: str):
    """schema 里必填的字段，API 响应模型也必须必填，否则契约对外漏字段。"""
    schema = json.loads((SCHEMA_DIR / schema_file).read_text(encoding="utf-8"))
    model = load_contract()["components"]["schemas"][model_name]

    schema_required = set(schema["required"])
    model_required = set(model.get("required", []))
    assert schema_required <= model_required, (
        f"{model_name} 缺少必填字段：{sorted(schema_required - model_required)}"
    )


def test_cli_writes_contract(tmp_path: Path):
    target = tmp_path / "openapi.yaml"
    assert main(["openapi", "--out", str(target)]) == 0
    assert yaml.safe_load(target.read_text(encoding="utf-8")) == create_app().openapi()
