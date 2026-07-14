import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from tools.stock_price_tool import compare_stock_prices


class StockPriceComparisonTest(unittest.TestCase):
    @patch("tools.stock_price_tool._download_naver_price_data")
    def test_comparison_uses_backtest_max_and_min_close_keys(self, download):
        download.return_value = pd.DataFrame(
            {"Close": [100.0, 120.0, 90.0, 110.0]},
            index=pd.to_datetime(["2025-01-02", "2025-02-03", "2025-03-04", "2025-04-01"]),
        )
        companies = [
            SimpleNamespace(company_name="삼성물산", stock_code="028260", market="KOSPI"),
            SimpleNamespace(company_name="에코프로", stock_code="086520", market="KOSDAQ"),
        ]

        result = compare_stock_prices("삼성물산과 에코프로의 최근 2년 주가 흐름을 비교해줘", companies)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["comparison"]), 2)
        self.assertTrue(any("최고/최저 120원 / 90원" in step for step in result["steps"]))


if __name__ == "__main__":
    unittest.main()
