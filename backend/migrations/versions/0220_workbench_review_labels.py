"""Separate human audit labels from requests to change an agent or grader."""

from alembic import op

revision = "0220"
down_revision = "0219"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE rm_wb_feedback DROP CONSTRAINT rm_wb_feedback_change_kind_check")
    op.execute(
        "ALTER TABLE rm_wb_feedback ADD CONSTRAINT rm_wb_feedback_change_kind_check CHECK(change_kind IN ('judge_error','agent_error','both','requirement_change','unclear','label_only'))"
    )

    op.execute(
        "CREATE INDEX rm_wb_assessments_grader_created ON rm_wb_assessments(grader_id,created_at)"
    )
    op.execute(
        "CREATE INDEX rm_wb_feedback_owner_created ON rm_wb_feedback(owner_user_id,created_at)"
    )
    op.execute("CREATE INDEX rm_wb_reviewers_user ON rm_wb_trace_reviewers(user_id,trace_id)")


def downgrade():
    op.execute("DROP INDEX rm_wb_assessments_grader_created")
    op.execute("DROP INDEX rm_wb_feedback_owner_created")
    op.execute("DROP INDEX rm_wb_reviewers_user")
    op.execute("UPDATE rm_wb_feedback SET change_kind='unclear' WHERE change_kind='label_only'")
    op.execute("ALTER TABLE rm_wb_feedback DROP CONSTRAINT rm_wb_feedback_change_kind_check")
    op.execute(
        "ALTER TABLE rm_wb_feedback ADD CONSTRAINT rm_wb_feedback_change_kind_check CHECK(change_kind IN ('judge_error','agent_error','both','requirement_change','unclear'))"
    )
