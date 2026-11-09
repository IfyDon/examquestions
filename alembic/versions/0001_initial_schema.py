"""Create question bank schema.

Revision ID: 0001_initial
"""
from alembic import op

from app.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    op.execute(
        """
        ALTER TABLE questions
        ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION save_question_revision() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO question_revisions (question_id, previous_data)
            VALUES (OLD.id, to_jsonb(OLD));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("DROP TRIGGER IF EXISTS questions_save_revision ON questions")
    op.execute(
        """
        CREATE TRIGGER questions_save_revision
        BEFORE UPDATE ON questions
        FOR EACH ROW EXECUTE FUNCTION save_question_revision()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS questions_save_revision ON questions")
    op.execute("DROP FUNCTION IF EXISTS save_question_revision()")
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
