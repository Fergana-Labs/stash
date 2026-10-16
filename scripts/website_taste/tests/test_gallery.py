import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from scripts.website_taste.gallery import agent_report, handler, instructions_for, snapshot


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_journal_keeps_order_method_identity_and_partial_results_without_private_data(tmp_path):
    write(
        tmp_path / "experiment.json",
        {
            "model": {"id": "Qwen/pinned"},
            "tasks": [{"id": "brief", "brief": "Build a library", "partition": "dev"}],
            "examples": [{"quote": "PRIVATE HISTORY"}],
        },
    )
    (tmp_path / "SKILL.md").write_text("PRIVATE BASELINE INSTRUCTIONS")
    ledger = [
        {
            "id": "a" * 64,
            "task": "brief",
            "arm": "gepa-search",
            "instructions": "PRIVATE BASELINE INSTRUCTIONS",
        },
        {
            "id": "b" * 64,
            "task": "brief",
            "arm": "gepa-search",
            "instructions": "PRIVATE CHANGED INSTRUCTIONS",
        },
        {
            "id": "c" * 64,
            "task": "brief",
            "arm": "dpo-sampling",
            "instructions": "PRIVATE BASELINE INSTRUCTIONS",
        },
    ]
    # A restart can append the same request; do not pretend its one saved output is two designs.
    (tmp_path / "trials.jsonl").write_text(
        "\n".join(json.dumps(r) for r in ledger + ledger[:1]) + '\n{"id":'
    )
    first = tmp_path / "artifacts" / ("a" * 64)
    write(
        first / "receipt.json",
        {"valid": True, "classifier_score": 0.72, "prediction": {"secret": "PRIVATE"}},
    )
    (first / "website.png").write_bytes(b"pixels")
    write(tmp_path / "artifacts" / ("b" * 64) / "receipt.json", {"valid": False, "score": 0})
    data = snapshot(tmp_path)
    assert [r["method"] for r in data["trials"]] == ["skill", "gepa", "sampling"]
    assert [r["status"] for r in data["trials"]] == ["scored", "invalid", "generating"]
    assert data["trials"][1]["score"] is None  # Invalid HTML is not an aesthetic judgment.
    assert data["trials"][2]["brief"] == "Build a library"
    assert "PRIVATE" not in json.dumps(data)
    write(
        tmp_path / "artifacts" / ("c" * 64) / "generation.json", {"usage": {"output_tokens": 1200}}
    )
    updated = snapshot(tmp_path)
    assert updated["revision"] != data["revision"]
    assert updated["trials"][2]["status"] == "rendering"


def test_gallery_serves_only_screenshots_and_handles_symlink_escape(tmp_path):
    root, outside = tmp_path / "run", tmp_path / "outside"
    root.mkdir()
    write(root / "auth.json", {"api_key": "PRIVATE CREDENTIAL"})
    safe = root / "artifacts" / ("a" * 64)
    safe.mkdir(parents=True)
    (safe / "website.png").write_bytes(b"saved pixels")
    outside.mkdir()
    (outside / "website.png").write_bytes(b"PRIVATE PIXELS")
    (root / "artifacts" / ("b" * 64)).symlink_to(outside, target_is_directory=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(root))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/images/" + "a" * 64 + ".png") as response:
            assert response.read() == b"saved pixels"
            assert response.headers["Content-Type"] == "image/png"
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        for path in (
            "/auth.json",
            "/experiment.json",
            "/images/../auth.json",
            "/images/" + "b" * 64 + ".png",
        ):
            with pytest.raises(HTTPError) as error:
                urlopen(base + path)
            assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_exact_skill_diff_and_judge_report_bind_to_saved_trial(tmp_path):
    identity = "a" * 64
    write(
        tmp_path / "experiment.json",
        {
            "system": "Fixed instructions",
            "tasks": [{"id": "brief", "brief": "Same website prompt"}],
        },
    )
    (tmp_path / "SKILL.md").write_text("Starting skill")
    (tmp_path / "trials.jsonl").write_text(
        json.dumps({"id": identity, "instructions": "Revised skill", "task": "brief", "seed": 713})
        + "\n"
    )
    result = instructions_for(tmp_path, identity)
    assert result["brief"] == "Same website prompt" and result["seed"] == 713
    assert result["skill"] == "Revised skill" and not result["isBaseline"]
    assert "-Starting skill" in result["changes"] and "+Revised skill" in result["changes"]
    assert instructions_for(tmp_path, "../auth") is None
    before = snapshot(tmp_path)
    write(tmp_path / "pilot-invalidated.json", {"reason": "Human rejection"})
    (tmp_path / "human-feedback.jsonl").write_text(
        json.dumps({"trial_id": identity, "label": "disliked"}) + '\n{"partial":'
    )
    write(
        tmp_path / "agent-judge" / identity / "latest.json",
        {"fingerprint": "new", "validated": False},
    )
    after = snapshot(tmp_path)
    assert after["invalidated"] and after["trials"][0]["humanLabel"] == "disliked"
    assert before["revision"] != after["revision"]
    assert agent_report(tmp_path, identity)["validated"] is False
