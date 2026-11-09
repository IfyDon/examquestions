"""Track new questions and enforce question hash uniqueness.

Revision ID: 0002_dedup_counts
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_dedup_counts"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "crawl_runs",
        sa.Column(
            "new_question_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "crawl_runs",
        sa.Column(
            "duplicate_question_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_check_constraint(
        "crawl_runs_new_question_count_check",
        "crawl_runs",
        "new_question_count >= 0",
    )
    op.create_check_constraint(
        "crawl_runs_duplicate_question_count_check",
        "crawl_runs",
        "duplicate_question_count >= 0",
    )
    op.drop_index("questions_hash_idx", table_name="questions")
    op.create_index(
        "questions_hash_idx",
        "questions",
        ["question_hash"],
        unique=True,
        postgresql_where=sa.text("question_hash IS NOT NULL"),
    )


def downgrade():
    op.drop_index("questions_hash_idx", table_name="questions")
    op.create_index(
        "questions_hash_idx",
        "questions",
        ["question_hash"],
        postgresql_where=sa.text("question_hash IS NOT NULL"),
    )
    op.drop_constraint(
        "crawl_runs_duplicate_question_count_check", "crawl_runs", type_="check"
    )
    op.drop_constraint(
        "crawl_runs_new_question_count_check", "crawl_runs", type_="check"
    )
    op.drop_column("crawl_runs", "duplicate_question_count")
    op.drop_column("crawl_runs", "new_question_count")
