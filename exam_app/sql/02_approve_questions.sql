\set ON_ERROR_STOP on
BEGIN;

\prompt 'Reviewed JAMB question IDs (comma-separated, blank to skip): ' jamb_ids
UPDATE public.jamb_questions
SET review_status = 'approved'
WHERE review_status = 'pending'
  AND id = ANY(COALESCE(string_to_array(NULLIF(:'jamb_ids', ''), ',')::bigint[], ARRAY[]::bigint[]))
RETURNING id;

\prompt 'Reviewed WAEC question IDs (comma-separated, blank to skip): ' waec_ids
UPDATE public.waec_questions
SET review_status = 'approved'
WHERE review_status = 'pending'
  AND id = ANY(COALESCE(string_to_array(NULLIF(:'waec_ids', ''), ',')::bigint[], ARRAY[]::bigint[]))
RETURNING id;

\prompt 'Reviewed NECO question IDs (comma-separated, blank to skip): ' neco_ids
UPDATE public.neco_questions
SET review_status = 'approved'
WHERE review_status = 'pending'
  AND id = ANY(COALESCE(string_to_array(NULLIF(:'neco_ids', ''), ',')::bigint[], ARRAY[]::bigint[]))
RETURNING id;

\prompt 'Reviewed DEMO question IDs (comma-separated, blank to skip): ' demo_ids
UPDATE public.demo_questions
SET review_status = 'approved'
WHERE review_status = 'pending'
  AND id = ANY(COALESCE(string_to_array(NULLIF(:'demo_ids', ''), ',')::bigint[], ARRAY[]::bigint[]))
RETURNING id;

COMMIT;
