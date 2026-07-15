import unittest
from unittest.mock import patch

from tools.advanced_analysis_tool import analyze_advanced_question


class MultiFactorStressFallbackTest(unittest.TestCase):
    def test_dart_accounts_fill_missing_operating_income(self):
        question = "원/달러 환율이 10% 하락하고 기준금리가 1%p 상승하며 반도체 가격이 15% 하락하면 SK하이닉스의 영업이익과 적정 주가가 얼마나 변할지 분석해줘"
        company = type("Company", (), {
            "stock_code": "000660", "company_name": "SK하이닉스", "market": "KOSPI",
            "industry_name": "반도체 제조업",
            "__dict__": {"stock_code": "000660", "company_name": "SK하이닉스", "market": "KOSPI", "industry_name": "반도체 제조업"},
        })()
        dart_row = {
            "year": 2025,
            "operating_income": {"amount": 20_000},
            "total_assets": {"amount": 100_000},
            "total_liabilities": {"amount": 40_000},
        }
        with patch("tools.advanced_analysis_tool.FinancialStatementStore") as store_cls, \
             patch("tools.advanced_analysis_tool._fill_missing_series_with_yfinance", return_value=[{"year": 2025}]), \
             patch("tools.advanced_analysis_tool._prefer_dart_latest_accounts", return_value=dart_row), \
             patch("tools.advanced_analysis_tool._latest_price", return_value=200_000):
            store = store_cls.return_value
            store.resolve_company.return_value = company
            store.available_years.return_value = [2025]
            store.get_account_series.return_value = [{"year": 2025}]
            result = analyze_advanced_question(question)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mode"], "multi_factor_stress")
        self.assertIsNotNone(result["scenario_operating_income"])


if __name__ == "__main__":
    unittest.main()
