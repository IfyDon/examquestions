# Exam app configuration and manual test

Run these steps from the project root. Do not copy or print `.env` values.

## Configure and migrate

1. Confirm `.env` has non-empty values for `APP_READER_PASSWORD`, `APP_USER`,
   `APP_PASSWORD`, and `EXAM_APP_PORT`. Keep `.env` local and uncommitted.
2. Load the reader password into the current PowerShell process without
   displaying it, then apply the access migration:

   ```powershell
   $line = Get-Content .env | Where-Object { $_ -match '^APP_READER_PASSWORD=' } | Select-Object -First 1
   if (-not $line) { throw 'APP_READER_PASSWORD is missing from .env' }
   $env:APP_READER_PASSWORD = $line.Substring('APP_READER_PASSWORD='.Length)
   docker compose run --build --rm -e APP_READER_PASSWORD api alembic upgrade head
   Remove-Item Env:\APP_READER_PASSWORD
   ```

3. Start the UI and check service health:

   ```powershell
   docker compose up -d --build exam_app
   docker compose ps exam_app db
   ```

## Verify the database and UI

1. As the database owner, confirm the approved-only view can be queried:

   ```powershell
   docker compose exec -T db psql -U webuser -d examquestion -c "SELECT count(*) FROM public_questions;"
   ```

2. Open `http://127.0.0.1:8001` and sign in with `APP_USER` and
   `APP_PASSWORD`. Confirm exams and subjects load and that only approved
   questions are listed.
3. Select an exam, subject, and year; check that questions can be paged and
   searched. Confirm answers remain hidden until “Show answer” is selected.
4. To approve content, review it first and run
   `psql -U webuser -d examquestion -f exam_app/sql/02_approve_questions.sql`.
   Enter only reviewed IDs at the prompts, then reload the app to verify the
   approved questions appear.

## Run automated tests safely

Use only a throwaway database whose name ends in `_test`. The test fixture
truncates and seeds its database. Ensure the test schema and access migration
are already loaded, and use an admin connection string for that test database
only (never the `examquestion` database).

```powershell
python -m pip install -r exam_app\requirements.txt pytest httpx2
$env:TEST_ADMIN_URL = 'postgresql://webuser@127.0.0.1:5432/exam_app_test'
$line = Get-Content .env | Where-Object { $_ -match '^APP_READER_PASSWORD=' } | Select-Object -First 1
if (-not $line) { throw 'APP_READER_PASSWORD is missing from .env' }
$env:APP_READER_PASSWORD = $line.Substring('APP_READER_PASSWORD='.Length)
python -m pytest -q exam_app/tests
Remove-Item Env:\TEST_ADMIN_URL, Env:\APP_READER_PASSWORD
```

The test database must already contain the application schema and access
migration. Never point tests at the live database.
