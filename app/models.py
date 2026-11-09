from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("exam_id", "name"),
        UniqueConstraint("id", "exam_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exam_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subject_id", "exam_id"],
            ["subjects.id", "subjects.exam_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("schema_version > 0"),
        Index("questions_exam_subject_year_idx", "exam_id", "subject_id", "year"),
        Index(
            "questions_hash_idx",
            "question_hash",
            unique=True,
            postgresql_where="question_hash IS NOT NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exam_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | dict] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    answer: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    question_hash: Mapped[str | None] = mapped_column(Text)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )


class Option(Base):
    __tablename__ = "options"
    __table_args__ = (
        UniqueConstraint("question_id", "option_key"),
        Index("options_question_idx", "question_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    option_key: Mapped[str] = mapped_column(Text, nullable=False)
    option_text: Mapped[str] = mapped_column(Text, nullable=False)


class QuestionMedia(Base):
    __tablename__ = "question_media"
    __table_args__ = (Index("question_media_question_idx", "question_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    local_path: Mapped[str | None] = mapped_column(Text)
    svg_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    svg_content: Mapped[str | None] = mapped_column(Text)


class CrawlRun(Base):
    __tablename__ = "crawl_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')"
        ),
        CheckConstraint("discovered_count >= 0"),
        CheckConstraint("processed_count >= 0"),
        CheckConstraint("error_count >= 0"),
        CheckConstraint("new_question_count >= 0"),
        CheckConstraint("duplicate_question_count >= 0"),
        Index("crawl_runs_status_idx", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    exam_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("exams.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    new_question_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    duplicate_question_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class CrawlQueue(Base):
    __tablename__ = "crawl_queue"
    __table_args__ = (
        UniqueConstraint("run_id", "url"),
        CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')"),
        CheckConstraint("attempts >= 0"),
        Index(
            "crawl_queue_pending_idx",
            "run_id",
            "id",
            postgresql_where="status = 'pending'",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    page_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)


class QuestionRevision(Base):
    __tablename__ = "question_revisions"
    __table_args__ = (Index("question_revisions_question_idx", "question_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    question_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("questions.id", ondelete="SET NULL")
    )
    previous_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
