# wikiWebSafe Question Bank



## Start the services

From this directory, copy `.env.example` to `.env` if you do not already have
one, set a strong random `POSTGRES_PASSWORD`, and run:

```powershell
docker compose up -d --build
docker compose ps
```

The API listens on `http://127.0.0.1:8000` and PostgreSQL on
`127.0.0.1:5432`. The API and database bind to localhost by default. Keep the
API off public interfaces unless authentication and HTTPS have been configured.
PostgreSQL data and media files persist in Docker volumes. Database schema
changes are managed by Alembic.

The previous PostgreSQL 17 data volume is deliberately kept when switching the
service to PostgreSQL 16. The v16 service uses a separate volume; back up and
restore data explicitly before removing either volume.

## Try the fixture pipeline

Open `http://127.0.0.1:8000/docs`, or from PowerShell queue the synthetic demo
question:

```powershell
$run = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/crawl-runs/fixture
$run
```

The worker processes the local fixture. Check the run and exported JSON:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/crawl-runs/$($run.id)"
Invoke-RestMethod http://127.0.0.1:8000/questions/export.json
```

## Bulk-import a JSON question file

The importer streams flat or nested subject/year JSON, validates records, and
inserts questions and options in batches. It skips records whose normalized
exam, subject, year, and question text already exist.

Copy the JSON exports into the running API container and run the importer.
Multiple files are streamed in configurable batches; exports without an exam
field default to JAMB (override with `--default-exam`):

```powershell
docker cp "C:\Users\USA\Desktop\Project\wikiWebSafe\Crawl\Export_Group1.json" wikiwebsafe-api-1:/tmp/Export_Group1.json
docker cp "C:\Users\USA\Desktop\Project\wikiWebSafe\Crawl\Export_Group3.json" wikiwebsafe-api-1:/tmp/Export_Group3.json
docker cp "C:\Users\USA\Desktop\Project\wikiWebSafe\Crawl\Export_Group4.json" wikiwebsafe-api-1:/tmp/Export_Group4.json
docker cp "C:\Users\USA\Desktop\Project\wikiWebSafe\Crawl\Export_Group5.json" wikiwebsafe-api-1:/tmp/Export_Group5.json
docker compose exec -T api python -m app.import_questions --file /tmp/Export_Group1.json /tmp/Export_Group3.json /tmp/Export_Group4.json /tmp/Export_Group5.json --batch-size 500
```

The command prints the number imported and skipped, then reports database
totals for each exam/subject and a grand total. Duplicate identity includes
exam, subject, year, and normalized question text. Input files are not added
to the Docker image or committed to Git.

Questions are stored in separate `jamb_questions`, `waec_questions`,
`neco_questions`, and `demo_questions` tables. The `questions` view combines
them for existing API reads, while `question_registry` preserves globally
unique IDs and duplicate hashes.

Question updates are deduplicated by a normalized content hash and recorded in
`question_revisions`. Questions remain in `pending` review status until reviewed.

## Source and media policy

Live fetching is disabled by default. Only enable it for a source you are
authorized to access and store. The JAMB adapter is scoped to
`jambcbt.awajis.com`, checks that site's `robots.txt`, discovers pages through
its sitemap, applies a one-second minimum request interval, and uses the quiz's
public data-loading interface. It does not submit answers or attempt to infer
answers/explanations that the source does not return.

After confirming you have permission to reproduce and store the site's
questions, set `LIVE_FETCH_ENABLED=true` in `.env`, then restart the services:

```powershell
docker compose up -d --build
$run = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/crawl-runs/jambcbt
```

Monitor the queued page crawl and export the saved content:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/crawl-runs/$($run.id)"
Invoke-RestMethod http://127.0.0.1:8000/questions/export.json
```

The crawl queues subject pages listed in the sitemap; some sitemap pages may
not contain a quiz and will be skipped. The returned quiz questions do not
include answers or explanations, so those fields remain empty. Do not expose
the API to the public internet without authentication and HTTPS.

Question text is normalized and hashed per exam, subject, and year. A unique
database index prevents duplicate imports, and previously imported questions
are skipped without changing their saved data. Each crawl run reports
`new_question_count` and `duplicate_question_count`.

Media files belong in the persistent media volume; the database stores their
source URLs, MIME types, relative paths, and metadata. SVGs are not rasterized.
The demo fixture contains no external content.

## Optional scheduler

The scheduler is disabled by default. Enable it only when scheduled fixture
ingestion is useful:

```powershell
docker compose --profile scheduler up -d --build
```

It queues the local synthetic fixture at `SCHEDULER_INTERVAL_SECONDS` (one day
by default); the worker consumes the queue.

## Other commands

```powershell
docker compose logs -f api worker
docker compose down
python .\scrape_wikipedia.py
```

`docker compose down` stops containers but preserves database and media volumes.
Do not remove volumes unless you intend to delete their data.

## Exam app

The read-only practice app is available at `http://127.0.0.1:8001` after its
database access migration has been applied and the `exam_app` service is
started. Set `APP_READER_PASSWORD`, `APP_USER`, `APP_PASSWORD`, and
`EXAM_APP_PORT` in `.env`. The reader password is used only by the one-off
migration; the app receives only its database URL and login credentials.
Questions stay hidden until an owner approves their IDs with
[`exam_app/sql/02_approve_questions.sql`](./exam_app/sql/02_approve_questions.sql).
See [Configtest.md](./Configtest.md) for setup and manual checks.
