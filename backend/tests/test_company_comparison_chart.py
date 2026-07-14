import unittest

from chart_builder import build_chart_spec
from llm_client import build_company_comparison_answer


class CompanyComparisonChartTest(unittest.TestCase):
    def setUp(self):
        self.calculation = {
            "status": "ok",
            "comparison": [
                {
                    "company": {"company_name": "S-Oil", "stock_code": "010950"},
                    "period": {"start_year": 2023, "end_year": 2025},
                    "series": [
                        {"year": year, "revenue": {"label": "매출액", "amount": revenue}, "operating_income": {"label": "영업이익", "amount": income}}
                        for year, revenue, income in [(2023, 35, 1.3), (2024, 36, 1.4), (2025, 37, 1.5)]
                    ],
                },
                {
                    "company": {"company_name": "두산에너빌리티", "stock_code": "034020"},
                    "period": {"start_year": 2023, "end_year": 2025},
                    "series": [
                        {"year": year, "revenue": {"label": "매출액", "amount": revenue}, "operating_income": {"label": "영업이익", "amount": income}}
                        for year, revenue, income in [(2023, 6.6, 0.45), (2024, 6.3, 0.39), (2025, 7.1, 0.50)]
                    ],
                },
            ],
        }

    def test_comparison_builds_two_metric_chart(self):
        chart = build_chart_spec("company_trend_tool", self.calculation)
        self.assertEqual(chart["type"], "compact_metric_bar")
        self.assertEqual([metric["key"] for metric in chart["metrics"]], ["revenue", "operating_income"])
        self.assertEqual([len(metric["values"]) for metric in chart["metrics"]], [6, 6])
        self.assertIn("S-Oil", chart["metrics"][0]["values"][0]["label"])

    def test_answer_omits_irrelevant_investment_disclaimer(self):
        answer = build_company_comparison_answer(self.calculation)
        self.assertNotIn("투자 추천이나 목표주가 의견", answer)


if __name__ == "__main__":
    unittest.main()
