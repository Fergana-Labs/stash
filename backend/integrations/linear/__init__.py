"""Linear integration: OAuth provider.

A connected Linear account lets Stash read the issues referenced in a
workspace's sessions (backend/services/linear_ticket_service.py) and keeps
their labels fresh in real time via the inbound webhook in
backend/routers/webhooks.py.
"""

from ..registry import register_provider
from .provider import LinearIntegration

register_provider(LinearIntegration())
