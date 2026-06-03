from cli.client import CartridgeClient, stash_permissions_for_access


def _post_stub_client():
    client = CartridgeClient.__new__(CartridgeClient)
    calls: list[tuple[str, dict]] = []

    def fake_post(path: str, json=None) -> dict:
        calls.append((path, json))
        return {"ok": True}

    client._post = fake_post  # type: ignore[method-assign]
    return client, calls


def test_cartridge_permissions_for_access() -> None:
    assert stash_permissions_for_access("public") == {
        "workspace_permission": "read",
        "public_permission": "read",
    }
    assert stash_permissions_for_access("workspace") == {
        "workspace_permission": "read",
        "public_permission": "none",
    }
    assert stash_permissions_for_access("private") == {
        "workspace_permission": "none",
        "public_permission": "none",
    }


def test_create_cartridge_uses_permission_fields() -> None:
    client, calls = _post_stub_client()

    client.create_cartridge(
        "WS", "Launch notes", items=[{"object_type": "folder", "object_id": "F1"}]
    )

    assert calls == [
        (
            "/api/v1/workspaces/WS/cartridges",
            {
                "title": "Launch notes",
                "description": "",
                "workspace_permission": "read",
                "public_permission": "none",
                "discoverable": False,
                "items": [{"object_type": "folder", "object_id": "F1"}],
            },
        )
    ]


def test_publish_cartridge_uses_public_permission_fields() -> None:
    client, calls = _post_stub_client()

    client.publish_cartridge(
        "WS", "Launch notes", items=[{"object_type": "folder", "object_id": "F1"}]
    )

    assert calls == [
        (
            "/api/v1/workspaces/WS/cartridges/publish",
            {
                "title": "Launch notes",
                "description": "",
                "workspace_permission": "read",
                "public_permission": "read",
                "discoverable": False,
                "items": [{"object_type": "folder", "object_id": "F1"}],
            },
        )
    ]
