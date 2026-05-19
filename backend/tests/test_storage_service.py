from backend.services import storage_service


def test_object_uri_encodes_key_path_segments(monkeypatch):
    monkeypatch.setattr(storage_service, "S3_BUCKET", "stash")

    uri = storage_service._object_uri("workspace/abc123/Screen Shot #1.png")

    assert uri == "/stash/workspace/abc123/Screen%20Shot%20%231.png"


async def test_public_file_url_encodes_key(monkeypatch):
    monkeypatch.setattr(storage_service, "S3_PUBLIC_URL", "http://localhost:9000/stash")

    url = await storage_service.get_file_url("workspace/abc123/Screen Shot #1.png")

    assert url == "http://localhost:9000/stash/workspace/abc123/Screen%20Shot%20%231.png"
