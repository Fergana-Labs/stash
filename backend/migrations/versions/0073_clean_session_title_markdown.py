"""Clean markdown prefixes from generated session titles.

Revision ID: 0073
Revises: 0072
Create Date: 2026-05-21
"""

from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE session_titles
        SET title = BTRIM(
            REGEXP_REPLACE(
                REGEXP_REPLACE(title, '^[[:space:]]*title:[[:space:]]*', '', 'i'),
                '^[[:space:]]{0,3}#{1,6}[[:space:]]*',
                ''
            )
        ),
        updated_at = now()
        WHERE title ~* '^[[:space:]]*(title:[[:space:]]*)?[[:space:]]*#{1,6}[[:space:]]*'
        """)


def downgrade() -> None:
    pass
