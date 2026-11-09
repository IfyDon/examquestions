import logging
import os
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.adapters import AwajisJambAdapter, FixtureAdapter
from app.database import SessionLocal
from app.models import CrawlQueue, CrawlRun
from app.services import save_question

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("question-bank.worker")
fixture_adapter = FixtureAdapter()
jamb_adapter = AwajisJambAdapter()


def process_one() -> bool:
    with SessionLocal() as db:
        with db.begin():
            item = db.scalar(
                select(CrawlQueue)
                .where(CrawlQueue.status == "pending")
                .order_by(CrawlQueue.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if item is None:
                return False
            item.status = "processing"
            item.attempts += 1
            run_id = item.run_id
            item_id = item.id
            url = item.url
            run = db.get(CrawlRun, run_id)
            if run is None:
                raise RuntimeError(f"Crawl run {run_id} does not exist.")
            run.status = "running"
            run.started_at = run.started_at or datetime.now(timezone.utc)

    try:
        if url.startswith("fixture://"):
            questions = fixture_adapter.read_questions(url)
        else:
            if os.environ.get("LIVE_FETCH_ENABLED", "false").lower() != "true":
                raise PermissionError("Live source fetching is disabled.")
            questions = jamb_adapter.read_questions(url)
        new_count = 0
        duplicate_count = 0
        with SessionLocal() as db:
            with db.begin():
                for payload in questions:
                    _, is_new = save_question(db, payload)
                    if is_new:
                        new_count += 1
                    else:
                        duplicate_count += 1
                item = db.get(CrawlQueue, item_id)
                run = db.get(CrawlRun, run_id)
                item.status = "completed"
                item.last_error = None
                run.processed_count += 1
                run.new_question_count += new_count
                run.duplicate_question_count += duplicate_count
                if run.processed_count + run.error_count >= run.discovered_count:
                    run.status = "completed" if run.error_count == 0 else "failed"
                    run.completed_at = datetime.now(timezone.utc)
        logger.info(
            "Processed %s questions from %s for crawl run %s",
            len(questions),
            url,
            run_id,
        )
        logger.info(
            "Crawl run %s added %s new questions and skipped %s duplicates",
            run_id,
            new_count,
            duplicate_count,
        )
    except Exception as error:
        logger.exception("Failed to process queue item %s", item_id)
        with SessionLocal() as db:
            with db.begin():
                item = db.get(CrawlQueue, item_id)
                run = db.get(CrawlRun, run_id)
                item.status = "failed"
                item.last_error = str(error)[:4000]
                run.error_count += 1
                run.last_error = str(error)[:4000]
                if run.processed_count + run.error_count >= run.discovered_count:
                    run.status = "failed"
                    run.completed_at = datetime.now(timezone.utc)
    return True


def main():
    logger.info("Fixture-only worker started; live network fetching is disabled.")
    while True:
        if not process_one():
            time.sleep(float(os.environ.get("WORKER_POLL_SECONDS", "1")))


if __name__ == "__main__":
    main()
