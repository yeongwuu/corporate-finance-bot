import unittest

from chart_builder import build_chart_spec
from llm_client import append_concept_example


class ConceptExamplesAndRatioTitlesTest(unittest.TestCase):
    def test_theory_answer_gets_relevant_example(self):
        answer = append_concept_example(
            "NPV와 IRR의 차이와 투자안 선택 기준을 설명해줘",
            "NPV와 IRR은 투자안을 평가하는 지표입니다.",
        )
        self.assertIn("예시", answer)
        self.assertIn("100만원", answer)

    def test_liquidity_and_stability_ratios_do_not_use_profitability_title(self):
        calculation = {
            "status": "ok",
            "company": {"company_name": "LG화학"},
            "period": {"start_year": 2021, "end_year": 2025},
            "ratio_series": [
                {
                    "year": year,
                    "current_ratio": {"label": "유동비율", "value": 1.5},
                    "quick_ratio": {"label": "당좌비율", "value": 1.1},
                    "debt_ratio": {"label": "부채비율", "value": 0.8},
                }
                for year in range(2021, 2026)
            ],
        }
        chart = build_chart_spec("company_trend_tool", calculation)
        self.assertEqual(chart["title"], "LG화학 유동성·안정성 비율 추이")
        self.assertNotIn("수익성", chart["title"])


if __name__ == "__main__":
    unittest.main()
