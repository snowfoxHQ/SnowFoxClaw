"""SnowFoxClaw — 个人 Agent 智能体，住在你设备里的狐狸。"""

__all__ = ["__version__", "main"]

__version__ = "0.1.0"


def main() -> int:
    """包级入口的轻量转发，指向 :func:`snowfoxclaw.cli.main`。"""
    from snowfoxclaw.cli import main as _main

    return _main()
