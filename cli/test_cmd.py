"""`stash test`: regression-test an agent against a test set, from a terminal or CI.

    stash test run "Support regressions" --command "python agent.py"

runs the command once per case with the case's input on stdin (plain text, or
JSON messages when the case is a conversation), takes stdout as the agent's
answer, uploads the answers as a run, waits for scoring, prints what broke and
what got fixed against the baseline, and exits 1 when the run fails the set's
gate -- so a CI step fails on a regression.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import typer
from rich.table import Table

from .client import StashClient, StashError
from .config import load_config
from .formatting import console, output_json

test_app = typer.Typer(help="Regression-test your agent against a test set.", no_args_is_help=True)

POLL_SECONDS = 2
PASS, FAIL, ERROR = 0, 1, 2


def _client() -> StashClient:
    cfg = load_config()
    return StashClient(
        base_url=cfg["base_url"], api_key=cfg.get("api_key", ""), scope=cfg.get("scope", "")
    )


def _fail(message: str) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(ERROR)


def _resolve(c: StashClient, ref: str) -> dict:
    try:
        return c._get(f"/api/v1/test-sets/resolve/{ref}")
    except StashError as e:
        _fail(str(e))


def _stdin_for(case_input) -> tuple[str, str]:
    if isinstance(case_input, str):
        return case_input, "text"
    return json.dumps(case_input), "messages"


def _run_case(command: str, case: dict, timeout: int) -> str:
    stdin, fmt = _stdin_for(case["input"])
    env = {
        **os.environ,
        "STASH_TEST_CASE_ID": str(case["id"]),
        "STASH_TEST_CASE_NAME": case.get("name") or "",
        "STASH_TEST_INPUT_FORMAT": fmt,
    }
    try:
        done = subprocess.run(
            command,
            shell=True,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return f"[the command timed out after {timeout}s]"
    if done.returncode != 0:
        return f"[the command exited {done.returncode}]\n{done.stderr[-2000:]}"
    return done.stdout.strip()


def _wait(c: StashClient, run_id: str) -> dict:
    while True:
        run = c._get(f"/api/v1/test-sets/runs/{run_id}")
        if run["status"] != "scoring":
            return run
        time.sleep(POLL_SECONDS)


def _report(run: dict, as_json: bool) -> int:
    summary = run.get("summary") or {}
    if as_json:
        output_json(run)
    if run["status"] == "failed":
        if not as_json:
            console.print(f"[red]Scoring failed: {run.get('error')}[/red]")
        return ERROR
    names = {str(r["case_id"]): r["case_name"] or str(r["case_id"])[:8] for r in run["results"]}
    if not as_json:
        rate = summary.get("pass_rate")
        base = (summary.get("baseline") or {}).get("pass_rate")
        line = (
            f"[bold]{summary.get('passed')}/{summary.get('cases')} passed[/bold] ({rate:.0%})"
            if rate is not None
            else "no cases"
        )
        if base is not None:
            line += f"  ·  baseline {base:.0%}"
        console.print(line)
        for title, key, style in (("Broke", "broke", "red"), ("Fixed", "fixed", "green")):
            if summary.get(key):
                table = Table(
                    title=f"{title} ({len(summary[key])})",
                    title_style=style,
                    show_header=False,
                    box=None,
                )
                for cid in summary[key]:
                    result = next(r for r in run["results"] if str(r["case_id"]) == cid)
                    why = (
                        "; ".join(s["reason"] for s in result["scores"] if not s["passed"])
                        or result.get("error")
                        or ""
                    )
                    table.add_row(f"[{style}]•[/{style}] {names[cid]}", f"[dim]{why}[/dim]")
                console.print(table)
        failing = [
            r
            for r in run["results"]
            if not r["passed"] and str(r["case_id"]) not in set(summary.get("broke", []))
        ]
        if failing:
            console.print(
                f"[dim]{len(failing)} other failing case(s) also failed in the baseline or are new.[/dim]"
            )
        verdict = summary.get("gate")
        console.print(
            "[green]Gate: pass[/green]"
            if verdict == "pass"
            else "[red]Gate: fail — cases regressed[/red]"
        )
    return PASS if summary.get("gate") == "pass" else FAIL


@test_app.command("list")
def list_sets(as_json: bool = typer.Option(False, "--json")):
    """List your test sets."""
    with _client() as c:
        try:
            sets = c._get("/api/v1/test-sets")["test_sets"]
        except StashError as e:
            _fail(str(e))
    if as_json:
        output_json({"test_sets": sets})
        return
    if not sets:
        console.print('[dim]No test sets yet. `stash test create "<name>"` starts one.[/dim]')
    for s in sets:
        last = s.get("last_run") or {}
        rate = (last.get("summary") or {}).get("pass_rate")
        console.print(
            f"  [bold]{s['name']}[/bold]  [dim]{s['case_count']} cases{f' · last run {rate:.0%}' if rate is not None else ''}[/dim]"
        )


@test_app.command("create")
def create(
    name: str,
    expected: bool = typer.Option(True, help="Score answers against each case's expected answer."),
):
    """Create a test set (scored against expected answers by default)."""
    with _client() as c:
        try:
            s = c._post(
                "/api/v1/test-sets",
                json={"name": name, "scorers": [{"type": "expected"}] if expected else None},
            )
        except StashError as e:
            _fail(str(e))
    console.print(f"Created test set [bold]{s['name']}[/bold] ({s['id']})")


@test_app.command("add")
def add(
    test_set: str,
    file: Path = typer.Option(
        ..., "--file", help='JSONL: {"input": ..., "expected": ..., "name": ...} per line'
    ),
):
    """Add cases from a JSONL file."""
    cases = [json.loads(line) for line in file.read_text().splitlines() if line.strip()]
    with _client() as c:
        s = _resolve(c, test_set)
        try:
            added = c._post(f"/api/v1/test-sets/{s['id']}/cases", json={"cases": cases})["cases"]
        except StashError as e:
            _fail(str(e))
    console.print(f"Added {len(added)} case(s) to [bold]{s['name']}[/bold]")


@test_app.command("run")
def run(
    test_set: str,
    command: str = typer.Option(
        ..., "--command", "-c", help="Runs once per case: input on stdin, answer on stdout."
    ),
    label: str = typer.Option("", "--label", help="Name this run, e.g. a commit or version."),
    baseline: str = typer.Option(
        "",
        "--baseline",
        help="Run id to compare against (default: the set's baseline, else the last run).",
    ),
    timeout: int = typer.Option(300, "--timeout", help="Seconds per case."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Run your agent on every case, score it, and compare with the baseline. Exits 1 on a regression."""
    with _client() as c:
        s = _resolve(c, test_set)
        outputs = []
        for i, case in enumerate(s["cases"], 1):
            if not as_json:
                console.print(f"[dim]{i}/{len(s['cases'])} {case.get('name') or case['id']}[/dim]")
            outputs.append({"case_id": case["id"], "output": _run_case(command, case, timeout)})
        if not outputs:
            _fail("This test set has no cases")
        body = {"label": label or os.environ.get("GITHUB_SHA", "")[:12], "outputs": outputs}
        if baseline:
            body["baseline_run_id"] = baseline
        try:
            started = c._post(f"/api/v1/test-sets/{s['id']}/runs", json=body)
            result = _wait(c, started["id"])
        except StashError as e:
            _fail(str(e))
    raise typer.Exit(_report(result, as_json))


@test_app.command("submit")
def submit(
    test_set: str,
    outputs: Path = typer.Option(
        ..., "--outputs", help='JSONL: {"case_id" or "case_name", "output", "trace_id"?} per line'
    ),
    label: str = typer.Option("", "--label"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Score outputs your own harness produced. Exits 1 on a regression."""
    rows = [json.loads(line) for line in outputs.read_text().splitlines() if line.strip()]
    with _client() as c:
        s = _resolve(c, test_set)
        try:
            started = c._post(
                f"/api/v1/test-sets/{s['id']}/runs", json={"label": label, "outputs": rows}
            )
            result = _wait(c, started["id"])
        except StashError as e:
            _fail(str(e))
    raise typer.Exit(_report(result, as_json))
