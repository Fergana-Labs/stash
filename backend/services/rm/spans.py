"""Timed operations, independent of the messages they contain."""

from pydantic import BaseModel, Field, model_validator


class TraceSpan(BaseModel):
    id: str = Field(min_length=1)
    parent_id: str | None
    name: str = Field(min_length=1)
    kind: str | None
    start_ns: str = Field(pattern=r"^\d+$")
    end_ns: str = Field(pattern=r"^\d+$")
    input: str | None
    output: str | None
    step_indices: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_interval(self):
        if int(self.end_ns) < int(self.start_ns):
            raise ValueError("span end precedes its start")
        if self.parent_id == self.id:
            raise ValueError("a span cannot be its own parent")
        return self


def validate_spans(spans: list[TraceSpan], step_count: int) -> None:
    by_id = {span.id: span for span in spans}
    if len(by_id) != len(spans):
        raise ValueError("duplicate span ids")
    for span in spans:
        if any(index < 0 or index >= step_count for index in span.step_indices):
            raise ValueError("span references a missing step")
        seen = {span.id}
        parent = span.parent_id
        # A parent may be outside the export or still in flight.
        while parent in by_id:
            if parent in seen:
                raise ValueError("cycle in span parents")
            seen.add(parent)
            parent = by_id[parent].parent_id
