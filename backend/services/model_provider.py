"""Model providers and the env var each harness CLI reads its key from.

Which provider/harness/credential a given user's turn runs on is decided in
agent_auth.resolve (bring-your-own key/OAuth, else the managed OpenRouter
agent on Pro). This module is just the provider vocabulary those decisions use.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    id: str
    env_var: str  # what the harness CLI reads the key from


ANTHROPIC = Provider("anthropic", "ANTHROPIC_API_KEY")
OPENAI = Provider("openai", "OPENAI_API_KEY")
OPENROUTER = Provider("openrouter", "OPENROUTER_API_KEY")
GEMINI = Provider("gemini", "GEMINI_API_KEY")
