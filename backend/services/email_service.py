"""Email notifications via Postmark.

The www app uses the same provider for contact-sales submissions, so we
standardize on Postmark across the product.
"""

import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

POSTMARK_URL = "https://api.postmarkapp.com/email"
DEFAULT_FROM = "Stash <notifications@joinstash.ai>"
FOUNDER_FROM = "Sam at Stash <sam@joinstash.ai>"


def _send(payload: dict) -> None:
    if not settings.POSTMARK_SERVER_TOKEN:
        logger.info("Skipping email because Postmark token is not configured")
        return

    payload.setdefault("MessageStream", "outbound")
    res = httpx.post(
        POSTMARK_URL,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": settings.POSTMARK_SERVER_TOKEN,
        },
        json=payload,
        timeout=10.0,
    )
    if res.status_code >= 300:
        logger.error("Postmark send failed status_code=%s", res.status_code)


def send_enterprise_lead_email(user_name: str, user_email: str | None) -> None:
    """Notify sales when a signup picks the enterprise plan during onboarding."""
    _send(
        {
            "From": DEFAULT_FROM,
            "To": settings.SALES_NOTIFY_EMAIL,
            "Subject": f"Enterprise-intent signup: {user_name}",
            "HtmlBody": (
                f"<p><strong>{user_name}</strong> ({user_email or 'no email'}) picked the "
                "enterprise plan during onboarding — production-agent use case.</p>"
                "<p>Their API key is self-serve; unlimited sleep-time curation is gated "
                "on the enterprise plan, which you grant via the admin plan endpoint "
                "after the contract conversation.</p>"
            ),
        }
    )


def send_share_invite_email(to_email: str, owner_name: str, object_type: str) -> None:
    """Tell a not-yet-user someone shared something with them. Without this,
    a pending share_invite sits silent until the recipient independently
    discovers Stash — which they never do."""
    app_url = settings.PUBLIC_URL.rstrip("/")
    _send(
        {
            "From": DEFAULT_FROM,
            "To": to_email,
            "Subject": f"{owner_name} shared a {object_type} with you on Stash",
            "HtmlBody": (
                f"<p><strong>{owner_name}</strong> shared a {object_type} with you on "
                f'<a href="{app_url}">Stash</a> &mdash; a shared workspace your AI '
                "agents can read and write too.</p>"
                f'<p><a href="{app_url}/login">Sign up with this email address</a> and '
                "it will be waiting in your account.</p>"
            ),
        }
    )


def send_verification_email(to_email: str, token: str) -> None:
    """One click sets `users.email_verified` — the trust anchor for joining
    the workspace on the email's domain."""
    app_url = settings.PUBLIC_URL.rstrip("/")
    _send(
        {
            "From": DEFAULT_FROM,
            "To": to_email,
            "Subject": "Verify your email for Stash",
            "HtmlBody": (
                "<p>Click to verify this email address for your Stash account:</p>"
                f'<p><a href="{app_url}/verify-email?token={token}">Verify my email</a></p>'
                "<p>Verifying connects you to your company's workspace if one exists "
                "for your email domain. The link works for 7 days; requesting a new "
                "one replaces it.</p>"
            ),
        }
    )


def send_welcome_email(user_email: str, first_name: str | None = None) -> None:
    if not user_email:
        return

    app_url = settings.PUBLIC_URL.rstrip("/")

    greeting = f"Hey {first_name}," if first_name else "Hey,"

    html = f"""
<p>{greeting}</p>

<p>Thanks for signing up for Stash. Stash helps your agents to learn across
trajectories.</p>

<p><strong>Getting started. There are two ways to get started:</strong></p>

<ol>
  <li><a href="https://joinstash.ai/docs/quickstart"><strong>Install Stash for your Coding Agent</strong></a> &mdash; Just run a cURL command and it will walk you through how to install Stash. You&rsquo;ll start uploading transcripts, and your agent will get access to Skills created from those transcripts (eg if you tell your agent &ldquo;never use useEffect&rdquo;, it will make a skill called &ldquo;don&rsquo;t use useEffect&rdquo;)</li>
  <li><a href="{app_url}/developer"><strong>Install Stash for your Product</strong></a> &mdash; You can do the same operation for your product. If you&rsquo;re building an agent, copy an API key and copy the prompt provided to give your agent learning across rollouts in minutes! A cool feature here is we let your agent merge learnings across multiple end users with anonymization</li>
</ol>

<p>There's also an agent in the app itself (Chat, in the sidebar) &mdash; point it at your own Claude, Codex, or OpenRouter key, or a local model, in settings.</p>

<p>Please reply to this email if you have any questions, or even if you just
want to chat. I personally read every reply!</p>

<p>Sam<br>CEO, Stash</p>
""".strip()

    _send(
        {
            "From": FOUNDER_FROM,
            "To": user_email,
            "ReplyTo": "sam@joinstash.ai, henry@joinstash.ai",
            "Subject": "Welcome to Stash — let's get your agents connected",
            "HtmlBody": html,
        }
    )
