"""`stash sql` renders the endpoint's result as an aligned text table —
the output agents read — and passes the raw payload through under --json."""

from __future__ import annotations

import json
from unittest import mock

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()

RESULT = {
    "columns": [{"name": "Company", "type": "VARCHAR"}, {"name": "Salary", "type": "DOUBLE"}],
    "rows": [["Acme", 90000.0], ["Globex", None]],
    "row_count": 2,
    "truncated": False,
}


def test_sql_renders_aligned_rows() -> None:
    with mock.patch("cli.main._client") as client_factory:
        client = client_factory.return_value.__enter__.return_value
        client.run_sql.return_value = RESULT
        result = runner.invoke(app, ["sql", "SELECT * FROM jobs"])

    assert result.exit_code == 0
    client.run_sql.assert_called_once_with("SELECT * FROM jobs")
    lines = result.output.splitlines()
    assert lines[0].split(" | ") == ["Company", "Salary "]
    assert "Acme" in lines[2] and "90000.0" in lines[2]
    # NULL renders as empty, not the string "None".
    assert "None" not in lines[3]
    assert "(2 rows)" in result.output


def test_sql_json_passes_payload_through() -> None:
    with mock.patch("cli.main._client") as client_factory:
        client = client_factory.return_value.__enter__.return_value
        client.run_sql.return_value = RESULT
        result = runner.invoke(app, ["sql", "SELECT 1", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == RESULT
