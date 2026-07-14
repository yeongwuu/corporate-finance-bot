import unittest
from types import SimpleNamespace
from unittest.mock import patch

from chart_builder import build_chart_spec
from llm_client import build_final_answer
from main_agent import select_tool
from tools.advanced_analysis_tool import analyze_advanced_question


QUESTION = (
    "한화에어로스페이스의 2022~2024년 매출원가율을 백테스팅하고 "
    "매출원가 2% 상승 시 EPS 방어 확률을 몬테카를로 시뮬레이션해줘"
)


def _financial_rows(revenue, cost):
    return [
        {"sj_div": "CIS", "account_nm": "매출", "thstrm_amount": str(revenue)},
        {"sj_div": "CIS", "account_nm": "매출원가", "thstrm_amount": str(cost)},
        {"sj_div": "CIS", "account_nm": "매출총이익", "thstrm_amount": str(revenue - cost)},
    ]


class _FakeStore:
    company = SimpleNamespace(
        stock_code="012450",
        company_name="한화에어로스페이스",
        market="유가증권시장상장법인",
        industry_name="항공기, 우주선 및 부품 제조업",
    )

    def resolve_company(self, _question):
        return self.company

    def available_years(self, _stock_code):
        return [2019, 2020, 2021, 2022, 2023, 2024, 2025]


class _FakeDartClient:
    rows = {
        2022: _financial_rows(6_539_605_817_572, 5_190_306_443_615),
        2023: _financial_rows(9_359_005_981_309, 7_221_204_757_399),
        2024: _financial_rows(11_240_121_484_118, 8_370_268_279_539),
        2025: [{"sj_div": "CIS", "account_nm": "계속영업 기본주당이익", "thstrm_amount": "28530"}],
    }

    def fetch_financial_accounts(self, stock_code=None, corp_name=None, fiscal_year=None):
        return {"status": "ok", "accounts": self.rows[fiscal_year]}


class CostOfSalesEarTest(unittest.TestCase):
    def _calculate(self):
        with patch("tools.advanced_analysis_tool.FinancialStatementStore", return_value=_FakeStore()), patch(
            "tools.advanced_analysis_tool.load_dart_api_key", return_value="key"
        ), patch("tools.advanced_analysis_tool.DartClient", return_value=_FakeDartClient()):
            return analyze_advanced_question(QUESTION)

    def test_question_routes_to_advanced_analysis(self):
        self.assertEqual(select_tool(QUESTION), "advanced_analysis_tool")

    def test_cost_ratio_backtest_and_defense_probability(self):
        result = self._calculate()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mode"], "cost_of_sales_ear")
        self.assertEqual([round(row["cost_ratio"] * 100, 1) for row in result["history"]], [79.4, 77.2, 74.5])
        self.assertAlmostEqual(result["cost_ratio_volatility"] * 100, 2.45, places=2)
        self.assertEqual(result["base_eps"], 28_530)
        self.assertAlmostEqual(result["base_defense_probability"] * 100, 49.3, places=1)
        self.assertAlmostEqual(result["scenario_defense_probability"] * 100, 21.0, places=1)
        self.assertAlmostEqual(result["probability_change"] * 100, -28.2, places=1)
        self.assertEqual(result["validation"]["status"], "passed")

    def test_answer_and_chart_include_scenario_results(self):
        result = self._calculate()
        answer = build_final_answer(QUESTION, "advanced_analysis_tool", result, [])
        chart = build_chart_spec("advanced_analysis_tool", result)
        self.assertIn("49.3% → 21.0% (-28.2%p)", answer)
        self.assertIn("교차 검증", answer)
        self.assertEqual(chart["type"], "bar")
        self.assertEqual([bar["display"] for bar in chart["bars"]], ["49.3%", "21.0%"])


if __name__ == "__main__":
    unittest.main()
