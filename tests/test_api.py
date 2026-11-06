"""M0-8 服务骨架测试。"""

from fastapi.testclient import TestClient

import snowfoxclaw
from snowfoxclaw.api.server import create_app
from snowfoxclaw.cli import build_parser


def test_healthz():
    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": snowfoxclaw.__version__}


def test_serve_defaults_to_loopback():
    args = build_parser().parse_args(["serve"])
    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert callable(args.handler)


def test_no_subcommand_keeps_version_banner(capsys):
    from snowfoxclaw.cli import main

    assert main([]) == 0
    assert f"snowfoxclaw {snowfoxclaw.__version__}" in capsys.readouterr().out
