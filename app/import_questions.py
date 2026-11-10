"""Bulk-import streamed question JSON into the configured PostgreSQL database.

In Docker, copy the source file to the API container and run:

    docker compose exec -T api python -m app.import_questions \
        --file /tmp/Export_Group1.json /tmp/Export_Group3.json \
        /tmp/Export_Group4.json /tmp/Export_Group5.json --batch-size 500
"""

import argparse
import json
import re
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import ijson
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import SessionLocal
from app.models import Exam, Option, Question, Subject
from app.schemas import QuestionInput
from app.services import question_hash

DEFAULT_FILES = [
    Path(r"C:\Users\USA\Desktop\Project\wikiWebSafe\Crawl\Export_Group1.json"),
    Path(r"C:\Users\USA\Desktop\Project\wikiWebSafe\Crawl\Export_Group3.json"),
    Path(r"C:\Users\USA\Desktop\Project\wikiWebSafe\Crawl\Export_Group4.json"),
    Path(r"C:\Users\USA\Desktop\Project\wikiWebSafe\Crawl\Export_Group5.json"),
]
EXAM_NAMES = {
    "bece",
    "demo",
    "jamb",
    "jssce",
    "ncee",
    "neco",
    "post utme",
    "ssce",
    "utme",
    "waec",
    "wassce",
    "wassce/gce",
}
YEAR_PATTERN = re.compile(r"^(?:19|20|21)\d{2}$")
CONTAINER_NAMES = {
    "data",
    "exam",
    "exams",
    "items",
    "questions",
    "records",
    "subject",
    "subjects",
    "year",
    "years",
}
QUESTION_KEYS = ("question_text", "question")
EXAM_KEYS = ("exam_type", "exam", "exam_name")
SUBJECT_KEYS = ("subject", "subject_name")
YEAR_KEYS = ("year", "exam_year")
OPTION_KEYS = ("options", "choices")


