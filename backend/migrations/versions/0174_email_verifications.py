"""Single-use email verification tokens.

`users.email_verified` is the trust anchor for derived workspace membership,
but until now only an OAuth provider could set it — a password signup
(Auth0 database connection on hosted, /users/register on self-host) had no
way to verify and was silently locked out of its domain workspace forever.
This table backs a plain email-a-link flow: one live token per user,
consumed on click.
"""

from alembic import op

revision = "0174"
down_revision = "0173"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE email_verifications (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            token text NOT NULL UNIQUE,
            email text NOT NULL,
            expires_at timestamptz NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE email_verifications")
