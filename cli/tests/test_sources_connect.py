"""`stash sources connect` is the OAuth-grant step that `sources add` depends
on. The consent itself is the user's (password + 2FA), so the command's whole
job is the handoff: surface the URL, then watch the provider's account list
until the grant lands. These lock in what "landed" means — including the
reconnect case, where the account key is unchanged and only the timestamp
moves — and that a consent that never completes fails loudly instead of
reporting a connection that does not exist.
"""

import json
import time
import webbrowser

import pytest
import typer

from cli import main


class _FakeClient:
    """Serves a scripted status per call: the first is the baseline read the
    command takes before opening the browser, the rest are polls. The last
    entry repeats, which is what an abandoned consent looks like."""

    def __init__(self, statuses: list[dict], calls: list):
        self._statuses = statuses
        self._reads = 0
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def integration_status(self, provider):
        self._calls.append(("status", provider))
        status = self._statuses[min(self._reads, len(self._statuses) - 1)]
        self._reads += 1
        return status

    def integration_authorize_url(self, provider):
        self._calls.append(("authorize_url", provider))
        return f"https://accounts.example.com/o/oauth2/auth?provider={provider}"


def _account(key: str, updated_at: str, **overrides) -> dict:
    account = {
        "account_key": key,
        "account_email": key,
        "account_display_name": None,
        "disconnected": False,
        "updated_at": updated_at,
    }
    account.update(overrides)
    return account


def _wire(monkeypatch, statuses: list[dict], opened: bool = True) -> list:
    """The command imports time/webbrowser inside its body, so the patches go
    on the real modules. sleep drives a fake clock so a timeout costs no wall
    time and lands on an exact number of polls."""
    calls: list = []
    now = {"t": 0.0}
    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_client", lambda: _FakeClient(statuses, calls))
    monkeypatch.setattr(main, "_refocus_terminal", lambda: None)
    monkeypatch.setattr(main, "_is_ssh", lambda: False)
    monkeypatch.setattr(webbrowser, "open", lambda _url: opened)
    monkeypatch.setattr(time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(time, "sleep", lambda s: now.__setitem__("t", now["t"] + s))
    return calls


def test_connect_waits_for_a_new_account_then_reports_it(monkeypatch, capsys) -> None:
    """The grant appears only after the user finishes in the browser, so the
    command must keep polling past an unchanged status rather than declaring
    victory on the first read."""
    existing = _account("henry@ferganalabs.com", "2026-08-01T00:00:00+00:00")
    arrived = _account("htdowling@gmail.com", "2026-08-11T12:00:00+00:00")
    calls = _wire(
        monkeypatch,
        [
            {"accounts": [existing]},  # baseline, before the browser opens
            {"accounts": [existing]},  # still mid-consent
            {"accounts": [existing, arrived]},
        ],
    )

    main.sources_connect("gmail", timeout=60, as_json=False)

    out = capsys.readouterr().out
    assert "htdowling@gmail.com" in out
    assert "stash sources add" in out  # the next step is spelled out
    assert calls.count(("status", "gmail")) == 3


def test_connect_reports_only_the_account_that_just_arrived(monkeypatch, capsys) -> None:
    """Mailboxes authorized on earlier runs are not news. Reporting them again
    would tell the user they just connected an account they already had."""
    existing = _account("henry@ferganalabs.com", "2026-08-01T00:00:00+00:00")
    arrived = _account("htdowling@gmail.com", "2026-08-11T12:00:00+00:00")
    _wire(monkeypatch, [{"accounts": [existing]}, {"accounts": [existing, arrived]}])

    main.sources_connect("gmail", timeout=60, as_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert [a["account_key"] for a in payload["accounts"]] == ["htdowling@gmail.com"]


def test_connect_detects_a_reconnect_of_an_existing_account(monkeypatch, capsys) -> None:
    """Repairing an expired grant reuses the same account_key, so a key-only
    comparison would poll forever through a consent that actually succeeded.
    The moved updated_at is what makes the repair visible."""
    stale = _account("henry@ferganalabs.com", "2026-08-01T00:00:00+00:00")
    repaired = _account("henry@ferganalabs.com", "2026-08-11T12:00:00+00:00")
    _wire(monkeypatch, [{"accounts": [stale]}, {"accounts": [repaired]}])

    main.sources_connect("gmail", timeout=60, as_json=False)

    assert "henry@ferganalabs.com" in capsys.readouterr().out


def test_connect_ignores_a_disconnected_account(monkeypatch) -> None:
    """A disconnected row keeps its key and timestamp but holds no token, so
    counting it as a grant would report success for an unusable account."""
    revoked = _account("henry@ferganalabs.com", "2026-08-11T12:00:00+00:00", disconnected=True)
    _wire(monkeypatch, [{"accounts": []}, {"accounts": [revoked]}])

    with pytest.raises(typer.Exit) as exc:
        main.sources_connect("gmail", timeout=4, as_json=False)

    assert exc.value.exit_code == 1


def test_connect_fails_loudly_when_consent_never_completes(monkeypatch, capsys) -> None:
    """An abandoned consent must exit non-zero: a caller that took silence for
    success would go on to `sources add` against a grant that isn't there."""
    existing = _account("henry@ferganalabs.com", "2026-08-01T00:00:00+00:00")
    _wire(monkeypatch, [{"accounts": [existing]}])

    with pytest.raises(typer.Exit) as exc:
        main.sources_connect("gmail", timeout=4, as_json=False)

    assert exc.value.exit_code == 1
    assert "Timed out" in capsys.readouterr().out


def test_connect_prints_the_url_when_the_browser_cannot_open(monkeypatch, capsys) -> None:
    """Headless and SSH sessions have no local browser; the URL is the only
    way the user can complete the step, so it has to be visible."""
    existing = _account("henry@ferganalabs.com", "2026-08-01T00:00:00+00:00")
    arrived = _account("htdowling@gmail.com", "2026-08-11T12:00:00+00:00")
    _wire(
        monkeypatch,
        [{"accounts": [existing]}, {"accounts": [existing, arrived]}],
        opened=False,
    )

    main.sources_connect("gmail", timeout=60, as_json=False)

    assert "accounts.example.com" in capsys.readouterr().out


def test_connect_json_keeps_stdout_parseable(monkeypatch, capsys) -> None:
    """Agents consume --json on stdout. The authorize URL still has to reach a
    human, so it goes to stderr where it cannot corrupt the payload."""
    existing = _account("henry@ferganalabs.com", "2026-08-01T00:00:00+00:00")
    arrived = _account("htdowling@gmail.com", "2026-08-11T12:00:00+00:00")
    _wire(monkeypatch, [{"accounts": [existing]}, {"accounts": [existing, arrived]}])

    main.sources_connect("gmail", timeout=60, as_json=True)

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["provider"] == "gmail"
    assert "accounts.example.com" in captured.err
