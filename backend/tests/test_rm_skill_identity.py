"""Metadata recovery runs without an LLM, model weights, or GPU dependencies."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from rm_worker.skill_identity import derive_skill_identity, render_skill

EXAMPLES = [
    {
        "messages": [{"role": "user", "content": "Find a replacement part"}],
        "feedback": ["Cite the catalog"],
    }
]


def response(identity=None, *, arguments=None, tool_name="set_skill_identity"):
    call = SimpleNamespace(
        function=SimpleNamespace(
            name=tool_name,
            arguments=arguments if arguments is not None else json.dumps(identity),
        )
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))])


def test_overlong_description_is_corrected_without_restarting_the_job():
    # Sam's failed production response was 1,050 characters against the 1,024 limit.
    good = {
        "name": "vehicle-parts",
        "description": "Use when researching vehicle parts and cross-references.",
    }
    complete = Mock(side_effect=[response({**good, "description": "x" * 1050}), response(good)])
    assert derive_skill_identity("reflection", EXAMPLES, complete=complete) == tuple(good.values())
    assert complete.call_count == 2
    correction = complete.call_args.kwargs["messages"][0]["content"]
    assert "got 1050" in correction
    assert "under 256 characters" in correction
    assert "Cite the catalog" in correction


@pytest.mark.parametrize(
    "invalid",
    [
        {"name": "Bad Name", "description": "Use for parts"},
        {"name": "x" * 65, "description": "Use for parts"},
        {"name": "parts", "description": " \n "},
        {"name": "parts", "description": 12},
        {"name": "parts"},
        [],
    ],
)
def test_invalid_identity_has_bounded_retries_and_actionable_error(invalid):
    complete = Mock(return_value=response(invalid))
    with pytest.raises(ValueError, match="after 3 attempts.*Please retry skill creation"):
        derive_skill_identity("reflection", EXAMPLES, complete=complete)
    assert complete.call_count == 3


@pytest.mark.parametrize(
    "bad",
    [
        response(arguments="{invalid json"),
        response({}, tool_name="wrong_tool"),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=None))]),
    ],
)
def test_malformed_tool_response_is_repaired(bad):
    good = {"name": "parts", "description": "Use for parts."}
    complete = Mock(side_effect=[bad, response(good)])
    assert derive_skill_identity("reflection", EXAMPLES, complete=complete) == (
        "parts",
        "Use for parts.",
    )


def test_valid_boundary_description_is_preserved_after_whitespace_normalization():
    complete = Mock(
        return_value=response({"name": " parts ", "description": " \n" + "é" * 1024 + "\t "})
    )
    assert derive_skill_identity("reflection", EXAMPLES, complete=complete) == ("parts", "é" * 1024)
    assert complete.call_count == 1


def test_provider_failure_is_not_retried_as_a_validation_failure():
    complete = Mock(side_effect=ConnectionError("provider unavailable"))
    with pytest.raises(ConnectionError, match="provider unavailable"):
        derive_skill_identity("reflection", EXAMPLES, complete=complete)
    assert complete.call_count == 1


def test_generated_skill_frontmatter_round_trips_yaml_special_characters():
    description = 'Use for parts: verify "OEM" references # accurately.'
    rendered = render_skill("parts", description, "Check the catalog.")
    metadata = yaml.safe_load(rendered.split("---", 2)[1])
    assert metadata == {"name": "parts", "description": description}
    assert rendered.endswith("Check the catalog.")
