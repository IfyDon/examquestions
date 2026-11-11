"""Read-only API plus a single page for browsing the exam question database.

Env: DATABASE_URL (use the app_reader role). Optional: APP_USER, APP_PASSWORD (HTTP Basic login).
"""

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

pool: ConnectionPool


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pool
    pool = ConnectionPool(
        os.environ["DATABASE_URL"],
        min_size=1,
        max_size=5,
        open=True,
        kwargs={
            "row_factory": dict_row,
            # belt and braces: even a privileged login cannot write or run long queries
            "options": "-c default_transaction_read_only=on -c statement_timeout=5000",
        },
    )
    yield
    pool.close()


_basic = HTTPBasic(auto_error=False)


def require_login(creds: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    user = os.getenv("APP_USER")
    password = os.getenv("APP_PASSWORD")
    if not user or not password:
        raise HTTPException(503, "Login is not configured")
    user_ok = pw_ok = False
    if creds:
        user_ok = secrets.compare_digest(creds.username.encode(), user.encode())
        pw_ok = secrets.compare_digest(creds.password.encode(), password.encode())
    if not (user_ok and pw_ok):
        raise HTTPException(401, "Login required", headers={"WWW-Authenticate": "Basic"})


app = FastAPI(
    lifespan=lifespan,
    dependencies=[Depends(require_login)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _all(sql: str, args: list[Any] | tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        return conn.execute(sql, args).fetchall()


def norm_options(raw: Any) -> list[dict[str, str]]:
    """Return [{'key': 'A', 'text': '...'}] whatever shape the scraper stored in the jsonb column."""
    out: list[dict[str, str]] = []
    if isinstance(raw, dict):
        for k in sorted(raw):
            out.append({"key": str(k).upper(), "text": "" if raw[k] is None else str(raw[k])})
    elif isinstance(raw, list):
        for i, o in enumerate(raw):
            default_key = chr(65 + i) if i < 26 else str(i + 1)
            if isinstance(o, dict):
                key = next((o[k] for k in ("key", "label", "option_key", "id") if o.get(k)), default_key)
                text = next((o[k] for k in ("text", "option_text", "value", "content") if o.get(k) is not None), "")
                out.append({"key": str(key).upper(), "text": str(text)})
            else:
                out.append({"key": default_key, "text": "" if o is None else str(o)})
    return out


@app.get("/")
def home() -> FileResponse:
    return FileResponse(Path(__file__).parent / "index.html")


@app.get("/api/exams")
def exams() -> list[dict[str, Any]]:
    return _all(
        """SELECT e.id, e.name, count(*) AS n
           FROM public.public_questions q JOIN public.exams e ON e.id = q.exam_id
           GROUP BY e.id, e.name ORDER BY e.name"""
    )


@app.get("/api/subjects")
def subjects(exam_id: int) -> list[dict[str, Any]]:
    return _all(
        """SELECT s.id, s.name, count(*) AS n
           FROM public.public_questions q JOIN public.subjects s ON s.id = q.subject_id
           WHERE q.exam_id = %s GROUP BY s.id, s.name ORDER BY s.name""",
        [exam_id],
    )


@app.get("/api/years")
def years(exam_id: int, subject_id: int | None = None) -> list[int]:
    sql = "SELECT DISTINCT year FROM public.public_questions WHERE exam_id = %s AND year IS NOT NULL"
    args: list[Any] = [exam_id]
    if subject_id is not None:
        sql += " AND subject_id = %s"
        args.append(subject_id)
    return [r["year"] for r in _all(sql + " ORDER BY year DESC", args)]


@app.get("/api/questions")
def questions(
    exam_id: int | None = None,
    subject_id: int | None = None,
    year: int | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=100_000),
) -> dict[str, Any]:
    where, args = ["TRUE"], []
    for col, val in (("q.exam_id", exam_id), ("q.subject_id", subject_id), ("q.year", year)):
        if val is not None:
            where.append(f"{col} = %s")  # column names are fixed above; values are bound
            args.append(val)
    if q and q.strip():
        where.append("to_tsvector('english', q.question) @@ websearch_to_tsquery('english', %s)")
        args.append(q.strip())
    clause = " AND ".join(where)
    total = _all(f"SELECT count(*) AS n FROM public.public_questions q WHERE {clause}", args)[0]["n"]
    items = _all(
        f"""SELECT q.id, q.year, q.question, q.options, e.name AS exam, s.name AS subject
            FROM public.public_questions q
            JOIN public.exams e ON e.id = q.exam_id
            JOIN public.subjects s ON s.id = q.subject_id
            WHERE {clause}
            ORDER BY q.year DESC NULLS LAST, q.id LIMIT %s OFFSET %s""",
        [*args, limit, offset],
    )
    for item in items:
        item["options"] = norm_options(item["options"])
    return {"total": total, "items": items}


@app.get("/api/questions/{question_id}/answer")
def answer(question_id: int) -> dict[str, Any]:
    rows = _all("SELECT answer, explanation FROM public.public_questions WHERE id = %s", [question_id])
    if not rows:
        raise HTTPException(404, "Not found")
    return rows[0]
