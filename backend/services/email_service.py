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

<p>Thanks for signing up for Stash. It's one place your agents connect to all
your data &mdash; and a Drive they can read and write natively.</p>

<p><strong>Start here. Any one of these is a real first win:</strong></p>

<ol>
  <li><a href="{app_url}"><strong>Connect a source</strong></a> (Integrations, in the sidebar) &mdash; GitHub, Google Drive, Gmail, Slack, Notion, Linear, Jira, Asana, Granola, PostHog, or X. Whatever you connect becomes searchable by every agent you point at Stash.</li>
  <li><a href="{app_url}"><strong>Give your coding agent memory</strong></a> &mdash; run <code>uv tool install stashai</code> then <code>stash signin</code>. It finds the agents on your machine, wires them up, and from then on your sessions land in Stash automatically. Then ask one something only Stash would know.</li>
  <li><a href="{app_url}/agents"><strong>Chat with the agent in the app</strong></a> &mdash; it already has everything above, and it's a real coding agent on its own cloud box, so it can read, write, and run things rather than just answer. Connect your Claude, Codex, or OpenRouter key in settings to point it at your own account.</li>
</ol>

<p><strong>What's in your Stash:</strong></p>

<ul>
  <li><strong>Files</strong> &mdash; pages, documents, and tables. Markdown, HTML, PDFs, spreadsheets, decks. Your agents read and edit pages alongside you, with conflict-safe saves.</li>
  <li><strong>Sessions</strong> &mdash; every conversation with your coding agents, pushed and indexed automatically.</li>
  <li><strong>Memory</strong> &mdash; a wiki an agent maintains for you. It runs nightly over whatever is new and compiles it into linked pages you can actually read.</li>
  <li><strong>Skills</strong> &mdash; a folder with a <code>SKILL.md</code> in it. Put related work in one folder and it becomes a unit you can share, publish, or install into an agent. We've put four in your account already.</li>
</ul>

<p><strong>A few things worth knowing:</strong></p>

<ul>
  <li>One search covers your pages, sessions, and every source you've connected.</li>
  <li>Your agent can reach Stash through the CLI, MCP, a filesystem-style shell, or the API.</li>
  <li>You can reach <em>your</em> agent from Slack and Telegram too, not just the app.</li>
  <li>Give an agent a schedule and it runs on its own &mdash; a standup summary, a nightly digest, whatever you'd otherwise forget.</li>
  <li><a href="{app_url}/discover"><strong>Discover</strong></a> &mdash; browse what others have published and fork it into your Stash in one click.</li>
</ul>

<p>The free plan covers two connected accounts and ten Memory runs a month,
which is enough to know whether this is for you.</p>

<p>Hit reply if anything&rsquo;s broken or confusing. It lands in my inbox directly.</p>

<p>Sam<br>CEO, Stash</p>
""".strip()

    _send(
        {
            "From": FOUNDER_FROM,
            "To": user_email,
            "ReplyTo": "sam@joinstash.ai",
            "Subject": "Welcome to Stash — let's get your agents connected",
            "HtmlBody": html,
        }
    )
