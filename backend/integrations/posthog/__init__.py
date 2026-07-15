"""PostHog integration for project analytics configuration."""

from ..registry import register_provider
from .provider import PostHogIntegration

register_provider(PostHogIntegration())
