"""Add a least-privilege read-only role and approved-question view."""

import os

from alembic import op
import sqlalchemy as sa

revision = "0005_exam_app_access"
down_revision = "0004_question_registry_cleanup"
branch_labels = None
depends_on = None

EXAM_TABLES = (
    "jamb_questions",
    "waec_questions",
    "neco_questions",
    "demo_questions",
)


def upgrade():
    password = os.environ.get("APP_READER_PASSWORD")
    if not password or password == "change-me":
        raise RuntimeError(
            "Set a non-placeholder APP_READER_PASSWORD for this migration."
        )

    bind = op.get_bind()
    bind.execute(
        sa.text("SELECT set_config('app.exam_reader_password', :password, true)"),
        {"password": password},
    )
    op.execute(
        """
        DO $migration$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_reader') THEN
                EXECUTE format(
                    'ALTER ROLE app_reader WITH LOGIN NOSUPERUSER NOCREATEDB '
                    'NOCREATEROLE NOREPLICATION NOINHERIT PASSWORD %L',
                    current_setting('app.exam_reader_password')
                );
            ELSE
                EXECUTE format(
                    'CREATE ROLE app_reader WITH LOGIN NOSUPERUSER NOCREATEDB '
                    'NOCREATEROLE NOREPLICATION NOINHERIT PASSWORD %L',
                    current_setting('app.exam_reader_password')
                );
            END IF;
        END
        $migration$
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW public.public_questions
        WITH (security_barrier = true) AS
        SELECT id, exam_id, subject_id, year, question, options, answer, explanation
        FROM public.questions
        WHERE review_status = 'approved'
        """
    )
    for table in EXAM_TABLES:
        op.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {table}_fts_idx
            ON public.{table} USING gin (to_tsvector('english', question))
            """
        )

    op.execute("REVOKE ALL PRIVILEGES ON SCHEMA public FROM app_reader")
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM app_reader")
    op.execute(
        "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM app_reader"
    )
    op.execute("GRANT USAGE ON SCHEMA public TO app_reader")
    op.execute(
        "GRANT SELECT ON public.public_questions, public.exams, public.subjects "
        "TO app_reader"
    )
    op.execute("ALTER ROLE app_reader SET default_transaction_read_only = on")
    op.execute("ALTER ROLE app_reader SET statement_timeout = '5s'")


def downgrade():
    op.execute(
        "REVOKE SELECT ON public.public_questions, public.exams, public.subjects "
        "FROM app_reader"
    )
    op.execute("DROP VIEW IF EXISTS public.public_questions")
    for table in EXAM_TABLES:
        op.execute(f"DROP INDEX IF EXISTS public.{table}_fts_idx")
