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


def send_welcome_email(user_email: str, first_name: str | None = None) -> None:
    if not user_email:
        return

    app_url = settings.PUBLIC_URL.rstrip("/")

    greeting = f"Hey {first_name}," if first_name else "Hey,"

    html = f"""
<p>{greeting}</p>

<p>Thanks for signing up for Stash. Two things it does for your agents:</p>

<ul>
  <li><strong>One place to connect to all your data</strong> &mdash; GitHub, Google Drive, Gmail, Notion, Slack, Granola. Your agent reads and searches across everything you connect, from day one.</li>
  <li><strong>An agent-native Drive</strong> &mdash; Markdown and HTML pages, files, and session transcripts your agents read and write natively through the CLI, MCP, and API.</li>
</ul>

<p>Under the hood, your workspace is organized into three things:</p>

<ul>
  <li><strong>Skills</strong> &mdash; virtual sub-workspaces. Bundle any subset of your workspace into a Stash, share it publicly, or keep it private. Use them for teams, workstreams, or projects (LinkedIn marketing, backend infra, kernel reading group).</li>
  <li><strong>Files</strong> &mdash; a filesystem for documents (markdown, HTML, PDF, CSV, images). Built so agents can read and edit it natively.</li>
  <li><strong>Sessions</strong> &mdash; every conversation between you and your coding agent (Claude Code, Codex, OpenCode), automatically pushed and indexed.</li>
</ul>

<p><strong>Three ways to get to a first &ldquo;aha&rdquo;:</strong></p>

<ol>
  <li><a href="{app_url}"><strong>Connect your data sources</strong></a> &mdash; GitHub, Google Drive, Gmail, Notion, Slack, or Granola. Your agent reads across everything you connect from day one instead of starting empty.</li>
  <li><a href="{app_url}"><strong>Give your agent memory</strong></a> &mdash; install the CLI, run a coding agent like you normally would, then ask it something only Stash would know.</li>
  <li><a href="{app_url}"><strong>Publish your first artifact</strong></a> &mdash; drop a doc or deck, get a shareable link. Sharing is a first-class feature here, not an afterthought.</li>
</ol>

<p><strong>A few things that make Stash different:</strong></p>

<ul>
  <li><strong>Real-time collaborative editing</strong> on every markdown page (two cursors at once).</li>
  <li><strong>Agent-native by default</strong> &mdash; markdown, HTML, virtual filesystems. The formats agents are already fluent in.</li>
  <li><strong>Search and ask across everything you&rsquo;ve added</strong> &mdash; your agent is grounded on your stuff, not just the pretty docs.</li>
  <li><a href="{app_url}"><strong>Discover &amp; install Skills</strong></a> &mdash; browse skills and knowledge others have published; copy into your workspace in one click.</li>
</ul>

<p><strong>Bring your team in.</strong> One person using Stash is a personal log. A team using Stash is a shared brain.</p>

<p>Hit reply if anything&rsquo;s broken or confusing. It lands in my inbox directly.</p>

<p>Sam<br>CEO, Stash</p>
""".strip()

    _send(
        {
            "From": FOUNDER_FROM,
            "To": user_email,
            "ReplyTo": "sam@joinstash.ai",
            "Subject": "Welcome to Stash — connect your data and start writing",
            "HtmlBody": html,
        }
    )
