"""命令行入口。

子命令按里程碑逐步开放：``serve``（M0-8）、``chat`` 与 ``context``（W1-5 之后）。
无子命令时保持 0.1.0 的行为，仅打印版本。
"""

from __future__ import annotations

import argparse
import sys

from snowfoxclaw import __version__


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from snowfoxclaw.api.server import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level=args.log_level)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="foxclaw",
        description="SnowFoxClaw — 个人 Agent 智能体，住在你设备里的狐狸",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"snowfoxclaw {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    serve = subparsers.add_parser("serve", help="启动本地 HTTP 服务")
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="监听地址，默认仅回环地址（架构文档 6.2 约定）",
    )
    serve.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    serve.add_argument("--log-level", default="info", help="uvicorn 日志级别")
    serve.set_defaults(handler=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    handler = getattr(args, "handler", None)
    if handler is None:
        print(f"snowfoxclaw {__version__}")
        print("功能开发中，用 `foxclaw serve` 启动本地服务。")
        return 0
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
