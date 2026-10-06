import json

import pytest

from rm_worker.context import PREFIX, action_context, encode_action_input, render_action_input


class CharacterTokenizer:
    model_max_length = 4096

    def encode(self, text, **kwargs):
        return list(map(ord, text))

    def num_special_tokens_to_add(self, **kwargs):
        return 0

    def decode(self, ids, **kwargs):
        return "".join(map(chr, ids))


def test_long_tools_do_not_evict_task_constraints_or_current_action():
    steps = [
        {"role": "system", "content": "Never edit the customer repository."},
        {"role": "user", "content": "Fix Stash's upload parser."},
        {"role": "tool", "content": "irrelevant output " * 10000},
        {"role": "user", "content": "Keep the original step IDs."},
        {
            "role": "assistant",
            "content": "",
            "tool_name": "exec",
            "tool_input": {"cmd": "pytest test_upload.py"},
        },
    ]
    ids = encode_action_input(CharacterTokenizer(), render_action_input(steps))
    text = "".join(map(chr, ids))
    assert len(ids) <= 4096
    for wanted in [
        "Never edit the customer repository.",
        "Fix Stash's upload parser.",
        "Keep the original step IDs.",
        "pytest test_upload.py",
    ]:
        assert wanted in text
    assert "[omitted]" in text


def test_longer_candidate_does_not_change_the_other_context_sections():
    prior = [
        {"role": "user", "content": "original task " * 1000},
        {"role": "tool", "content": "output " * 1000},
    ]
    texts = []
    for answer in ["short answer", "long answer " * 1000]:
        texts.append(
            "".join(
                map(
                    chr,
                    encode_action_input(
                        CharacterTokenizer(),
                        render_action_input([*prior, {"role": "assistant", "content": answer}]),
                    ),
                )
            )
        )
    assert texts[0].split("[action]")[0] == texts[1].split("[action]")[0]


def test_repo_instructions_and_task_are_distinct_and_updated_rules_win():
    steps = [
        {"role": "user", "content": "# AGENTS.md instructions\nold rules"},
        {
            "role": "user",
            "content": "<external_codex_apps_open_page>metadata</external_codex_apps_open_page>",
        },
        {"role": "user", "content": "Fix the parser"},
        {"role": "user", "content": "# AGENTS.md instructions\nnew rules"},
        {"role": "assistant", "content": "Done"},
    ]
    context = action_context(steps)
    assert context["task"] == context["request"] == "Fix the parser"
    assert "new rules" in context["instructions"] and "old rules" not in context["instructions"]


def test_input_version_is_explicit_and_json_cannot_inject_sections():
    with pytest.raises(ValueError, match="version 3"):
        encode_action_input(CharacterTokenizer(), "legacy conversation")
    with pytest.raises(ValueError, match="sections"):
        encode_action_input(CharacterTokenizer(), PREFIX + json.dumps({"action": "hi"}))
    with pytest.raises(ValueError, match="end at"):
        action_context([{"role": "tool", "content": "a later result"}])


def test_harness_messages_cannot_replace_human_task_or_steering():
    steps = [
        {"role": "user", "content": "<teammate-message>Idle</teammate-message>"},
        {"role": "user", "content": "Fix the upload parser"},
        {"role": "user", "content": "Preserve step IDs"},
        {"role": "user", "content": "  <heartbeat>Check progress</heartbeat>"},
        {"role": "assistant", "content": "Running parser tests"},
    ]
    context = action_context(steps)
    assert context["task"] == "Fix the upload parser"
    assert context["request"] == "Preserve step IDs"
    assert "Check progress" in context["history"]


def test_subagent_keeps_wrapped_task_assignment_without_promoting_later_pings():
    assignment = "<teammate-message>Implement the parser</teammate-message>"
    context = action_context(
        [
            {"role": "user", "content": assignment},
            {"role": "user", "content": "<teammate-message>Status?</teammate-message>"},
            {"role": "assistant", "content": "Running tests"},
        ]
    )
    assert context["task"] == context["request"] == assignment
