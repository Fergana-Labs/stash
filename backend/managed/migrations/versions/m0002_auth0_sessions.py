"""Server-side Auth0 session store (managed-only).

Sessions move out of the stateless browser cookie into this table so that
logout (and back-channel logout / admin revocation) deletes the session
authoritatively instead of racing rolling cookie re-writes. `data` is the
AES-256-GCM-encrypted session JSON (see frontend/managed/auth0/sessionStore.ts);
`sub` and `sid` are plaintext so sessions can be revoked per user / per Auth0
session without decrypting.

Revision ID: m0002
Revises: m0001
"""

from alembic import op

revision = "m0002"
down_revision = "m0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth0_sessions (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            sub TEXT NOT NULL,
            sid TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth0_sessions_expires_at ON auth0_sessions(expires_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_auth0_sessions_sub ON auth0_sessions(sub)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_auth0_sessions_sid ON auth0_sessions(sid)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth0_sessions")
