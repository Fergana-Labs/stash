from cli.client import StashClient, skill_permissions_for_access


def _post_stub_client():
    client = StashClient.__new__(StashClient)
    calls: list[tuple[str, dict]] = []

    def fake_post(path: str, json=None) -> dict:
        calls.append((path, json))
        return {"ok": True}

    client._post = fake_post  # type: ignore[method-assign]
    return client, calls


def test_skill_permissions_for_access() -> None:
    assert skill_permissions_for_access("public") == {
        "workspace_permission": "read",
        "public_permission": "read",
    }
    assert skill_permissions_for_access("workspace") == {
        "workspace_permission": "read",
        "public_permission": "none",
    }
    assert skill_permissions_for_access("private") == {
        "workspace_permission": "none",
        "public_permission": "none",
    }


def test_create_skill_uses_permission_fields() -> None:
    client, calls = _post_stub_client()

    client.create_skill("WS", "Launch notes", items=[{"object_type": "folder", "object_id": "F1"}])

    assert calls == [
        (
            "/api/v1/workspaces/WS/skills",
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


def test_publish_skill_uses_public_permission_fields() -> None:
    client, calls = _post_stub_client()

    client.publish_skill("WS", "Launch notes", items=[{"object_type": "folder", "object_id": "F1"}])

    assert calls == [
        (
            "/api/v1/workspaces/WS/skills/publish",
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


def test_publish_maps_audience_to_permission_fields() -> None:
    # The /publish API has no `audience` field — sending one would be silently
    # dropped and the server would apply its private defaults.
    client, calls = _post_stub_client()

    client.publish("WS", "Draft", "# hi", audience="private")

    assert calls == [
        (
            "/api/v1/publish",
            {
                "workspace_id": "WS",
                "title": "Draft",
                "content": "# hi",
                "content_type": "markdown",
                "workspace_permission": "none",
                "public_permission": "none",
            },
        )
    ]
