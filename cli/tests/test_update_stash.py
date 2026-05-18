from cli.client import StashClient


def _stub_client():
    client = StashClient.__new__(StashClient)
    calls: list[tuple[str, dict]] = []

    def fake_patch(path: str, json=None) -> dict:
        body = json or {}
        calls.append((path, body))
        if path.endswith("/share"):
            return {
                "stash": {
                    "id": "stash-1",
                    "access": body.get("access", "workspace"),
                    "discoverable": body.get("discoverable", False),
                }
            }
        return {"id": "stash-1", **body}

    client._patch = fake_patch  # type: ignore[method-assign]
    return client, calls


def test_update_stash_metadata_uses_stash_endpoint() -> None:
    client, calls = _stub_client()

    stash = client.update_stash("stash-1", title="Roadmap", description="Plan")

    assert stash == {"id": "stash-1", "title": "Roadmap", "description": "Plan"}
    assert calls == [
        ("/api/v1/stashes/stash-1", {"title": "Roadmap", "description": "Plan"})
    ]


def test_update_stash_access_uses_share_endpoint() -> None:
    client, calls = _stub_client()

    stash = client.update_stash("stash-1", access="public", discoverable=True)

    assert stash == {"id": "stash-1", "access": "public", "discoverable": True}
    assert calls == [
        ("/api/v1/stashes/stash-1/share", {"access": "public", "discoverable": True})
    ]


def test_update_stash_mixed_fields_splits_endpoints() -> None:
    client, calls = _stub_client()

    stash = client.update_stash("stash-1", title="Roadmap", access="private")

    assert stash == {"id": "stash-1", "access": "private", "discoverable": False}
    assert calls == [
        ("/api/v1/stashes/stash-1", {"title": "Roadmap"}),
        ("/api/v1/stashes/stash-1/share", {"access": "private"}),
    ]
