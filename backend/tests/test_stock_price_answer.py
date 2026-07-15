import unittest

from llm_client import build_stock_price_answer


class StockPriceAnswerTest(unittest.TestCase):
    def test_return_and_volatility_are_prioritized(self):
        calculation = {
            "company": {"company_name": "현대모비스"},
            "price_source": "네이버 금융",
            "period": {"label": "최근 2년"},
            "stats": {
                "first_close": 232000,
                "last_close": 466000,
                "min_close": 204000,
                "max_close": 768000,
                "cumulative_return_display": "100.86%",
                "daily_return_mean_display": "0.12%",
                "daily_return_std_display": "2.35%",
                "annualized_return_display": "35.10%",
                "annualized_volatility_display": "37.30%",
                "max_drawdown_display": "-39.45%",
            },
        }

        answer = build_stock_price_answer(calculation)

        self.assertIn("기간 수익률은 100.86%", answer)
        self.assertIn("일간 수익률 변동성은 2.35%", answer)
        self.assertIn("연율화한 변동성은 37.30%", answer)
        self.assertNotIn("종가 표준편차", answer)


if __name__ == "__main__":
    unittest.main()
