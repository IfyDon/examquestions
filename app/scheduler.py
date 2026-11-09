import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler

from app.database import SessionLocal
from app.models import CrawlRun, Exam
from app.adapters import FixtureAdapter
from app.models import CrawlQueue
from sqlalchemy import select

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("question-bank.scheduler")


def enqueue_fixture_run():
    with SessionLocal() as db:
        payload = FixtureAdapter().read_question("fixture://questions/demo-physics")
        exam = db.scalar(select(Exam).where(Exam.name == payload.exam.strip()))
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
            )
        )
        db.commit()
        logger.info("Queued scheduled synthetic fixture run %s", run.id)


def main():
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        enqueue_fixture_run,
        "interval",
        seconds=int(os.environ.get("SCHEDULER_INTERVAL_SECONDS", "86400")),
        id="synthetic-fixture-crawl",
        max_instances=1,
        next_run_time=None,
    )
    logger.info("Opt-in scheduler started; source crawling remains fixture-only.")
    scheduler.start()


if __name__ == "__main__":
    main()
