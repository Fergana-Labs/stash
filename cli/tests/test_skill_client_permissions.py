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

    client.publish_skill_folder("F1", title="Launch notes", discoverable=True)

    assert calls == [
        (
            "/api/v1/me/skills",
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

    client.publish_skill_folder("F1")

    assert calls == [
        (
            "/api/v1/me/skills",
            {
                "folder_id": "F1",
                "description": "",
                "discoverable": False,
            },
        )
    ]
