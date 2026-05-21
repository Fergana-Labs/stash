from typer.testing import CliRunner

from cli.main import app


def test_root_command_without_args_shows_help() -> None:
    runner = CliRunner()

    result = runner.invoke(app, [])
    help_result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert result.output == help_result.output
