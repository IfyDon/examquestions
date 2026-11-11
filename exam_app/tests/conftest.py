"""Tests run against a THROWAWAY Postgres whose schema is already loaded.

  TEST_ADMIN_URL=postgresql://postgres@127.0.0.1:5544/examdb_test pytest -q

The database name must end in _test: the fixture truncates tables and inserts synthetic rows.
"""

import os
import secrets
import sys
from base64 import b64encode
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ADMIN = os.environ.get("TEST_ADMIN_URL", "")
if not urlparse(ADMIN).path.endswith("_test"):
    pytest.exit("Set TEST_ADMIN_URL to a throwaway database whose name ends in _test", 2)

APP_READER_PASSWORD = os.environ.get("APP_READER_PASSWORD", "")
if not APP_READER_PASSWORD:
    pytest.exit("Set APP_READER_PASSWORD for the throwaway test database", 2)
ADMIN_PARTS = urlparse(ADMIN)
READER = urlunparse(
    ADMIN_PARTS._replace(
        netloc=f"app_reader:{quote(APP_READER_PASSWORD, safe='')}@{ADMIN_PARTS.netloc.rsplit('@', 1)[-1]}"
    )
)
os.environ["APP_USER"] = "exam-test-reader"
os.environ["APP_PASSWORD"] = secrets.token_urlsafe(24)
TEST_APP_USER = os.environ["APP_USER"]
TEST_APP_PASSWORD = os.environ["APP_PASSWORD"]
os.environ["DATABASE_URL"] = READER

SQL = (Path(__file__).resolve().parents[1] / "sql" / "01_app_access.sql").read_text()

LATEX = r"Evaluate \(\frac{1}{2} + \frac{1}{4}\)"
XSS = '<script>window.__xss=1</script><img src=x onerror="window.__xss=2"> Which unit measures force?'

# (exam, subject, year, question, options, answer, explanation, review_status)
ROWS = [
    (
        "JAMB",
        "Mathematics",
        1999,
        LATEX,
        [
            {"key": "A", "text": "1/4"},
            {"key": "B", "text": "1/2"},
            {"key": "C", "text": "3/4"},
            {"key": "D", "text": "1"},
        ],
        "C",
        r"\(\frac{2}{4}+\frac{1}{4}=\frac{3}{4}\)",
        "approved",
    ),
    (
        "JAMB",
        "Mathematics",
        2005,
        "What is 2 + 2?",
        [{"label": "a", "option_text": "3"}, {"label": "b", "option_text": "4"}, {"label": "c", "option_text": "5"}],
        "B",
        None,
        "approved",
    ),
    (
        "JAMB",
        "Mathematics",
        None,
        "Solve x squared equals four",
        {"A": "2", "B": "-2", "C": "both"},
        "C",
        None,
        "approved",
    ),
    (
        "JAMB",
        "Mathematics",
        2010,
        "PENDING-SHOULD-NOT-APPEAR",
        ["x", "y"],
        "A",
        "SECRET-PENDING-EXPLANATION",
        "pending",
    ),
    (
        "JAMB",
        "English Language",
        2001,
        "Choose the word opposite in meaning to benevolent",
        ["kind", "malevolent", "generous", "gentle"],
        "B",
        None,
        "approved",
    ),
    ("WAEC", "Physics", 2008, XSS, ["Joule", "Newton", "Watt", "Pascal"], "B", "F = ma", "approved"),
    ("WAEC", "Physics", 2012, "Photosynthesis needs which gas", ["Oxygen", "Carbon dioxide"], "B", None, "approved"),
    ("WAEC", "Physics", 2013, "REJECTED-QUESTION", ["x", "y"], "A", None, "rejected"),
]
FILLER = 25  # extra approved JAMB Mathematics rows, years 2000-2024, for pagination tests


@pytest.fixture(scope="session", autouse=True)
def database():
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute("TRUNCATE exams, question_registry RESTART IDENTITY CASCADE")
        ids: dict[str, int] = {}
        subj: dict[tuple[str, str], int] = {}
        n = 0

        def add(exam, subject, year, question, options, answer, expl, status):
            nonlocal n
            if exam not in ids:
                ids[exam] = c.execute("INSERT INTO exams(name) VALUES (%s) RETURNING id", [exam]).fetchone()[0]
            if (exam, subject) not in subj:
                subj[(exam, subject)] = c.execute(
                    "INSERT INTO subjects(exam_id, name) VALUES (%s,%s) RETURNING id", [ids[exam], subject]
                ).fetchone()[0]
            n += 1
            rid = c.execute(
                "INSERT INTO question_registry(exam_id, question_hash) VALUES (%s, md5(%s)) RETURNING id",
                [ids[exam], f"{n}-{question}"],
            ).fetchone()[0]
            c.execute(
                f"INSERT INTO {exam.lower()}_questions(id, exam_id, subject_id, year, question, options, answer, explanation, review_status)"
                " VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)",
                [
                    rid,
                    ids[exam],
                    subj[(exam, subject)],
                    year,
                    question,
                    psycopg.types.json.Jsonb(options),
                    answer,
                    expl,
                    status,
                ],
            )

        for row in ROWS:
            add(*row)
        for i in range(FILLER):
            add(
                "JAMB",
                "Mathematics",
                2000 + i,
                f"Filler question number {i}",
                ["a", "b", "c", "d"],
                "A",
                None,
                "approved",
            )
        c.execute(SQL)
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    import main

    credentials = b64encode(f"{TEST_APP_USER}:{TEST_APP_PASSWORD}".encode()).decode()
    with TestClient(main.app, headers={"Authorization": f"Basic {credentials}"}) as cl:
        yield cl
