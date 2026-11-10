"""Keep question registry rows consistent when exam-table rows are deleted."""

from alembic import op

revision = "0004_question_registry_cleanup"
down_revision = "0003_exam_question_tables"
branch_labels = None
depends_on = None

EXAMS = ("jamb", "waec", "neco", "demo")


def upgrade():
    op.execute(
        """
        CREATE OR REPLACE FUNCTION save_question_revision() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO question_revisions (question_id, previous_data)
            VALUES (
                OLD.id,
                to_jsonb(OLD) || jsonb_build_object(
                    'question_hash',
                    (SELECT question_hash FROM question_registry WHERE id = OLD.id)
                )
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION delete_question_registry_row() RETURNS TRIGGER AS $$
        BEGIN
            DELETE FROM question_registry WHERE id = OLD.id;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for exam in EXAMS:
        op.execute(
            f"""
            CREATE TRIGGER {exam}_questions_delete_registry
            AFTER DELETE ON {exam}_questions
            FOR EACH ROW EXECUTE FUNCTION delete_question_registry_row()
            """
        )


def downgrade():
    for exam in EXAMS:
        op.execute(
            f"DROP TRIGGER IF EXISTS {exam}_questions_delete_registry "
            f"ON {exam}_questions"
        )
    op.execute("DROP FUNCTION IF EXISTS delete_question_registry_row()")
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
