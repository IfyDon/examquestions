import unittest

from bs4 import BeautifulSoup

from app.adapters import AwajisJambAdapter, FixtureAdapter
from app.schemas import QuestionInput


class FixtureAdapterTests(unittest.TestCase):
    def test_reads_synthetic_question(self):
        question = FixtureAdapter().read_question(
            "fixture://questions/demo-physics"
        )

        self.assertIsInstance(question, QuestionInput)
        self.assertEqual(question.exam, "DEMO")
        self.assertEqual(question.options["B"], "Ampere")

    def test_rejects_non_fixture_urls(self):
        with self.assertRaises(ValueError):
            FixtureAdapter().read_question("https://example.com/question")

    def test_rejects_missing_fixture(self):
        with self.assertRaises(FileNotFoundError):
            FixtureAdapter().read_question("fixture://questions/not-present")

    def test_jamb_adapter_parses_questions_and_choices_without_inventing_answers(self):
        adapter = AwajisJambAdapter(min_request_interval=0)
        page = BeautifulSoup(
            '<meta property="og:title" content="Physics">', "html.parser"
        )
        content = """
        <li class="wpProQuiz_listItem">
          <div class="wpProQuiz_question_text"><p>Sample question?</p></div>
          <ul class="wpProQuiz_questionList">
            <li class="wpProQuiz_questionListItem"><label><input>A choice</label></li>
            <li class="wpProQuiz_questionListItem"><label><input>B choice</label></li>
          </ul>
        </li>
        """

        questions = adapter._parse_quiz_content(
            "https://jambcbt.awajis.com/physics/", page, content
        )

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].exam, "JAMB")
        self.assertEqual(questions[0].subject, "Physics")
        self.assertEqual(questions[0].options, {"A": "A choice", "B": "B choice"})
        self.assertIsNone(questions[0].answer)
        self.assertIsNone(questions[0].explanation)

    def test_jamb_adapter_reads_quiz_id_and_rejects_other_hosts(self):
        page = BeautifulSoup(
            '<div class="wpProQuiz_content"></div><script>quizId: 42,</script>',
            "html.parser",
        )

        self.assertEqual(AwajisJambAdapter._quiz_id(page), "42")
        with self.assertRaises(ValueError):
            AwajisJambAdapter().read_questions("https://example.com/physics/")

    def test_sitemap_discovery_ignores_image_locations(self):
        xml = b"""\
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
                xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
          <url>
            <loc>https://jambcbt.awajis.com/physics/</loc>
            <image:image>
              <image:loc>https://jambcbt.awajis.com/logo.png</image:loc>
            </image:image>
          </url>
        </urlset>
        """

        self.assertEqual(
            AwajisJambAdapter._xml_locations(xml),
            ["https://jambcbt.awajis.com/physics/"],
        )


if __name__ == "__main__":
    unittest.main()
