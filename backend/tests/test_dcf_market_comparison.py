import unittest
from unittest.mock import patch

from llm_client import build_dcf_sensitivity_answer
from tools.advanced_analysis_tool import analyze_advanced_question


class DcfMarketComparisonTest(unittest.TestCase):
    question = "SK하이닉스의 WACC를 7~9%, 영구성장률을 1~3%로 변경해 적정 주가 민감도 표를 만들고 현재 주가 대비 고평가·저평가 여부를 분석해줘"

    def test_compares_middle_assumption_with_current_price(self):
        base = {
            "status": "ok",
            "company": {"company_name": "SK하이닉스", "stock_code": "000660", "market": "KOSPI"},
            "projections": [{"fcf": 100_000_000_000.0} for _ in range(10)],
        }
        with patch("tools.advanced_analysis_tool._ten_year_dcf", return_value=base), \
             patch("tools.advanced_analysis_tool._fetch_listed_shares", return_value=1_000_000), \
             patch("tools.advanced_analysis_tool._latest_price", return_value=100_000):
            result = analyze_advanced_question(self.question)

        self.assertEqual(result["mode"], "dcf_sensitivity")
        self.assertEqual(result["valuation_comparison"]["current_price"], 100_000)
        self.assertIn(result["valuation_comparison"]["assessment"], {"저평가", "고평가", "적정 수준"})
        answer = build_dcf_sensitivity_answer(result)
        self.assertIn("현재 주가", answer)
        self.assertIn("고평가·저평가", answer)


if __name__ == "__main__":
    unittest.main()
