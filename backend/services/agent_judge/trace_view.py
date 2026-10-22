"""A trajectory as a queryable object: the tools workers use to pull only the slices they need.

Every tool returns text under a character budget, so a worker's context holds
the evidence it asked for and nothing else, however long the trace is.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from uuid import UUID

from ..behaviors.segments import clip

READ_CHARS = 12_000
STEP_CHARS = 3_000
GREP_HITS = 25


@dataclass
class TraceView:
    steps: list[dict]
    title: str = ""
    trace_id: UUID | None = None
    owner_id: UUID | None = None
    window: dict | None = None
    hits: list[dict] = field(default_factory=list)

    @classmethod
    def from_item(cls, item, owner_id: UUID | None = None) -> TraceView:
        """An eval item as a trace: trace items keep their steps; anything else is one step."""
        if isinstance(item, dict) and isinstance(item.get("steps"), list):
            steps = [
                {
                    "idx": int(s.get("index", s.get("idx", i))),
                    "role": s.get("role") or "assistant",
                    "content": s.get("content") or "",
                    "tool_name": s.get("tool_name"),
                    "tool_input": s.get("tool_input"),
                }
                for i, s in enumerate(item["steps"])
            ]
            trace_id = item.get("trace_id")
            return cls(
                steps=steps,
                title=item.get("title") or "",
                trace_id=UUID(trace_id) if trace_id else None,
                owner_id=owner_id,
                window=item.get("window"),
            )
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        return cls(
            steps=[
                {
                    "idx": 0,
                    "role": "assistant",
                    "content": text,
                    "tool_name": None,
                    "tool_input": None,
                }
            ],
            owner_id=owner_id,
        )

    @property
    def size(self) -> int:
        return sum(len(s["content"] or "") for s in self.steps)

    def _render(self, step: dict, cap: int = STEP_CHARS) -> str:
        head = f"[{step['idx']}] {step['role'].upper()}"
        if step.get("tool_name"):
            args = json.dumps(step.get("tool_input") or {}, ensure_ascii=False, sort_keys=True)
            head += f" tool call {step['tool_name']} {clip(args, 600)}"
        return f"{head}\n{clip(step['content'] or '', cap)}".rstrip()

    def outline(self) -> str:
        """Shape of the trace: turns, tool use, and where each user turn starts."""
        roles: dict[str, int] = {}
        tools: dict[str, int] = {}
        for s in self.steps:
            roles[s["role"]] = roles.get(s["role"], 0) + 1
            if s.get("tool_name"):
                tools[s["tool_name"]] = tools.get(s["tool_name"], 0) + 1
        lines = [
            f"TITLE: {self.title or '(untitled)'}",
            f"STEPS: {len(self.steps)} (indices {self.steps[0]['idx']}–{self.steps[-1]['idx']}), {self.size:,} characters",
            "ROLES: " + ", ".join(f"{k} {v}" for k, v in sorted(roles.items())),
            "TOOLS: "
            + (
                ", ".join(f"{k} ×{v}" for k, v in sorted(tools.items(), key=lambda kv: -kv[1]))
                or "none"
            ),
        ]
        if self.window:
            lines.append(
                f"JUDGED WINDOW: steps {self.window.get('start')}–{self.window.get('end')} (other steps are context)"
            )
        lines.append("USER TURNS AND FINAL MESSAGES:")
        for s in self.steps:
            if s["role"] == "user":
                lines.append(f"  [{s['idx']}] user: {clip((s['content'] or '').strip(), 160)}")
        finals = [
            s
            for s in self.steps
            if s["role"] == "assistant" and not s.get("tool_name") and (s["content"] or "").strip()
        ]
        for s in finals[-3:]:
            lines.append(f"  [{s['idx']}] assistant: {clip(s['content'].strip(), 240)}")
        if self.hits:
            lines.append("BEHAVIOR TAGS ALREADY ON THIS TRACE:")
            for h in self.hits[:20]:
                lines.append(f"  steps {h['start_idx']}–{h['end_idx']}: {h['behavior_name']}")
        return clip("\n".join(lines), READ_CHARS)

    def read_steps(self, start: int, end: int, max_chars: int = READ_CHARS) -> str:
        chosen = [s for s in self.steps if start <= s["idx"] <= end]
        if not chosen:
            return f"No steps in {start}–{end}."
        out, used = [], 0
        per = max(500, min(STEP_CHARS, max_chars // max(1, len(chosen))))
        for s in chosen:
            text = self._render(s, per)
            if used + len(text) > max_chars:
                out.append(
                    f"…[stopped at step {s['idx']}: budget reached; read from here to continue]"
                )
                break
            out.append(text)
            used += len(text)
        return "\n\n".join(out)

    def grep(self, pattern: str, role: str | None = None, tool: str | None = None) -> str:
        try:
            rx = re.compile(pattern, re.I)
        except re.error:
            rx = re.compile(re.escape(pattern), re.I)
        found = []
        for s in self.steps:
            if role and s["role"] != role:
                continue
            if tool and s.get("tool_name") != tool:
                continue
            haystack = (
                (s["content"] or "")
                + " "
                + json.dumps(s.get("tool_input") or {}, ensure_ascii=False)
            )
            m = rx.search(haystack)
            if m:
                lo = max(0, m.start() - 120)
                found.append(
                    f"[{s['idx']}] {s['role']}{' ' + s['tool_name'] if s.get('tool_name') else ''}: …{haystack[lo : m.end() + 160]}…"
                )
            if len(found) >= GREP_HITS:
                found.append("…more matches; narrow the pattern")
                break
        return "\n".join(found) or f"No step matches {pattern!r}."

    def tool_calls(self, name: str | None = None) -> str:
        """Each tool call with its arguments and the start of the result that follows it."""
        out = []
        for i, s in enumerate(self.steps):
            if not s.get("tool_name") or (name and s["tool_name"] != name):
                continue
            result = next((r for r in self.steps[i + 1 : i + 4] if r["role"] == "tool"), None)
            args = clip(
                json.dumps(s.get("tool_input") or {}, ensure_ascii=False, sort_keys=True), 300
            )
            res = (
                "(no result recorded)"
                if result is None
                else f"[{result['idx']}] {clip((result['content'] or '').strip(), 300)}"
            )
            out.append(f"[{s['idx']}] {s['tool_name']} {args}\n    → {res}")
        return clip("\n".join(out), READ_CHARS) or "No tool calls."
