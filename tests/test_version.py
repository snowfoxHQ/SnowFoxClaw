import snowfoxclaw
from snowfoxclaw.cli import main


def test_version():
    assert snowfoxclaw.__version__ == "0.1.0"


def test_cli_runs(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "snowfoxclaw 0.1.0" in out
