"""`stash join` is the guidance path for non-members: it must print the
invite-link instructions, not crash. It once passed a client to
_handle_not_member after the join-request flow (and the extra parameter)
was removed."""

import json

from cli import main


def test_join_prints_invite_guidance(monkeypatch, tmp_path, capsys) -> None:
    (tmp_path / ".stash").write_text(json.dumps({"workspace_id": "ws-1234567890"}))
    monkeypatch.setattr(main, "_require_auth", lambda: {"base_url": "http://test", "api_key": "k"})
    monkeypatch.setattr(main, "_git_toplevel", lambda cwd=None: tmp_path)

    main.join_cmd()

    out = capsys.readouterr().out
    assert "You're not a member" in out
