# Past Questions app

A small read-only web app over the exam database: filter and practise by exam,
subject, year, and full-text search. Answers stay hidden until requested.

## Set up

1. Set `APP_READER_PASSWORD`, `APP_USER`, `APP_PASSWORD`, and `EXAM_APP_PORT` in
   the project `.env`. Keep `.env` local and uncommitted.
2. Apply the access migration from the project root, passing
   `APP_READER_PASSWORD` only to this one-off migration:

   ```powershell
   docker compose run --build --rm -e APP_READER_PASSWORD api alembic upgrade head
   ```

   It provisions the restricted `app_reader` role, approved-only
   `public_questions` view, and search indexes.
3. As the database owner, approve reviewed question IDs with
   `sql/02_approve_questions.sql`. The app displays approved rows only.
4. Start the app and open `http://127.0.0.1:8001`:

   ```powershell
   docker compose up -d --build exam_app
   ```

   Sign in with `APP_USER` and `APP_PASSWORD`. See the project
   [manual configuration and test steps](../Configtest.md).

## Settings

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Compose supplies the restricted `app_reader` connection. |
| `APP_USER` | Required HTTP Basic login name. |
| `APP_PASSWORD` | Required HTTP Basic login password. |
| `APP_READER_PASSWORD` | One-off migration input; never passed to `exam_app`. |
| `EXAM_APP_PORT` | Host port; defaults to `8001`. |

Compose binds the app to localhost. Basic auth sends the password with every
request; use HTTPS if the service is ever exposed beyond localhost.

## Tests

Tests truncate and seed the configured database. Run them only against a
throwaway database whose name ends in `_test`, with the schema and access
migration applied:

```powershell
python -m pip install -r requirements.txt pytest httpx2
$env:TEST_ADMIN_URL = 'postgresql://webuser@127.0.0.1:5432/exam_app_test'
# Set APP_READER_PASSWORD in this shell to the test role's configured password.
python -m pytest -q tests
Remove-Item Env:\TEST_ADMIN_URL, Env:\APP_READER_PASSWORD
```

The suite covers filters, pagination, approved-only results, answer visibility,
search, read-only permissions, login, and stored option shapes.

## Data assumptions

- **Options:** handled as lists of keyed objects, strings, or keyed objects.
- **Answers:** expected as an option letter or matching option text.
- **Images and SVG:** `question_media` is not rendered; never insert SVG content
  into the page as HTML.
- **Content rights:** keep the app private or behind login unless you have
  permission to share the question text.
