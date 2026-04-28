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
        logger.info("Skipping email (POSTMARK_SERVER_TOKEN not set): %s", payload.get("Subject"))
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
        logger.error("Postmark send failed (%s): %s", res.status_code, res.text)


def send_join_request_email(
    admin_emails: list[str],
    requester_name: str,
    workspace_name: str,
    workspace_id: str,
) -> None:
    if not admin_emails:
        return

    review_url = f"{settings.PUBLIC_URL}/workspaces/{workspace_id}/requests"
    html = (
        f"<p><strong>{requester_name}</strong> requested to join "
        f"<strong>{workspace_name}</strong> on Stash.</p>"
        f'<p><a href="{review_url}">Review request</a></p>'
    )

    for admin in admin_emails:
        _send(
            {
                "From": DEFAULT_FROM,
                "To": admin,
                "Subject": f"{requester_name} wants to join {workspace_name}",
                "HtmlBody": html,
            }
        )


def send_join_approved_email(user_email: str, workspace_name: str) -> None:
    if not user_email:
        return

    _send(
        {
            "From": DEFAULT_FROM,
            "To": user_email,
            "Subject": f"You're in! Welcome to {workspace_name}",
            "HtmlBody": (
                f"<p>Your request to join <strong>{workspace_name}</strong> has been approved.</p>"
                "<p>Next time you run a stash command in the repo, streaming will start automatically.</p>"
            ),
        }
    )


def send_welcome_email(user_email: str, first_name: str | None = None) -> None:
    if not user_email:
        return

    base = settings.PUBLIC_URL.rstrip("/")
    install_url = f"{base}/docs/quickstart"
    repo_install_url = f"{base}/docs/cli"
    workspaces_url = f"{base}/workspaces"

    greeting = f"Hey {first_name}," if first_name else "Hey,"

    html = f"""
<p>{greeting}</p>

<p>Thanks for signing up for Stash. You just joined a workspace where every Claude Code, Cursor, and Codex session your team runs becomes shared, queryable context.</p>

<p><strong>Get to your first "aha" in ~2 minutes:</strong></p>

<ol>
  <li><a href="{install_url}"><strong>Install Stash</strong></a> on the machine where you run your coding agent. One line in your terminal.</li>
  <li><strong>During install, we'll offer to import your existing Claude Code and Cursor history.</strong> Say yes. It means your workspace is useful from day one instead of starting empty.</li>
  <li><strong>Run a coding agent like you normally would.</strong> Stash captures the session in the background.</li>
  <li><strong>Ask the agent something only Stash would know.</strong></li>
</ol>

<p><strong>What teams use Stash for:</strong></p>

<ul>
  <li>Live docs for an engineering team, kept in sync with a GitHub repo.</li>
  <li>A shared repository of papers and blog posts, so the team stays up to date without re-sending links.</li>
  <li>A knowledge base for marketing, sales, and content. Every brief, draft, and customer quote in one place.</li>
  <li>Onboarding context for new hires: the decisions, dead-ends, and "why we did X" that never made it into the README.</li>
  <li>Customer research and call notes pooled across PM, design, and GTM.</li>
  <li>On-call runbooks and incident retros, queryable by the next person paged.</li>
</ul>

<p><strong>Bring your team in.</strong> One person using Stash is a personal log. A team using Stash is a shared brain.</p>

<ul>
  <li><a href="{repo_install_url}"><strong>Connect Stash to a GitHub repo</strong></a>. Adds a <code>stash.json</code> manifest and a Stash block to <code>CLAUDE.md</code>. Anyone running a coding agent in that repo is auto-connected, and the <code>CLAUDE.md</code> block is a live doc their agent reads to learn how to query the workspace.</li>
  <li><a href="{workspaces_url}"><strong>Invite a teammate by email</strong></a>.</li>
</ul>

<p>Hit reply if anything's broken or confusing. It lands in my inbox directly.</p>

<p>Sam<br>CEO, Stash</p>
""".strip()

    _send(
        {
            "From": FOUNDER_FROM,
            "To": user_email,
            "ReplyTo": "sam@joinstash.ai",
            "Subject": "Welcome to Stash, let's get your first session captured",
            "HtmlBody": html,
        }
    )
