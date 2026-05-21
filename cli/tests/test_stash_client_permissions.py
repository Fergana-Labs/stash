from cli.client import StashClient, stash_permissions_for_access


def _post_stub_client():
    client = StashClient.__new__(StashClient)
    calls: list[tuple[str, dict]] = []

    def fake_post(path: str, json=None) -> dict:
        calls.append((path, json))
        return {"ok": True}

    client._post = fake_post  # type: ignore[method-assign]
    return client, calls


def test_stash_permissions_for_access() -> None:
    assert stash_permissions_for_access("public") == {
        "workspace_permission": "view",
        "public_permission": "view",
    }
    assert stash_permissions_for_access("workspace") == {
        "workspace_permission": "view",
        "public_permission": "none",
    }
    assert stash_permissions_for_access("private") == {
        "workspace_permission": "none",
        "public_permission": "none",
    }


def test_create_stash_uses_permission_fields() -> None:
    client, calls = _post_stub_client()

    client.create_stash("WS", "Launch notes", items=[{"object_type": "folder", "object_id": "F1"}])

    assert calls == [
        (
            "/api/v1/workspaces/WS/stashes",
            {
                "title": "Launch notes",
                "description": "",
                "workspace_permission": "view",
                "public_permission": "none",
                "discoverable": False,
                "items": [{"object_type": "folder", "object_id": "F1"}],
            },
        )
    ]


def test_publish_stash_uses_public_permission_fields() -> None:
    client, calls = _post_stub_client()

    client.publish_stash("WS", "Launch notes", items=[{"object_type": "folder", "object_id": "F1"}])

    assert calls == [
        (
            "/api/v1/workspaces/WS/stashes/publish",
            {
                "title": "Launch notes",
                "description": "",
                "workspace_permission": "view",
                "public_permission": "view",
                "discoverable": False,
                "items": [{"object_type": "folder", "object_id": "F1"}],
            },
        )
    ]
