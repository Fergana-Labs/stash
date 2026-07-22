"""Heavi rules-of-the-road: rendering rules as virtual files.

Used only by source_service's live branches (ls/cat), which fetch the
customer's endpoint on every read — Heavi's Postgres is the source of truth.
There is deliberately no indexer: whether rules get a local search index at
all is deferred until the unified-search work (PR #860) settles what search
wants from sources. Until then the heavi_learning_docs table stays empty and
rules are browse-only.
"""

from __future__ import annotations


def _path_segment(value: str) -> str:
    return " ".join(value.replace("/", "-").split())[:80].strip()


def rule_path(rule: dict) -> str:
    # One folder per customer org: rules are org-scoped preferences, and
    # per-org folders match how the rest of their stash is organized
    # (session folders per org, /memory/org/<name> pages).
    return f"{_path_segment(rule['org'])}/{_path_segment(rule['summary'])} ({rule['id']})"


def rule_name(rule: dict) -> str:
    return _path_segment(rule["summary"])


def rule_content(rule: dict) -> str:
    if rule["source_type"] == "user_feedback":
        source = f"user_feedback (candidate {rule.get('source_id') or 'unknown'})"
    else:
        source = rule["source_type"]
    lines = [
        rule["summary"],
        "",
        f"- id: {rule['id']}",
        f"- org: {rule['org']}",
        f"- source: {source}",
        f"- created: {rule['created_at']}",
    ]
    return "\n".join(lines) + "\n"


def rule_entries(rules: list[dict], prefix: str = "") -> list[dict]:
    ordered = sorted(rules, key=lambda r: r["created_at"], reverse=True)
    entries = [
        {"path": rule_path(rule), "name": rule_name(rule), "kind": "rule"} for rule in ordered
    ]
    return [entry for entry in entries if entry["path"].startswith(prefix)]


def find_rule(rules: list[dict], path: str) -> dict | None:
    for rule in rules:
        if rule_path(rule) == path or rule["id"] == path:
            return rule
    return None
