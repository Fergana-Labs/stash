from cli.client import StashClient


def _post_stub_client():
    client = StashClient.__new__(StashClient)
    calls: list[tuple[str, dict]] = []

    def fake_post(path: str, json=None) -> dict:
        calls.append((path, json))
        return {"ok": True}

    client._post = fake_post  # type: ignore[method-assign]
    return client, calls


def test_publish_skill_folder_publishes_publicly() -> None:
    client, calls = _post_stub_client()

    client.publish_skill_folder("WS", "F1", title="Launch notes", discoverable=True)

    assert calls == [
        (
            "/api/v1/workspaces/WS/skills",
            {
                "folder_id": "F1",
                "description": "",
                "discoverable": True,
                "title": "Launch notes",
            },
        )
    ]


def test_publish_skill_folder_defaults() -> None:
    client, calls = _post_stub_client()

    client.publish_skill_folder("WS", "F1")

    assert calls == [
        (
            "/api/v1/workspaces/WS/skills",
            {
                "folder_id": "F1",
                "description": "",
                "discoverable": False,
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
