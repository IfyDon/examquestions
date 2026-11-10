import json
import tempfile
import unittest
from pathlib import Path

from app.import_questions import iter_question_records, normalize_record


class ImportQuestionTests(unittest.TestCase):
    def test_streams_flat_records(self):
        data = [
            {
                "exam_type": "JAMB",
                "year": 2019,
                "subject": "Physics",
                "question_text": "What is force?",
                "options": {"A": "A push or pull"},
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            path.write_text(json.dumps(data), encoding="utf-8")

            records = list(iter_question_records(path))

        payload = normalize_record(*records[0])
        self.assertEqual(payload.exam, "JAMB")
        self.assertEqual(payload.subject, "Physics")
        self.assertEqual(payload.year, 2019)
        self.assertEqual(payload.options["A"], "A push or pull")

    def test_inherits_exam_subject_and_year_from_nested_structure(self):
        data = {
            "JAMB": {
                "2019": {
                    "Agricultural Science": [
                        {
                            "question_number": 1,
                            "question_text": "Which crop is a legume?",
                            "options": ["Maize", "Groundnut"],
                        }
                    ]
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            path.write_text(json.dumps(data), encoding="utf-8")

            records = list(iter_question_records(path))

        self.assertEqual(len(records), 1)
        payload = normalize_record(*records[0])
        self.assertEqual(payload.exam, "JAMB")
        self.assertEqual(payload.subject, "Agricultural Science")
        self.assertEqual(payload.year, 2019)
        self.assertEqual(payload.options, {"A": "Maize", "B": "Groundnut"})

    def test_does_not_yield_parent_containers_as_questions(self):
        data = {
            "subjects": {
                "Physics": {
                    "2020": [
                        {
                            "exam_type": "WAEC",
                            "year": 2020,
                            "question": "A nested question?",
                            "options": {"A": "Yes"},
                        }
                    ]
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            path.write_text(json.dumps(data), encoding="utf-8")

            records = list(iter_question_records(path))

        self.assertEqual(len(records), 1)
        payload = normalize_record(*records[0])
        self.assertEqual((payload.exam, payload.subject, payload.year), ("WAEC", "Physics", 2020))


if __name__ == "__main__":
    unittest.main()
