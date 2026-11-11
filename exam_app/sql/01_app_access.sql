-- Prefer the Alembic migration, which provisions the role password from
-- APP_READER_PASSWORD. Run this SQL only as the database owner.

-- 1. Only approved questions are ever exposed to the app
CREATE OR REPLACE VIEW public.public_questions AS
SELECT id, exam_id, subject_id, year, question, options, answer, explanation
FROM public.questions
WHERE review_status = 'approved';

-- 2. Full-text search indexes (one per question table)
CREATE INDEX IF NOT EXISTS jamb_questions_fts_idx ON public.jamb_questions USING gin (to_tsvector('english', question));
CREATE INDEX IF NOT EXISTS waec_questions_fts_idx ON public.waec_questions USING gin (to_tsvector('english', question));
CREATE INDEX IF NOT EXISTS neco_questions_fts_idx ON public.neco_questions USING gin (to_tsvector('english', question));
CREATE INDEX IF NOT EXISTS demo_questions_fts_idx ON public.demo_questions USING gin (to_tsvector('english', question));

-- 3. The app_reader role is created by the Alembic migration.
ALTER ROLE app_reader SET default_transaction_read_only = on;
ALTER ROLE app_reader SET statement_timeout = '5s';
REVOKE ALL PRIVILEGES ON SCHEMA public FROM app_reader;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM app_reader;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM app_reader;
GRANT USAGE ON SCHEMA public TO app_reader;
GRANT SELECT ON public.public_questions, public.exams, public.subjects TO app_reader;
