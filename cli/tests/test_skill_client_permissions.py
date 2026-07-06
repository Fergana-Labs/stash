from cli.client import StashClient


def _stub_client():
    client = StashClient.__new__(StashClient)
    calls: list[tuple[str, str, dict]] = []

    def fake_post(path: str, json=None) -> dict:
        calls.append(("POST", path, json))
        return {"ok": True}

    def fake_put(path: str, json=None) -> dict:
        calls.append(("PUT", path, json))
        return {"ok": True}

    client._post = fake_post  # type: ignore[method-assign]
    client._put = fake_put  # type: ignore[method-assign]
    return client, calls


def test_create_skill_record_sends_classification_fields() -> None:
    client, calls = _stub_client()

    client.create_skill_record("F1", title="Launch notes", discoverable=True)

    assert calls == [
        (
            "POST",
            "/api/v1/me/skills",
            {
                "folder_id": "F1",
                "description": "",
                "discoverable": True,
                "title": "Launch notes",
            },
        )
    ]


def test_create_skill_record_defaults() -> None:
    client, calls = _stub_client()

    client.create_skill_record("F1")

    assert calls == [
        (
            "POST",
            "/api/v1/me/skills",
            {
                "folder_id": "F1",
                "description": "",
                "discoverable": False,
            },
        )
    ]


def test_set_general_access_puts_to_the_share_endpoint() -> None:
    # Public access is a share property, not a skill property — the one
    # endpoint covers every shareable object type.
    client, calls = _stub_client()

    client.set_general_access("folder", "F1", "public")

    assert calls == [
        (
            "PUT",
            "/api/v1/share/general-access",
            {"object_type": "folder", "object_id": "F1", "access": "public"},
        )
    ]


def test_materialize_session_posts_folder_id() -> None:
    client, calls = _stub_client()

    client.materialize_session("sess-abc", "F1")

    assert calls == [
        (
            "POST",
            "/api/v1/me/sessions/sess-abc/materialize",
            {"folder_id": "F1"},
        )
    ]
