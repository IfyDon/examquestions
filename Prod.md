# Prod.md

# WAEC, JAMB & NECO Question Bank Crawler

## 1. Project Goal

Build a crawler that, extract

- Questions
- Options
- Answers
- Explanations
- Subjects
- Years
- Images

From:
The URL will be provided later

Store all data in PostgreSQL running in Docker. Do not use a local SQLite
database for application/development data.

Export all content as JSON.

Preserve original media. Keep source SVGs as SVG; do not lossy-trace raster
diagrams. Store media files outside PostgreSQL and their metadata/paths in the
database.

## 2. Technology Stack

### Backend

- Python
- FastAPI
- PostgreSQL 16 in a Docker Compose service
- SQLAlchemy and Alembic migrations

### Crawling

- Source adapter interface; live fetchers/parsers are authorization-gated
- Requests/BeautifulSoup4 for permitted static sources
- Playwright only when needed and permitted for dynamic sources

### Validation

- Pydantic

### Scheduling

- APScheduler

### Deployment

- Docker Compose (PostgreSQL, API, worker; scheduler as an opt-in profile)
- Ubuntu VPS
- Nginx

---

## 3. Source Analysis

### WAEC


### JAMB


### NECO


### Crawler Flow

Exam Page → Subjects → Pagination → Question Pages → Images

The flow above describes a future authorized source adapter. The current
synthetic fixture adapter bypasses network discovery and fetches.

---

## 4. JSON Structure

```json
{
  "exam": "WAEC",
  "subject": "Physics",
  "year": 2025,
  "question": "...",
  "options": {
    "A": "...",
    "B": "...",
    "C": "...",
    "D": "..."
  },
  "answer": "B",
  "explanation": "...",
  "svg_assets": [],
  "source_url": "...",
  "scraped_at": "..."
}
```

---

## 5. Database Design
Database Design

### exams
- id
- name

### subjects
- id
- exam_id
- name

### questions
- id
- exam
- subject
- year
- question
- options
- answer
- explanation
- source_url
- question_hash
- review_status
- schema_version

### options
- id
- question_id
- option_key
- option_text

### question_media
- id
- question_id
- source_url
- media_type
- local_path
- SVG metadata/content when permitted and applicable

### crawl_queue
- id
- run_id
- url
- page_type
- status
- attempts
- last_error

### crawl_runs
- id
- source
- exam
- status
- discovered_count
- processed_count
- error_count
- timestamps
- last_error

### question_revisions
- id
- question_id
- previous_data
- changed_at

### PostgreSQL deployment requirements (Note: Make the database to later accept data for web scraping)

-- Design on docker. Leave it open to accept data for web scraping

---
