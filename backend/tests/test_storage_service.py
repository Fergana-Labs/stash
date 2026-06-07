from backend.services import storage_service


def test_object_uri_encodes_key_path_segments(monkeypatch):
    monkeypatch.setattr(storage_service, "S3_BUCKET", "stash")

    uri = storage_service._object_uri("workspace/abc123/Screen Shot #1.png")

    assert uri == "/stash/workspace/abc123/Screen%20Shot%20%231.png"


async def test_presigned_file_url_encodes_key(monkeypatch):
    monkeypatch.setattr(storage_service, "S3_BUCKET", "stash")
    monkeypatch.setattr(storage_service, "S3_ENDPOINT", "https://r2.example.com")
    monkeypatch.setattr(storage_service, "S3_ACCESS_KEY", "access")
    monkeypatch.setattr(storage_service, "S3_SECRET_KEY", "secret")
    monkeypatch.setattr(storage_service, "S3_REGION", "auto")

    url = await storage_service.get_file_url(
        "workspace/abc123/Screen Shot #1.png",
        expires_in=300,
    )

    assert url.startswith("https://r2.example.com/stash/workspace/abc123/Screen%20Shot%20%231.png?")
    assert "X-Amz-Expires=300" in url
    assert "X-Amz-Signature=" in url