def _record_field(record: dict[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        value = record.get(name)
        if value is not None and value != "":
            return value
    return None


def _is_question_record(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    question = _record_field(value, QUESTION_KEYS)
    return isinstance(question, str) and bool(question.strip())


def iter_question_records(file_path: Path) -> Iterator[tuple[dict[str, Any], tuple[str, ...]]]:
    """Stream question objects from flat arrays or nested subject/year JSON."""
    stack: list[dict[str, Any]] = []
    with file_path.open("rb") as source:
        for _, event, value in ijson.parse(source):
            if event in ("start_map", "start_array"):
                path = ()
                if stack:
                    parent = stack[-1]
                    path = parent["path"]
                    if parent["kind"] == "map" and parent["key"] is not None:
                        path += (str(parent["key"]),)
                stack.append(
                    {
                        "kind": "map" if event == "start_map" else "array",
                        "value": {} if event == "start_map" else [],
                        "path": path,
                        "key": None,
                    }
                )
                continue

            if event == "map_key":
                if not stack or stack[-1]["kind"] != "map":
                    raise ValueError("Malformed JSON: object key outside an object.")
                stack[-1]["key"] = value
                continue

            if event in ("end_map", "end_array"):
                if not stack:
                    raise ValueError("Malformed JSON: unmatched closing container.")
                frame = stack.pop()
                record = frame["value"]
                if frame["kind"] == "map" and _is_question_record(record):
                    yield record, frame["path"]
                    continue
                if stack:
                    _append_value(stack, record)
                continue

            if event in ("string", "number", "boolean", "null"):
                _append_value(stack, value)


def _append_value(stack: list[dict[str, Any]], value: Any) -> None:
    if not stack:
        raise ValueError("Malformed JSON: value found outside the root document.")
    parent = stack[-1]
    if parent["kind"] == "array":
        parent["value"].append(value)
        return
    key = parent["key"]
    if key is None:
        raise ValueError("Malformed JSON: object value has no key.")
    parent["value"][key] = value
    parent["key"] = None


def _context_fields(path: tuple[str, ...]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for part in path:
        cleaned = part.strip()
        lowered = cleaned.casefold()
        if lowered in EXAM_NAMES and "exam_type" not in fields:
            fields["exam_type"] = cleaned
        if YEAR_PATTERN.fullmatch(cleaned) and "year" not in fields:
            fields["year"] = int(cleaned)
    if "subject" not in fields:
        for part in reversed(path):
            cleaned = part.strip()
            lowered = cleaned.casefold()
            if (
                cleaned
                and lowered not in EXAM_NAMES
                and lowered not in CONTAINER_NAMES
                and not YEAR_PATTERN.fullmatch(cleaned)
            ):
                fields["subject"] = cleaned
                break
    return fields


def normalize_record(
    record: dict[str, Any],
    path: tuple[str, ...],
    default_exam: str = "JAMB",
) -> QuestionInput:
    context = _context_fields(path)
    exam = _record_field(record, EXAM_KEYS) or context.get("exam_type") or default_exam
    subject = _record_field(record, SUBJECT_KEYS) or context.get("subject")
    year = _record_field(record, YEAR_KEYS)
    if year is None:
        year = context.get("year")
    question = _record_field(record, QUESTION_KEYS)
    options = _record_field(record, OPTION_KEYS) or {}

    if isinstance(options, list):
        options = {
            chr(ord("A") + index): option
            for index, option in enumerate(options)
        }
    if not isinstance(options, dict):
        raise ValueError("Question options must be an object or an array.")

    return QuestionInput(
        exam=exam,
        subject=subject,
        year=year,
        question=question,
        options=options,
        answer=record.get("answer"),
        explanation=record.get("explanation"),
        source_url=record.get("source_url"),
    )


def _chunks(items: Iterator[QuestionInput], size: int) -> Iterator[list[QuestionInput]]:
    chunk = []
    for item in items:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def import_questions(
    file_paths: Sequence[Path],
    batch_size: int,
    default_exam: str = "JAMB",
) -> tuple[int, int, int]:
    imported = skipped = processed = 0
    records = (
        normalize_record(record, path, default_exam)
        for file_path in file_paths
        for record, path in iter_question_records(file_path)
    )

    with SessionLocal() as db:
        with db.begin():
            for payloads in _chunks(records, batch_size):
                prepared = []
                seen_hashes = set()
                for payload in payloads:
                    digest = question_hash(payload)
                    processed += 1
                    if digest in seen_hashes:
                        skipped += 1
                        continue
                    seen_hashes.add(digest)
                    prepared.append((payload, digest))

                if not prepared:
                    continue

                exam_names = sorted({payload.exam.strip() for payload, _ in prepared})
                db.execute(
                    pg_insert(Exam)
                    .values([{"name": name} for name in exam_names])
                    .on_conflict_do_nothing(index_elements=[Exam.name])
                )
                exams = {
                    name: exam_id
                    for name, exam_id in db.execute(
                        select(Exam.name, Exam.id).where(Exam.name.in_(exam_names))
                    )
                }

                subject_pairs = sorted(
                    {
                        (exams[payload.exam.strip()], payload.subject.strip())
                        for payload, _ in prepared
                    }
                )
                db.execute(
                    pg_insert(Subject)
                    .values(
                        [
                            {"exam_id": exam_id, "name": subject_name}
                            for exam_id, subject_name in subject_pairs
                        ]
                    )
                    .on_conflict_do_nothing(
                        index_elements=[Subject.exam_id, Subject.name]
                    )
                )
                subjects = {
                    (exam_id, name): subject_id
                    for exam_id, name, subject_id in db.execute(
                        select(Subject.exam_id, Subject.name, Subject.id).where(
                            Subject.exam_id.in_({exam_id for exam_id, _ in subject_pairs})
                        )
                    )
                }

                rows_by_hash = {}
                question_rows = []
                for payload, digest in prepared:
                    exam_id = exams[payload.exam.strip()]
                    question_rows.append(
                        {
                            "exam_id": exam_id,
                            "subject_id": subjects[
                                (exam_id, payload.subject.strip())
                            ],
                            "year": payload.year,
                            "question": payload.question.strip(),
                            "options": payload.options,
                            "answer": payload.answer,
                            "explanation": payload.explanation,
                            "source_url": (
                                str(payload.source_url) if payload.source_url else None
                            ),
                            "question_hash": digest,
                            "review_status": "pending",
                        }
                    )
                    rows_by_hash[digest] = payload

                inserted_questions = db.execute(
                    pg_insert(Question)
                    .values(question_rows)
                    .on_conflict_do_nothing(
                        index_elements=[Question.question_hash],
                        index_where=Question.question_hash.is_not(None),
                    )
                    .returning(Question.id, Question.question_hash)
                ).all()
                imported += len(inserted_questions)
                skipped += len(prepared) - len(inserted_questions)

                option_rows = [
                    {
                        "question_id": question_id,
                        "option_key": key,
                        "option_text": text,
                    }
                    for question_id, digest in inserted_questions
                    for key, text in rows_by_hash[digest].options.items()
                ]
                if option_rows:
                    db.execute(pg_insert(Option), option_rows)

    return processed, imported, skipped


def print_summary() -> None:
    with SessionLocal() as db:
        rows = db.execute(
            select(Exam.name, Subject.name, func.count(Question.id))
            .join(Subject, Subject.exam_id == Exam.id)
            .outerjoin(
                Question,
                (Question.exam_id == Exam.id)
                & (Question.subject_id == Subject.id),
            )
            .group_by(Exam.name, Subject.name)
            .order_by(Exam.name, Subject.name)
        ).all()

        print("\nQuestion totals by subject")
        print("-" * 64)
        print(f"{'Exam':<18} {'Subject':<32} {'Questions':>10}")
        print("-" * 64)
        total = 0
        for exam_name, subject_name, count in rows:
            print(f"{exam_name:<18} {subject_name:<32} {count:>10}")
            total += count
        print("-" * 64)
        print(f"{'GRAND TOTAL':<50} {total:>10}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stream question JSON files into the configured PostgreSQL database."
    )
    parser.add_argument("--file", type=Path, nargs="+", default=DEFAULT_FILES)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--default-exam",
        default="JAMB",
        help="Exam name for records without an exam field or enclosing exam key.",
    )
    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    missing_files = [path for path in args.file if not path.is_file()]
    if missing_files:
        parser.error(
            "Input file(s) do not exist: "
            + ", ".join(str(path) for path in missing_files)
        )

    try:
        processed, imported, skipped = import_questions(
            args.file, args.batch_size, args.default_exam
        )
    except Exception as error:
        print(f"Import failed: {error}", file=sys.stderr)
        return 1

    print(
        f"Processed {processed} records; imported {imported}; "
        f"skipped {skipped} duplicates."
    )
    print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
