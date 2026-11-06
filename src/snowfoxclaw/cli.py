"""命令行入口（占位实现）。

0.1.0 只用于在 PyPI 上占位，安装后执行 ``foxclaw`` 能看到版本号即可。
"""

from __future__ import annotations

import argparse
import sys

from snowfoxclaw import __version__


def main(argv: list[str] | None = None) -> int:
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
    parser.parse_args(argv)

    print(f"snowfoxclaw {__version__}")
    print("占位版本（0.1.0），功能正在开发中。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
