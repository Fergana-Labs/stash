"""An editable pi models.json for the local-model endpoint credential.

STAS-117's local model synthesizes pi's models.json from the connect doc
every turn, so a self-hoster could not add models or tune
contextWindow/maxTokens. 0203 lets the user store their own models.json
next to the endpoint credential (encrypted, NULL = use the synthesized
default); the resolver writes the stored bytes verbatim.

Revision ID: 0203
Revises: 0202
"""

from alembic import op

revision = "0203"
down_revision = "0202"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE user_agent_credentials
        ADD COLUMN models_json_enc bytea NULL   -- Fernet-encrypted pi models.json override (NULL = synthesized default)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE user_agent_credentials DROP COLUMN models_json_enc")
