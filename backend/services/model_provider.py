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
# The user's own OpenAI-compatible endpoint (Ollama, vLLM, ...), reached by
# the pi harness through a base URL stored as a credential — the key, when
# set, rides in STASH_LOCAL_KEY which pi's models.json $STASH_LOCAL_KEY
# interpolation reads.
LOCAL = Provider("local", "STASH_LOCAL_KEY")
# Documented fixed behavior (STAS-105): what pi's models.json entry gets for a
# local model when the user leaves the field unset on the endpoint credential.
LOCAL_DEFAULT_CONTEXT_WINDOW = 131072
LOCAL_DEFAULT_MAX_TOKENS = 8192
