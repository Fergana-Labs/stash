import base64
import json
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from PIL import Image

from backend.services import storage_service
from backend.services.rm.adapters import parse_traces
from backend.services.rm.trace_images import decode_image

from .test_rm_session_ingest import register, upload


@pytest.fixture
def image_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("STASH_TRACE_IMAGE_DIR", str(tmp_path))
    monkeypatch.setattr(storage_service, "is_configured", lambda: False)
    data = BytesIO()
    Image.new("RGB", (2, 3), "red").save(data, format="PNG")
    return data.getvalue()


def transcript(data):
    blocks = [
        {
            "type": "input_text",
            "text": 'Before 🐙\n<image name=[Image #1] path="/private/screenshot.png">',
        },
        {
            "type": "input_image",
            "image_url": "data:image/png;base64," + base64.b64encode(data).decode(),
        },
        {"type": "input_text", "text": "</image>\nPlease fix **this**."},
    ]
    records = [
        {"type": "session_meta", "payload": {"id": "session1"}},
        {
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": blocks},
        },
    ]
    return "\n".join(json.dumps(record) for record in records).encode()


async def test_images_are_private_lazy_and_shared_only_with_trace_reviewers(
    client, pool, image_storage
):
    auth, _ = await register(client)
    other_auth, other = await register(client)
    result = await upload(client, auth, transcript(image_storage))
    tid = result["trace"]["id"]
    detail = (await client.get(f"/api/v1/rm/traces/{tid}", headers=auth)).json()
    step = detail["steps"][0]
    image = step["images"][0]
    assert "base64" not in json.dumps(detail)
    assert image["width"] == 2 and image["height"] == 3
    assert "storage_key" not in image
    route = f"/api/v1/rm/trace-images/{image['id']}"
    assert (await client.get(route)).status_code == 401
    assert (await client.get(route, headers=other_auth)).status_code == 404
    response = await client.get(route, headers=auth)
    assert response.content == image_storage
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, no-cache"
    await pool.execute(
        "INSERT INTO rm_wb_trace_reviewers(trace_id,user_id) VALUES($1,$2)", UUID(tid), other
    )
    assert (await client.get(route, headers=other_auth)).content == image_storage
    await pool.execute("DELETE FROM rm_wb_trace_reviewers WHERE trace_id=$1", UUID(tid))
    assert (await client.get(route, headers=other_auth)).status_code == 404


async def test_repeat_upload_backfills_images_without_replacing_steps_or_comments(
    client, pool, image_storage
):
    auth, _ = await register(client)
    body = transcript(image_storage)
    tid = (await upload(client, auth, body))["trace"]["id"]
    url = f"/api/v1/rm/traces/{tid}"
    before = (await client.get(url, headers=auth)).json()
    step = before["steps"][0]
    timestamp = await pool.fetchval("SELECT updated_at FROM rm_traces WHERE id=$1", UUID(tid))
    assert (await upload(client, auth, body))["trace"]["appended"] == 0
    assert (await client.get(url, headers=auth)).json()["steps"][0] == step
    await client.post(
        f"{url}/annotations",
        headers=auth,
        json={"step_id": step["id"], "comment": "Keep this review"},
    )
    # Simulate a trace saved before images were preserved.
    await pool.execute("DELETE FROM rm_trace_images WHERE step_id=$1", UUID(step["id"]))
    assert (await upload(client, auth, body))["trace"]["appended"] == 0
    after = (await client.get(url, headers=auth)).json()
    assert after["steps"][0]["id"] == step["id"]
    assert after["steps"][0]["content"] == step["content"]
    assert len(after["steps"][0]["images"]) == 1
    assert after["annotations"][0]["comment"] == "Keep this review"
    assert (
        await pool.fetchval("SELECT updated_at FROM rm_traces WHERE id=$1", UUID(tid)) == timestamp
    )


async def test_private_storage_failure_keeps_transcript_and_retries_on_next_upload(
    client, monkeypatch, image_storage
):
    monkeypatch.setattr(storage_service, "is_configured", lambda: True)
    save = AsyncMock(side_effect=[httpx.ConnectError("Temporary outage"), "private/image"])
    read = AsyncMock(return_value=image_storage)
    monkeypatch.setattr(storage_service, "upload_file", save)
    monkeypatch.setattr(storage_service, "download_file", read)
    auth, owner = await register(client)
    body = transcript(image_storage)
    tid = (await upload(client, auth, body))["trace"]["id"]
    url = f"/api/v1/rm/traces/{tid}"
    before = (await client.get(url, headers=auth)).json()["steps"][0]
    assert before["images"] == [] and "Please fix" in before["content"]
    assert (await upload(client, auth, body))["trace"]["appended"] == 0
    after = (await client.get(url, headers=auth)).json()["steps"][0]
    assert after["id"] == before["id"]
    image = after["images"][0]
    assert (
        await client.get(f"/api/v1/rm/trace-images/{image['id']}", headers=auth)
    ).content == image_storage
    read.assert_awaited_once_with("private/image")
    assert save.await_args.args[0] == str(owner)
    assert save.await_args.args[2:] == (image_storage, "image/png")
    await upload(client, auth, body)
    assert save.await_count == 2


def test_images_preserve_wrapper_offsets_in_utf16_and_never_open_local_paths(image_storage):
    _, traces = parse_traces(transcript(image_storage).decode(), "codex")
    step = traces[0].steps[0]
    image = step.images[0]
    encoded = step.content.encode("utf-16-le")
    replaced = encoded[image.start * 2 : image.end * 2].decode("utf-16-le")
    assert (
        replaced
        == '<image name=[Image #1] path="/private/screenshot.png">\n[input_image]\n</image>'
    )
    assert step.content.endswith("Please fix **this**.")
    assert "base64" not in step.content


@pytest.mark.parametrize("payload", [b"<svg onload='alert(1)'/>", b"not an image"])
def test_non_raster_or_invalid_image_bytes_are_rejected(payload):
    assert decode_image("data:image/png;base64," + base64.b64encode(payload).decode()) is None
    assert decode_image("data:image/png;base64,not-base64") is None


def test_remote_and_local_image_urls_are_not_fetched():
    blocks = [
        {"type": "input_image", "image_url": url}
        for url in ("https://example.test/image.png", "file:///private/file.png")
    ]
    record = {
        "type": "response_item",
        "payload": {"type": "message", "role": "user", "content": blocks},
    }
    data = (
        json.dumps({"type": "session_meta", "payload": {"id": "remote"}})
        + "\n"
        + json.dumps(record)
    )
    _, traces = parse_traces(data, "codex")
    assert traces[0].steps[0].images == []


def test_anthropic_images_are_preserved_as_attachments(image_storage):
    data = json.dumps(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64.b64encode(image_storage).decode(),
                            },
                        }
                    ],
                }
            ]
        }
    )
    _, traces = parse_traces(data, "anthropic_messages")
    step = traces[0].steps[0]
    assert step.content == "[image]" and len(step.images) == 1
