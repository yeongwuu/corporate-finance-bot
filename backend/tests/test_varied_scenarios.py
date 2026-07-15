import unittest
from unittest.mock import patch

from main_agent import select_tool
from tools.advanced_analysis_tool import analyze_advanced_question


class VariedScenarioTest(unittest.TestCase):
    def test_revenue_and_cost_scenario(self):
        question = "현대차의 매출이 4% 감소하고 매출원가율이 2%p 상승하는 시나리오를 분석해줘"
        company = type("Company", (), {
            "stock_code": "005380", "company_name": "현대자동차", "market": "KOSPI", "industry_name": "자동차",
            "__dict__": {"stock_code": "005380", "company_name": "현대자동차", "market": "KOSPI", "industry_name": "자동차"},
        })()
        latest = {
            "year": 2025,
            "revenue": {"amount": 100_000},
            "cost_of_sales": {"amount": 70_000},
            "operating_income": {"amount": 10_000},
        }
        self.assertEqual(select_tool(question), "advanced_analysis_tool")
        with patch("tools.advanced_analysis_tool.FinancialStatementStore") as store_cls, \
             patch("tools.advanced_analysis_tool._prefer_dart_latest_accounts", return_value=latest), \
             patch("tools.advanced_analysis_tool._latest_price", return_value=200_000):
            store = store_cls.return_value
            store.resolve_company.return_value = company
            store.available_years.return_value = [2025]
            store.get_account_series.return_value = [latest]
            result = analyze_advanced_question(question)
        self.assertEqual(result["mode"], "revenue_cost_scenario")
        self.assertAlmostEqual(result["assumptions"]["revenue_change"], -0.04)
        self.assertAlmostEqual(result["assumptions"]["cost_ratio_change"], 0.02)

    def test_dividend_growth_scenario(self):
        question = "주당 배당금 2,000원, 배당성장률이 3%에서 5%로 상승하고 요구수익률이 9%일 때 주식가치 변화를 계산해줘"
        self.assertEqual(select_tool(question), "advanced_analysis_tool")
        result = analyze_advanced_question(question)
        self.assertEqual(result["mode"], "dividend_growth_scenario")
        self.assertGreater(result["scenario_value"], result["base_value"])


if __name__ == "__main__":
    unittest.main()
