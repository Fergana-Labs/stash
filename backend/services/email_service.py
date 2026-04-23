"""Email notifications via Resend."""

import logging

from ..config import settings

logger = logging.getLogger(__name__)


def _get_resend():
    if not settings.RESEND_API_KEY:
        return None
    try:
        import resend
    except ImportError:
        logger.warning("resend package not installed, skipping email")
        return None

    resend.api_key = settings.RESEND_API_KEY
    return resend


def send_join_request_email(
    admin_emails: list[str],
    requester_name: str,
    workspace_name: str,
    workspace_id: str,
) -> None:
    resend = _get_resend()
    if not resend or not admin_emails:
        logger.info("Skipping join request email (no Resend key or no admin emails)")
        return

    review_url = f"{settings.PUBLIC_URL}/workspaces/{workspace_id}/requests"

    resend.Emails.send(
        {
            "from": "Stash <notifications@joinstash.ai>",
            "to": admin_emails,
            "subject": f"{requester_name} wants to join {workspace_name}",
            "html": (
                f"<p><strong>{requester_name}</strong> requested to join "
                f"<strong>{workspace_name}</strong> on Stash.</p>"
                f'<p><a href="{review_url}">Review request</a></p>'
            ),
        }
    )


def send_join_approved_email(
    user_email: str,
    workspace_name: str,
) -> None:
    resend = _get_resend()
    if not resend or not user_email:
        logger.info("Skipping approval email (no Resend key or no user email)")
        return

    resend.Emails.send(
        {
            "from": "Stash <notifications@joinstash.ai>",
            "to": [user_email],
            "subject": f"You're in! Welcome to {workspace_name}",
            "html": (
                f"<p>Your request to join <strong>{workspace_name}</strong> has been approved.</p>"
                "<p>Next time you run a stash command in the repo, streaming will start automatically.</p>"
            ),
        }
    )
