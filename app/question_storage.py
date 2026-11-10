from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

storage_metadata = MetaData()

question_registry = Table(
    "question_registry",
    storage_metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("exam_id", BigInteger, ForeignKey("exams.id"), nullable=False),
    Column("question_hash", Text),
    Index(
        "question_registry_hash_idx",
        "question_hash",
        unique=True,
        postgresql_where=text("question_hash IS NOT NULL"),
    ),
)


def _question_table(name: str) -> Table:
    return Table(
        name,
        storage_metadata,
        Column(
            "id",
            BigInteger,
            ForeignKey("question_registry.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        Column("exam_id", BigInteger, ForeignKey("exams.id"), nullable=False),
        Column("subject_id", BigInteger, nullable=False),
        Column("year", Integer),
        Column("question", Text, nullable=False),
        Column("options", JSONB, nullable=False),
        Column("answer", Text),
        Column("explanation", Text),
        Column("source_url", Text),
        Column("review_status", Text, nullable=False),
        Column("schema_version", Integer, nullable=False),
        Column("scraped_at", DateTime(timezone=True), nullable=False),
    )


QUESTION_TABLES = {
    "JAMB": _question_table("jamb_questions"),
    "WAEC": _question_table("waec_questions"),
    "NECO": _question_table("neco_questions"),
    "DEMO": _question_table("demo_questions"),
}


def question_table_for_exam(name: str) -> Table:
    try:
        return QUESTION_TABLES[name.strip().upper()]
    except KeyError as error:
        raise ValueError(
            f"No question storage table is configured for exam {name!r}."
        ) from error
