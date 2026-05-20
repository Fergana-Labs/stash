from __future__ import annotations

from cli import main
from stashai.plugin.upload_status import record_upload_failure, record_upload_success


def test_upload_health_snapshot_reads_local_plugin_status(monkeypatch, tmp_path):
    record_upload_failure(tmp_path, "event", "401 Unauthorized")
    monkeypatch.setattr(main, "PLUGIN_DATA_DIRS", {"codex": tmp_path})

    snapshot = main._upload_health_snapshot()

    assert snapshot[0]["agent"] == "codex"
    assert snapshot[0]["label"] == "Codex"
    assert snapshot[0]["health"] == "failing"
    assert snapshot[0]["last_error"] == "401 Unauthorized"


def test_upload_health_label_prefers_queued_failures(monkeypatch, tmp_path):
    record_upload_success(tmp_path, "event")
    (tmp_path / "event_queue.jsonl").write_text("{}\n{}\n")
    monkeypatch.setattr(main, "PLUGIN_DATA_DIRS", {"codex": tmp_path})

    assert main._upload_health_label(main._upload_health_snapshot()) == "Codex failing, 2 queued"


def test_single_failure_is_reported_as_failing(monkeypatch, tmp_path):
    record_upload_failure(tmp_path, "event", "temporary outage")
    monkeypatch.setattr(main, "PLUGIN_DATA_DIRS", {"codex": tmp_path})

    snapshot = main._upload_health_snapshot()

    assert snapshot[0]["health"] == "failing"
    assert main._failing_upload_agents(snapshot) == snapshot
