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

    def test_valuation_and_stress_questions_are_balanced(self):
        valuation = [question for question in server.VALUATION_STRESS_QUESTION_SEEDS if "WACC" in question and "영구성장률" in question]
        scenarios = [question for question in server.VALUATION_STRESS_QUESTION_SEEDS if question not in valuation]
        self.assertEqual(len(valuation), 12)
        self.assertEqual(len(scenarios), 13)

    def test_scenario_questions_use_varied_driver_pairs(self):
        scenarios = server.VALUATION_STRESS_QUESTION_SEEDS[12:]
        self.assertEqual(sum("기준금리" in q and "환율" in q for q in scenarios), 3)
        self.assertEqual(sum("매출 성장률" in q and "영업이익률" in q for q in scenarios), 4)
        self.assertEqual(sum("매출원가율" in q for q in scenarios), 3)
        self.assertEqual(sum("배당성장률" in q and "요구수익률" in q for q in scenarios), 3)

    def test_recommended_scenarios_do_not_use_semiconductor_price(self):
        for question in server.VALUATION_STRESS_QUESTION_SEEDS:
            self.assertNotIn("반도체 가격", question)


if __name__ == "__main__":
    unittest.main()
