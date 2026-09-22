"""Remove duplicates already sent to Trash by the original version of 0226."""

from importlib import import_module

revision = "0229"
down_revision = "0228"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import_module("backend.migrations.versions.0226_hide_reuploaded_curator_runs").upgrade()


def downgrade() -> None:
    pass
