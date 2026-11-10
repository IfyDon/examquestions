import unittest

from app.schemas import QuestionInput
from app.question_storage import question_table_for_exam
from app.services import _validate_local_media_path, question_hash


class QuestionServiceTests(unittest.TestCase):
    def setUp(self):
        self.question = QuestionInput(
            exam="Demo",
            subject="Physics",
            year=2025,
            question="What is current?",
            options={"A": "Ampere"},
        )

    def test_hash_ignores_question_whitespace_and_case(self):
        equivalent = self.question.model_copy(
            update={"exam": " DEMO ", "question": "  WHAT  IS current? "}
        )

        self.assertEqual(question_hash(self.question), question_hash(equivalent))

    def test_hash_changes_for_different_question(self):
        different = self.question.model_copy(update={"question": "What is voltage?"})

        self.assertNotEqual(question_hash(self.question), question_hash(different))

    def test_questions_use_separate_exam_tables(self):
        self.assertEqual(question_table_for_exam(" jamb ").name, "jamb_questions")
        self.assertEqual(question_table_for_exam("WAEC").name, "waec_questions")
        self.assertEqual(question_table_for_exam("NECO").name, "neco_questions")
        self.assertEqual(question_table_for_exam("DEMO").name, "demo_questions")

    def test_unknown_exam_has_no_implicit_storage_table(self):
        with self.assertRaisesRegex(ValueError, "No question storage table"):
            question_table_for_exam("Other Exam")

    def test_media_path_must_be_relative_and_confined(self):
        self.assertEqual(
            _validate_local_media_path("diagrams/figure.svg"),
            "diagrams/figure.svg",
        )
        for unsafe_path in ("../outside.svg", "folder/../../outside.svg", "C:\\outside.svg"):
            with self.subTest(path=unsafe_path):
                with self.assertRaises(ValueError):
                    _validate_local_media_path(unsafe_path)


if __name__ == "__main__":
    unittest.main()
