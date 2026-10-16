"""Typed contract for an intuition model version.

A version is the full, frozen description of how an item becomes a decision:
the context text, the output labels, the rubric questions the judge answers,
and (separately, in head.py) the weights that combine those answers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OutputType = Literal["choice", "preference", "multi"]
QuestionType = Literal["noul", "choice", "score", "eval", "probe"]
SLUG = r"^[a-z0-9][a-z0-9_-]{0,63}$"
MAX_QUESTIONS = 12
MAX_SEEDS = 20
PREFERENCE_ITEM_LABELS = ("good", "bad")
PAIR_LABELS = ("a", "b")
# Multi-issue models: any subset of the labels applies. An example's label is the
# sorted issue ids joined by "+", or "none" when no issue applies.
NO_ISSUES = "none"
MAX_ISSUES = 8


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Label(Strict):
    id: str = Field(pattern=SLUG)
    description: str = Field(default="", max_length=1000)


class Question(Strict):
    """One rubric question. Its answer becomes one or more head features.

    noul:   criteria = {"true": ..., "false": ...}; feature = P(yes)
    choice: criteria = {option: description}; one feature per option
    score:  criteria = ordered level descriptions; one feature per level
    eval:   another eval's decision (composition.py); criteria = its decisions,
            one feature per decision; eval_id and its pinned version_id are required
    probe:  a learned readout over item embeddings (probe.py); criteria = the
            classes it predicts, one feature per class; version_id pins the fit
    """

    id: str = Field(pattern=SLUG)
    type: QuestionType
    prompt: str = Field(min_length=1, max_length=2000)
    criteria: dict[str, str] | list[str]
    eval_id: str | None = None
    version_id: str | None = None

    @field_validator("prompt")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question prompt must not be blank")
        return value

    @model_validator(mode="after")
    def criteria_shape(self):
        c = self.criteria
        if self.type == "noul":
            if not isinstance(c, dict) or set(c) != {"true", "false"}:
                raise ValueError(f"{self.id}: yes/no criteria need exactly 'true' and 'false'")
        elif self.type in ("choice", "eval", "probe"):
            if not isinstance(c, dict) or not 2 <= len(c) <= 12:
                raise ValueError(f"{self.id}: choice questions need 2-12 options")
            if any(not k.strip() for k in c):
                raise ValueError(f"{self.id}: option names must not be blank")
        elif not isinstance(c, list) or not 2 <= len(c) <= 10:
            raise ValueError(f"{self.id}: score questions need 2-10 ordered levels")
        if self.type == "eval" and not (self.eval_id and self.version_id):
            raise ValueError(f"{self.id}: eval questions name an eval and its pinned version")
        if self.type == "probe" and not (self.version_id and self.eval_id is None):
            raise ValueError(f"{self.id}: probe questions pin a fitted probe by version_id")
        if self.type not in ("eval", "probe") and (self.eval_id or self.version_id):
            raise ValueError(f"{self.id}: only eval and probe questions pin another model")
        return self

    def options(self) -> list[str]:
        """Answer keys the provider must return probabilities for."""
        if self.type == "score":
            return [str(i) for i in range(len(self.criteria))]
        return list(self.criteria)


class VersionSpec(Strict):
    output_type: OutputType
    description: str = Field(max_length=6000)
    labels: list[Label]
    rubric: list[Question] = Field(default_factory=list, max_length=MAX_QUESTIONS)

    @model_validator(mode="after")
    def consistent(self):
        ids = [q.id for q in self.rubric]
        if len(ids) != len(set(ids)):
            raise ValueError("Rubric question ids must be unique")
        if self.output_type == "choice":
            names = [label.id for label in self.labels]
            if not 2 <= len(names) <= 12 or len(names) != len(set(names)):
                raise ValueError("Choice models need 2-12 unique output labels")
        elif self.output_type == "multi":
            names = [label.id for label in self.labels]
            if not 1 <= len(names) <= MAX_ISSUES or len(names) != len(set(names)):
                raise ValueError(f"Multi-issue models need 1-{MAX_ISSUES} unique issues")
            if NO_ISSUES in names or any("+" in n for n in names):
                raise ValueError(f"'{NO_ISSUES}' is reserved: it means no issue applies")
        elif self.labels:
            raise ValueError("Preference models have no output labels; they learn a score")
        return self


def feature_names(rubric: list[dict]) -> list[str]:
    names = []
    for q in rubric:
        if q["type"] in ("choice", "eval", "probe"):
            names.extend(f"{q['id']}={option}" for option in q["criteria"])
        elif q["type"] == "score":
            # One feature per level so the head can learn non-monotone effects
            # (e.g. both "far too short" and "far too long" are bad).
            names.extend(f"{q['id']}={level}" for level in range(len(q["criteria"])))
        else:
            names.append(q["id"])
    return names


def classes(output_type: str, labels: list[dict]) -> list[str]:
    return [label["id"] for label in labels] if output_type in ("choice", "multi") else ["score"]


def issues_of(label: str) -> set[str]:
    return set() if label == NO_ISSUES else set(label.split("+"))


def issues_label(issues) -> str:
    return "+".join(sorted(issues)) or NO_ISSUES


def normalize_label(output_type: str, kind: str, labels: list[dict], label: str) -> str:
    """The canonical form of an example label, or ValueError if it is not valid for the model."""
    if output_type == "multi" and kind == "item":
        ids = {lab["id"] for lab in labels}
        issues = {p.strip() for p in label.replace(",", "+").split("+") if p.strip()}
        issues.discard(NO_ISSUES)
        unknown = issues - ids
        if unknown:
            raise ValueError(
                f"Unknown issues {', '.join(sorted(unknown))}; use {', '.join(sorted(ids))} or {NO_ISSUES}"
            )
        return issues_label(issues)
    allowed = valid_example_labels(output_type, kind, labels)
    if label not in allowed:
        raise ValueError(f"Label must be one of {', '.join(allowed)}")
    return label


def valid_example_labels(output_type: str, kind: str, labels: list[dict]) -> tuple[str, ...]:
    if output_type == "multi" and kind == "item":
        raise ValueError("Multi-issue labels are combinations; use normalize_label")
    if kind == "pair":
        if output_type != "preference":
            raise ValueError("Pairwise examples belong to preference models")
        return PAIR_LABELS
    if output_type == "choice":
        return tuple(label["id"] for label in labels)
    return PREFERENCE_ITEM_LABELS


# ── The eval brief, compiled into what the judge reads ───────────────────
# Everything after the marker is generated from the brief and rewritten whenever
# the brief changes; the text before it is the user's own instructions.
BRIEF_MARKER = "\n\n— From the eval brief —\n"
MAX_DESCRIPTION = 6000


def render_brief(brief: dict) -> str:
    parts = []
    if brief.get("decision"):
        parts.append(f"Decision: {brief['decision']}")
    if brief.get("input"):
        parts.append(f"Inputs: {brief['input']}")
    if brief.get("labels"):
        lines = [
            f"- {lab.get('id')}: {lab.get('means', '')}"
            + (f" Not: {lab['not']}" if lab.get("not") else "")
            for lab in brief["labels"]
            if isinstance(lab, dict)
        ]
        parts.append("Labels and their boundaries:\n" + "\n".join(lines))
    if brief.get("costly_mistake"):
        parts.append(f"When unsure, avoid the costlier mistake: {brief['costly_mistake']}")
    for key, title in (
        ("must_never", "Never get these wrong"),
        ("edge_cases", "Hard cases and the right call"),
    ):
        if brief.get(key):
            parts.append(f"{title}:\n" + "\n".join(f"- {x}" for x in brief[key]))
    if brief.get("context"):
        parts.append(f"Context: {brief['context']}")
    return "\n\n".join(parts)


def instructions_part(description: str) -> str:
    return description.split(BRIEF_MARKER, 1)[0].rstrip()


def compose_description(description: str, brief: dict) -> str:
    """The user's instructions plus the brief, within the description limit."""
    own = instructions_part(description)
    rendered = render_brief(brief or {})
    if not rendered:
        return own
    room = MAX_DESCRIPTION - len(own) - len(BRIEF_MARKER)
    if room < 200:
        return own
    return own + BRIEF_MARKER + rendered[:room]
