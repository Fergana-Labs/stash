"""Typed contract for an intuition model version.

A version is the full, frozen description of how an item becomes a decision:
the context text, the output labels, the rubric questions the judge answers,
and (separately, in head.py) the weights that combine those answers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OutputType = Literal["choice", "preference"]
QuestionType = Literal["noul", "choice", "score"]
SLUG = r"^[a-z0-9][a-z0-9_-]{0,63}$"
MAX_QUESTIONS = 12
MAX_SEEDS = 20
PREFERENCE_ITEM_LABELS = ("good", "bad")
PAIR_LABELS = ("a", "b")


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
    """

    id: str = Field(pattern=SLUG)
    type: QuestionType
    prompt: str = Field(min_length=1, max_length=2000)
    criteria: dict[str, str] | list[str]

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
        elif self.type == "choice":
            if not isinstance(c, dict) or not 2 <= len(c) <= 12:
                raise ValueError(f"{self.id}: choice questions need 2-12 options")
            if any(not k.strip() for k in c):
                raise ValueError(f"{self.id}: option names must not be blank")
        elif not isinstance(c, list) or not 2 <= len(c) <= 10:
            raise ValueError(f"{self.id}: score questions need 2-10 ordered levels")
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
        elif self.labels:
            raise ValueError("Preference models have no output labels; they learn a score")
        return self


def feature_names(rubric: list[dict]) -> list[str]:
    names = []
    for q in rubric:
        if q["type"] == "choice":
            names.extend(f"{q['id']}={option}" for option in q["criteria"])
        elif q["type"] == "score":
            # One feature per level so the head can learn non-monotone effects
            # (e.g. both "far too short" and "far too long" are bad).
            names.extend(f"{q['id']}={level}" for level in range(len(q["criteria"])))
        else:
            names.append(q["id"])
    return names


def classes(output_type: str, labels: list[dict]) -> list[str]:
    return [label["id"] for label in labels] if output_type == "choice" else ["score"]


def valid_example_labels(output_type: str, kind: str, labels: list[dict]) -> tuple[str, ...]:
    if kind == "pair":
        if output_type != "preference":
            raise ValueError("Pairwise examples belong to preference models")
        return PAIR_LABELS
    if output_type == "choice":
        return tuple(label["id"] for label in labels)
    return PREFERENCE_ITEM_LABELS
