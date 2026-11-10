import hashlib
import json
from pathlib import Path
from pathlib import PureWindowsPath

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Exam, Option, Question, QuestionMedia, Subject
from app.question_storage import question_registry, question_table_for_exam
from app.schemas import QuestionInput

MEDIA_ROOT = Path(__import__("os").environ.get("MEDIA_ROOT", "/data/media")).resolve()


def question_hash(payload: QuestionInput) -> str:
    canonical = json.dumps(
        {
            "exam": payload.exam.strip().casefold(),
            "subject": payload.subject.strip().casefold(),
            "year": payload.year,
            "question": " ".join(payload.question.split()).casefold(),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_local_media_path(path: str | None) -> str | None:
    if path is None:
        return None
    media_path = Path(path)
    windows_path = PureWindowsPath(path)
    if (
        media_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in media_path.parts
        or ".." in windows_path.parts
    ):
        raise ValueError("Media paths must be relative to the configured media directory.")
    resolved = (MEDIA_ROOT / media_path).resolve()
    if not resolved.is_relative_to(MEDIA_ROOT):
        raise ValueError("Media path is outside the configured media directory.")
    return media_path.as_posix()


def save_question(db: Session, payload: QuestionInput) -> tuple[Question, bool]:
    exam_name = payload.exam.strip()
    subject_name = payload.subject.strip()
    exam = db.scalar(select(Exam).where(Exam.name == exam_name))
    if exam is None:
        exam = Exam(name=exam_name)
        db.add(exam)
        db.flush()

    subject = db.scalar(
        select(Subject).where(
            Subject.exam_id == exam.id, Subject.name == subject_name
        )
    )
    if subject is None:
        subject = Subject(exam_id=exam.id, name=subject_name)
        db.add(subject)
        db.flush()

    digest = question_hash(payload)
    question_id = db.execute(
        pg_insert(question_registry)
        .values(
            exam_id=exam.id,
            question_hash=digest,
        )
        .on_conflict_do_nothing(
            index_elements=[question_registry.c.question_hash],
            index_where=question_registry.c.question_hash.is_not(None),
        )
        .returning(question_registry.c.id)
    ).scalar_one_or_none()
    if question_id is None:
        existing_id = db.scalar(
            select(question_registry.c.id).where(
                question_registry.c.question_hash == digest
            )
        )
        if existing_id is None:
            raise RuntimeError(
                "Question hash conflict occurred but no saved question was found."
            )
        return db.get(Question, existing_id), False

    question_table = question_table_for_exam(exam_name)
    db.execute(
        pg_insert(question_table).values(
            id=question_id,
            exam_id=exam.id,
            subject_id=subject.id,
            year=payload.year,
            question=payload.question.strip(),
            options=payload.options,
            answer=payload.answer,
            explanation=payload.explanation,
            source_url=str(payload.source_url) if payload.source_url else None,
            review_status="pending",
            schema_version=1,
        )
    )
    question = db.get(Question, question_id)
    for key, text in payload.options.items():
        db.add(Option(question_id=question.id, option_key=key, option_text=text))

    for media in payload.media:
        db.add(
            QuestionMedia(
                question_id=question.id,
                source_url=str(media.source_url) if media.source_url else None,
                media_type=media.media_type,
                local_path=_validate_local_media_path(media.local_path),
                svg_metadata=media.svg_metadata,
            )
        )

    db.flush()
    return question, True


def question_json(db: Session, question: Question) -> dict:
    exam = db.get(Exam, question.exam_id)
    subject = db.get(Subject, question.subject_id)
    options = db.scalars(
        select(Option).where(Option.question_id == question.id).order_by(Option.id)
    ).all()
    media = db.scalars(
        select(QuestionMedia)
        .where(QuestionMedia.question_id == question.id)
        .order_by(QuestionMedia.id)
    ).all()
    return {
        "exam": exam.name,
        "subject": subject.name,
        "year": question.year,
        "question": question.question,
        "options": {option.option_key: option.option_text for option in options},
        "answer": question.answer,
        "explanation": question.explanation,
        "svg_assets": [
            {
                "source_url": item.source_url,
                "media_type": item.media_type,
                "local_path": item.local_path,
                "metadata": item.svg_metadata,
            }
            for item in media
            if "svg" in item.media_type.lower()
        ],
        "media_assets": [
            {
                "source_url": item.source_url,
                "media_type": item.media_type,
                "local_path": item.local_path,
                "metadata": item.svg_metadata,
            }
            for item in media
        ],
        "source_url": question.source_url,
        "scraped_at": question.scraped_at,
        "review_status": question.review_status,
        "schema_version": question.schema_version,
    }
