import json
import unittest

import server


class RecommendationCategoryTest(unittest.TestCase):
    def test_recommendations_include_one_question_per_category(self):
        questions = server._generate_guaranteed_questions()

        self.assertEqual(len(questions), 5)
        self.assertEqual(
            [server._question_family(question) for question in questions],
            list(server.RECOMMENDATION_CATEGORIES),
        )

    def test_valuation_and_stress_pool_contains_twenty_five_questions(self):
        server._init_questions_file()
        with open(server.QUESTIONS_FILE, "r", encoding="utf-8") as file:
            questions = json.load(file)

        valuation_questions = [
            question for question in questions
            if server._question_family(question) == "valuation_stress"
        ]
        self.assertEqual(len(valuation_questions), 25)

    def test_advanced_questions_use_explicit_numbers_and_supported_routes(self):
        unsupported = ["향후 10년 FCF", "CapEx와 운전자본"]
        for question in server.VALUATION_STRESS_QUESTION_SEEDS:
            self.assertFalse(any(token in question for token in unsupported), question)
            self.assertRegex(question, r"\d")
            self.assertEqual(server._question_family(question), "valuation_stress")


if __name__ == "__main__":
    unittest.main()
