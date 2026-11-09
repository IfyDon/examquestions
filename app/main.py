import os
import xml.etree.ElementTree as ET

from fastapi import Depends, FastAPI, HTTPException, Query
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import AwajisJambAdapter, FixtureAdapter, JAMB_BASE_URL
from app.database import get_db
from app.models import CrawlQueue, CrawlRun, Exam, Question, Subject
from app.schemas import CrawlRunResponse, QuestionInput
from app.services import question_json, save_question

app = FastAPI(
    title="Question Bank Crawler",
    description=(
        "Local question-bank API. Live source crawling is disabled; only local "
        "synthetic fixtures are available until an authorized source is configured."
    ),
    version="1.0.0",
)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "database": "connected"}


@app.post("/questions/import")
def import_question(payload: QuestionInput, db: Session = Depends(get_db)):
    try:
        question, _ = save_question(db, payload)
        db.commit()
        db.refresh(question)
        return question_json(db, question)
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception:
        db.rollback()
        raise


@app.get("/questions")
def list_questions(
    exam: str | None = None,
    subject: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    statement = select(Question).order_by(Question.id).limit(limit).offset(offset)
    if exam:
        statement = statement.join(Exam, Exam.id == Question.exam_id).where(
            Exam.name == exam
        )
    if subject:
        statement = statement.join(
            Subject, Subject.id == Question.subject_id
        ).where(Subject.name == subject)
    questions = db.scalars(statement).all()
    return [question_json(db, question) for question in questions]


@app.get("/questions/export.json")
def export_questions(db: Session = Depends(get_db)):
    questions = db.scalars(select(Question).order_by(Question.id)).all()
    return [question_json(db, question) for question in questions]


@app.post("/crawl-runs/fixture", response_model=CrawlRunResponse, status_code=201)
def create_fixture_run(db: Session = Depends(get_db)):
    fixtures = FixtureAdapter()
    fixture_path = fixtures.read_question("fixture://questions/demo-physics")
    exam = db.scalar(select(Exam).where(Exam.name == fixture_path.exam.strip()))
    run = CrawlRun(
        source="synthetic-fixtures",
        exam_id=exam.id if exam else None,
        status="pending",
        discovered_count=1,
    )
    db.add(run)
    db.flush()
    db.add(
        CrawlQueue(
            run_id=run.id,
            url="fixture://questions/demo-physics",
            page_type="question",
            status="pending",
        )
    )
    db.commit()
    db.refresh(run)
    return run


@app.post("/crawl-runs/jambcbt", response_model=CrawlRunResponse, status_code=201)
def create_jamb_crawl_run(db: Session = Depends(get_db)):
    if os.environ.get("LIVE_FETCH_ENABLED", "false").lower() != "true":
        raise HTTPException(
            status_code=403,
            detail="Live fetching is disabled. Set LIVE_FETCH_ENABLED=true and restart the services.",
        )

    adapter = AwajisJambAdapter()
    try:
        urls = adapter.discover_subject_urls()
    except (requests.RequestException, ET.ParseError, PermissionError, ValueError) as error:
        raise HTTPException(
            status_code=502, detail=f"Could not discover allowed source pages: {error}"
        ) from error
    if not urls:
        raise HTTPException(status_code=502, detail="The source sitemap contained no pages.")

    exam = db.scalar(select(Exam).where(Exam.name == "JAMB"))
    if exam is None:
        exam = Exam(name="JAMB")
        db.add(exam)
        db.flush()

    run = CrawlRun(
        source=JAMB_BASE_URL,
        exam_id=exam.id,
        status="pending",
        discovered_count=len(urls),
    )
    db.add(run)
    db.flush()
    db.add_all(
        CrawlQueue(
            run_id=run.id,
            url=url,
            page_type="subject",
            status="pending",
        )
        for url in urls
    )
    db.commit()
    db.refresh(run)
    return run


@app.get("/crawl-runs", response_model=list[CrawlRunResponse])
def list_crawl_runs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return db.scalars(select(CrawlRun).order_by(CrawlRun.id.desc()).limit(limit)).all()


@app.get("/crawl-runs/{run_id}", response_model=CrawlRunResponse)
def get_crawl_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Crawl run not found.")
    return run
