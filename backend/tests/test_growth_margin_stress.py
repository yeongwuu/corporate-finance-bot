import unittest
from unittest.mock import patch

from main_agent import select_tool
from tools.advanced_analysis_tool import analyze_advanced_question


class GrowthMarginStressTest(unittest.TestCase):
    question = "LG에너지솔루션의 매출 성장률이 5%p, 영업이익률이 2%p 동시에 하락하는 스트레스 시나리오를 분석해줘."

    def test_routes_to_advanced_analysis(self):
        self.assertEqual(select_tool(self.question), "advanced_analysis_tool")

    def test_calculates_explicit_growth_and_margin_shocks(self):
        company = type("Company", (), {
            "stock_code": "373220",
            "company_name": "LG에너지솔루션",
            "market": "KOSPI",
            "industry_name": "일차전지 및 축전지 제조업",
            "__dict__": {
                "stock_code": "373220",
                "company_name": "LG에너지솔루션",
                "market": "KOSPI",
                "industry_name": "일차전지 및 축전지 제조업",
            },
        })()
        rows = [
            {"year": 2023, "revenue": {"amount": 30_000}, "operating_income": {"amount": 3_000}},
            {"year": 2024, "revenue": {"amount": 33_000}, "operating_income": {"amount": 3_300}},
            {"year": 2025, "revenue": {"amount": 36_300}, "operating_income": {"amount": 3_630}},
        ]
        with patch("tools.advanced_analysis_tool.FinancialStatementStore") as store_cls, \
             patch("tools.advanced_analysis_tool._fill_missing_series_with_yfinance", return_value=rows), \
             patch("tools.advanced_analysis_tool._prefer_dart_revenue_income_series", return_value=rows), \
             patch("tools.advanced_analysis_tool._latest_price", return_value=400_000):
            store = store_cls.return_value
            store.resolve_company.return_value = company
            store.available_years.return_value = [2023, 2024, 2025]
            store.get_account_series.return_value = rows
            result = analyze_advanced_question(self.question)

        self.assertEqual(result["mode"], "growth_margin_stress")
        self.assertAlmostEqual(result["assumptions"]["growth_drop"], 0.05)
        self.assertAlmostEqual(result["assumptions"]["margin_drop"], 0.02)
        self.assertLess(result["scenario_operating_income"], result["base_operating_income"])


if __name__ == "__main__":
    unittest.main()
