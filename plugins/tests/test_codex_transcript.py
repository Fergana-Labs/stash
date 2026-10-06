"""Realistic resumed Codex histories must include their exact earlier prefix."""

import gzip
import json

import httpx
import pytest

from cli.client import StashClient as CLIClient
from cli.client import StashError
from stashai.plugin.codex_transcript import read_transcript
from stashai.plugin.stash_client import StashClient as HookClient
from stashai.plugin.upload_status import read_upload_status

THREAD = "11111111-1111-4111-8111-111111111111"
FORK = "22222222-2222-4222-8222-222222222222"


def page(tmp_path, name, messages, *, start=0, base=None, thread=THREAD):
    path = tmp_path / "sessions" / "2026" / "10" / "05" / f"{thread}_{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"id": thread}
    if base:
        meta["history_base"] = base
    records = [{"type": "session_meta", "payload": meta, "ordinal": start}]
    records += [
        {
            "type": "response_item",
            "ordinal": i,
            "payload": {"type": "message", "role": "user", "content": text},
        }
        for i, text in enumerate(messages, start=start + 1)
    ]
    path.write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in records))
    return path


def boundary(path, end):
    records = path.read_bytes().splitlines(keepends=True)
    return {
        "thread_id": THREAD,
        "end_ordinal_exclusive": end,
        "end_byte_offset": len(b"".join(records)),
    }


def records(raw):
    return [json.loads(line) for line in raw.split(b"\n") if line]


def test_resumed_history_uses_exact_prefix_and_current_identity(tmp_path):
    original = page(tmp_path, "original", ["Fix bug", "Ran tests"])
    base = boundary(original, 3)
    with original.open("ab") as f:
        f.write(
            json.dumps(
                {"ordinal": 3, "type": "response_item", "payload": {"content": "abandoned"}}
            ).encode()
            + b"\n"
        )
    resumed = page(tmp_path, "resumed", ["Continue", "Fixed"], start=3, base=base, thread=FORK)
    rows = records(read_transcript(resumed))
    assert rows[0]["payload"]["id"] == FORK
    assert "history_base" not in rows[0]["payload"]
    assert [r["payload"]["content"] for r in rows[1:]] == [
        "Fix bug",
        "Ran tests",
        "Continue",
        "Fixed",
    ]
    assert "history_base" in records(resumed.read_bytes())[0]["payload"]


def test_resolves_multiple_pages_and_archived_bases(tmp_path):
    original = page(tmp_path, "original", ["First"])
    second = page(tmp_path, "second", ["Second"], start=2, base=boundary(original, 2))
    third = page(tmp_path, "third", ["Third"], start=4, base=boundary(second, 4))
    archive = tmp_path / "archived_sessions"
    archive.mkdir()
    original.rename(archive / original.name)
    rows = records(read_transcript(third))
    assert [r["payload"]["content"] for r in rows[1:]] == ["First", "Second", "Third"]


@pytest.mark.parametrize("failure", ["missing", "bad_boundary", "ambiguous"])
def test_unresolvable_base_fails_instead_of_uploading_partial_history(tmp_path, failure):
    original = page(tmp_path, "original", ["First"])
    base = boundary(original, 2)
    resumed = page(tmp_path, "resumed", ["Second"], start=2, base=base)
    if failure == "missing":
        original.unlink()
    elif failure == "bad_boundary":
        original.write_bytes(original.read_bytes().replace(b'"ordinal": 1', b'"ordinal": 9'))
    else:
        page(tmp_path, "conflicting", ["Other"])
    with pytest.raises(ValueError, match="history_base"):
        read_transcript(resumed)


@pytest.mark.parametrize("client_class", [CLIClient, HookClient])
def test_both_upload_clients_send_reconstructed_history(tmp_path, monkeypatch, client_class):
    original = page(tmp_path, "original", ["Prompt"])
    resumed = page(tmp_path, "resumed", ["Answer"], start=2, base=boundary(original, 2))
    with client_class("https://example.test", api_key="test") as client:

        def request(method, path, **kwargs):
            body = gzip.decompress(kwargs["files"]["file"][1])
            assert [r["payload"]["content"] for r in records(body)[1:]] == ["Prompt", "Answer"]
            return httpx.Response(201, json={"trace": {"id": "trace1", "appended": 2}})

        monkeypatch.setattr(client._http, "request", request)
        assert client.upload_transcript(THREAD, resumed, "codex")["trace"]["appended"] == 2


def test_trace_sync_error_is_visible_in_hook_upload_health(tmp_path, monkeypatch):
    path = page(tmp_path, "original", ["Prompt"])
    with HookClient("https://example.test", api_key="test", data_dir=tmp_path) as client:
        monkeypatch.setattr(
            client._http,
            "request",
            lambda *a, **k: httpx.Response(201, json={"trace_sync_error": "Conflicting snapshot"}),
        )
        with pytest.raises(ValueError, match="Trace sync failed"):
            client.upload_transcript(THREAD, path, "codex")
    status = read_upload_status(tmp_path)
    assert status["health"] == "failing"
    assert "Conflicting snapshot" in status["last_error"]


def test_cli_import_can_report_unresolvable_history_and_trace_errors(tmp_path, monkeypatch):
    original = page(tmp_path, "original", ["Prompt"])
    resumed = page(tmp_path, "resumed", ["Answer"], start=2, base=boundary(original, 2))
    original.unlink()
    with CLIClient("https://example.test", api_key="test") as client:
        with pytest.raises(StashError, match="Missing Codex history_base"):
            client.upload_transcript(THREAD, resumed, "codex")
        original = page(tmp_path, "original", ["Prompt"])
        monkeypatch.setattr(
            client._http,
            "request",
            lambda *a, **k: httpx.Response(201, json={"trace_sync_error": "Conflicting snapshot"}),
        )
        with pytest.raises(StashError, match="Trace sync failed"):
            client.upload_transcript(THREAD, original, "codex")


def test_ordinary_transcript_is_unchanged(tmp_path):
    path = tmp_path / "claude.jsonl"
    raw = b'{"type":"user","message":{"content":"hello"}}\n'
    path.write_bytes(raw)
    assert read_transcript(path) == raw
