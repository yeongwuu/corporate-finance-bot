import unittest
from dataclasses import dataclass
from unittest.mock import patch

import numpy as np
import pandas as pd

from llm_client import build_arima_stock_forecast_answer
from tools.stock_price_tool import predict_stock_price_arima


@dataclass
class Company:
    company_name: str = "테스트기업"
    stock_code: str = "005930"
    market: str = "KOSPI"
    industry_name: str = "테스트"


class StockPriceForecastTest(unittest.TestCase):
    def test_arima_forecast_returns_intervals_and_validation(self):
        rng = np.random.default_rng(42)
        index = pd.bdate_range(end="2026-07-14", periods=260)
        prices = 70_000 * np.exp(np.cumsum(rng.normal(0.0002, 0.012, len(index))))
        frame = pd.DataFrame({"Close": prices}, index=index)

        with patch("tools.stock_price_tool._download_price_data", return_value=frame):
            result = predict_stock_price_arima(
                "테스트기업의 최근 2년 주가로 3일 뒤 주가를 예측해줘",
                Company(),
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mode"], "arima_stock_forecast")
        self.assertEqual(len(result["forecast_values"]), 3)
        self.assertEqual(len(result["forecast_lower"]), 3)
        self.assertEqual(len(result["forecast_upper"]), 3)
        self.assertIn(result["model_name"].split("(")[0], {"ARIMA", "랜덤워크"})
        self.assertIn("arima_test_mae", result)
        self.assertIn("naive_test_mae", result)

        answer = build_arima_stock_forecast_answer(result)
        self.assertIn("95% 예측구간", answer)
        self.assertIn("랜덤워크 MAE", answer)


if __name__ == "__main__":
    unittest.main()
