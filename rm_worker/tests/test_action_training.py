"""Optional ML-environment smoke test: a tiny random CPU model, no downloads or S3."""

import json

import pytest


@pytest.mark.parametrize("input_version", [1, 2, 3])
def test_train_save_reload_and_score_actions(tmp_path, monkeypatch, input_version):
    shared = input_version >= 2
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    tokenizers = pytest.importorskip("tokenizers")
    from rm_worker import evaluate_run, score_run, scoring, train
    from rm_worker.context import render_action_input

    def text(value):
        if input_version != 3:
            return value
        return render_action_input(
            [
                {"role": "user", "content": "Follow the coding task"},
                {"role": "assistant", "content": value},
            ],
            ["Be correct"],
        )

    torch.set_num_threads(1)
    torch.manual_seed(0)
    base = tmp_path / "tiny-base"
    tokenizer_impl = tokenizers.Tokenizer(
        tokenizers.models.WordLevel(
            {"[UNK]": 0, "[PAD]": 1, "user": 2, "assistant": 3, "good": 4, "bad": 5, "lookup": 6},
            unk_token="[UNK]",
        )
    )
    tokenizer_impl.pre_tokenizer = tokenizers.pre_tokenizers.Whitespace()
    tokenizer = transformers.PreTrainedTokenizerFast(
        tokenizer_object=tokenizer_impl,
        unk_token="[UNK]",
        pad_token="[PAD]",
        model_max_length=32,
    )
    tokenizer.save_pretrained(base)
    model = transformers.BertForSequenceClassification(
        transformers.BertConfig(
            vocab_size=7,
            hidden_size=8,
            num_hidden_layers=1,
            num_attention_heads=1,
            intermediate_size=16,
            max_position_embeddings=128,
            num_labels=1,
            hidden_dropout_prob=0,
            attention_probs_dropout_prob=0,
        )
    )
    assert sum(p.numel() for p in model.parameters()) < 20_000
    model.save_pretrained(base)
    monkeypatch.setattr(train, "pick_device", lambda: torch.device("cpu"))
    monkeypatch.setattr(scoring, "pick_device", lambda: torch.device("cpu"))
    monkeypatch.setattr(train, "MAX_LENGTH", 32)
    monkeypatch.setattr(train, "ACTION_MAX_LENGTH", 128)
    uploaded = []
    monkeypatch.setattr(train, "upload_model", lambda path, key: uploaded.append((path, key)))
    (tmp_path / "job.json").write_text(
        json.dumps(
            {
                "kind": "train",
                "base_model": str(base),
                "epochs": 1,
                "artifact_key": "test/checkpoint",
                "fixed_split": shared,
                "input_version": input_version,
                "rubric": ["Be correct"],
            }
        )
    )
    pairs = [
        {
            "trace_id": str(i),
            "chosen": text(f"user {i} assistant lookup good"),
            "rejected": text(f"user {i} assistant lookup bad"),
            "example_id": str(i),
            "partition": "eval" if i == 9 else "train",
            "task_group": str(i),
            "granularity": "action",
            "action_type": "tool_call",
        }
        for i in range(10)
    ]
    items = [
        {"trace_id": "0", "step_id": "call", "text": text("user assistant lookup good")},
        {"trace_id": "0", "step_id": "reply", "text": text("user assistant bad")},
    ]
    train.write_jsonl(tmp_path / "pairs.jsonl", pairs)
    train.write_jsonl(
        tmp_path / "score_items.jsonl", [{"trace_id": "0", "text": text("user assistant good")}]
    )
    train.write_jsonl(tmp_path / "action_score_items.jsonl", items)
    result = train.train(tmp_path)
    assert result["metrics"]["action_scoring_version"] == 1
    assert result["metrics"]["input_version"] == input_version
    assert result["metrics"]["eval_split"] == ("curated_task_groups" if shared else "trace")
    assert result["metrics"]["action_train_pairs"] == 9
    assert result["metrics"]["action_eval_pairs"] == 1
    assert result["metrics"]["tool_eval_pairs"] == 1
    assert result["metrics"]["action_eval_accuracy"] in (0, 1)
    assert (tmp_path / "model" / "action_reward_stats.json").exists()
    before = train.read_jsonl(tmp_path / "action_scores.jsonl")
    assert len(before) == 2 and all(-1 <= r["credit"] <= 1 for r in before)
    assert uploaded == [(tmp_path / "model", "test/checkpoint")]
    # Same saved tokenizer and action reference produce the same scores on another job.
    inference = tmp_path / "inference"
    inference.mkdir()
    (inference / "job.json").write_text('{"kind": "score", "reward_model_key": "test/checkpoint"}')
    train.write_jsonl(inference / "action_score_items.jsonl", items)
    monkeypatch.setattr(score_run, "download_model", lambda key, directory: tmp_path / "model")
    score_run.run(inference)
    after = train.read_jsonl(inference / "action_scores.jsonl")
    for original, restored in zip(before, after, strict=True):
        assert original["step_id"] == restored["step_id"]
        assert original["score"] == pytest.approx(restored["score"])
        assert original["credit"] == pytest.approx(restored["credit"])
    train.write_jsonl(inference / "evaluation_pairs.jsonl", pairs[-1:])
    monkeypatch.setattr(evaluate_run, "download_model", lambda key, directory: tmp_path / "model")
    evaluate_run.run(inference)
    evaluation = json.loads((inference / "evaluation.json").read_text())
    assert evaluation[0]["example_id"] == "9"
    assert type(evaluation[0]["correct"]) is bool
