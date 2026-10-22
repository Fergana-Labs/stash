"""`stash image-eval check` prints the score and the fixes; `stash image-eval create` uploads both folders and trains."""

from __future__ import annotations

from unittest import mock

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_check_prints_score_and_fixes(tmp_path) -> None:
    image = tmp_path / "draft.png"
    image.write_bytes(b"png")
    with mock.patch("cli.main._client") as factory:
        client = factory.return_value.__enter__.return_value
        client.image_eval_score.return_value = {
            "score": 0.62,
            "label": "liked",
            "summary": "Lines are too thin.",
            "fixes": [{"issue": "Hair is one outline", "fix": "Build it from small loops"}],
            "keep": ["the palette"],
        }
        result = runner.invoke(
            app, ["image-eval", "check", "c1", str(image), "--caller", "agent", "--task", "cat"]
        )
    assert result.exit_code == 0, result.output
    client.image_eval_score.assert_called_once_with(
        "c1", str(image), caller="agent", task="cat", comments=True
    )
    assert "score: 0.62" in result.output
    assert "Hair is one outline" in result.output and "Build it from small loops" in result.output


def test_create_uploads_both_folders_then_trains(tmp_path) -> None:
    for label in ("liked", "disliked"):
        (tmp_path / label).mkdir()
        for i in range(3):
            (tmp_path / label / f"{i}.png").write_bytes(b"png")
        (tmp_path / label / "notes.txt").write_text("not an image")
    with mock.patch("cli.main._client") as factory:
        client = factory.return_value.__enter__.return_value
        client.image_eval_create.return_value = {"id": "c1"}
        client.image_eval_train.return_value = {
            "id": "c1",
            "name": "Yoko",
            "heldout_accuracy": 0.97,
            "liked": 3,
            "disliked": 3,
        }
        result = runner.invoke(
            app,
            [
                "image-eval",
                "create",
                "Yoko",
                "--liked",
                str(tmp_path / "liked"),
                "--disliked",
                str(tmp_path / "disliked"),
            ],
        )
    assert result.exit_code == 0, result.output
    labels = [call.args[1] for call in client.image_eval_add_examples.call_args_list]
    assert labels == ["liked", "disliked"]
    assert all(len(call.args[2]) == 3 for call in client.image_eval_add_examples.call_args_list)
    client.image_eval_train.assert_called_once_with("c1")
    assert "97%" in result.output
