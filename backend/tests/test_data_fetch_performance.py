import time
import unittest
from dataclasses import dataclass
from unittest.mock import patch

import numpy as np
import pandas as pd

from tools.company_trend_tool import Period, _fill_missing_series_with_dart
from tools.portfolio_tool import calculate_optimal_portfolio
from tools.valuation_tool import calculate_market_ratio_trend


@dataclass
class Company:
    company_name: str
    stock_code: str
    market: str = "코스닥시장상장법인"


class DataFetchPerformanceTest(unittest.TestCase):
    def test_one_dart_response_fills_three_comparative_years(self):
        company = Company("태양", "053620")
        series = [{"year": year} for year in (2023, 2024, 2025)]
        dart_rows = [
            {
                "sj_div": "CIS",
                "account_nm": "매출액",
                "thstrm_amount": "100",
                "frmtrm_amount": "90",
                "bfefrmtrm_amount": "80",
            },
            {
                "sj_div": "CIS",
                "account_nm": "영업이익",
                "thstrm_amount": "10",
                "frmtrm_amount": "9",
                "bfefrmtrm_amount": "8",
            },
        ]

        with patch("tools.company_trend_tool.load_dart_api_key", return_value="key"), patch(
            "tools.company_trend_tool.DartClient.fetch_financial_accounts",
            return_value={"status": "ok", "accounts": dart_rows},
        ) as fetch:
            result = _fill_missing_series_with_dart(
                company,
                ["revenue", "operating_income"],
                series,
                Period(2023, 2025, "최근 3개년"),
            )

        self.assertEqual(fetch.call_count, 1)
        self.assertEqual([row["revenue"]["amount"] for row in result], [80.0, 90.0, 100.0])
        self.assertEqual([row["operating_income"]["amount"] for row in result], [8.0, 9.0, 10.0])

    def test_portfolio_price_downloads_run_concurrently(self):
        companies = [Company("삼성전자", "005930"), Company("SK하이닉스", "000660"), Company("LG에너지솔루션", "373220")]
        index = pd.bdate_range(end="2026-07-14", periods=400)

        class Store:
            def resolve_company(self, query):
                return next((company for company in companies if company.company_name in query), None)

        def slow_download(*_args, **_kwargs):
            time.sleep(0.12)
            prices = 100 * np.exp(np.linspace(0, 0.2, len(index)))
            return pd.DataFrame({"Close": prices}, index=index)

        started = time.perf_counter()
        with patch("company_data.financial_store.FinancialStatementStore", return_value=Store()), patch(
            "tools.stock_price_tool._download_price_data", side_effect=slow_download
        ):
            result = calculate_optimal_portfolio(
                "삼성전자·SK하이닉스·LG에너지솔루션의 최근 5년 주가를 이용해 최대 샤프지수 포트폴리오와 최소분산 포트폴리오를 구성해줘."
            )
        elapsed = time.perf_counter() - started

        self.assertEqual(result["status"], "ok")
        self.assertLess(elapsed, 0.28)

    def test_per_trend_uses_dart_when_local_net_income_is_missing(self):
        company = Company("유한양행", "000100", "유가증권시장상장법인")

        class Store:
            def resolve_company(self, _query):
                return company

            def available_years(self, _stock_code):
                return [2024, 2025]

            def get_account_series(self, *_args):
                return [{"year": 2024, "net_income": None}, {"year": 2025, "net_income": None}]

        enriched = [
            {"year": 2024, "net_income": {"label": "당기순이익", "amount": 100.0}},
            {"year": 2025, "net_income": {"label": "당기순이익", "amount": 200.0}},
        ]
        with patch("tools.valuation_tool.FinancialStatementStore", return_value=Store()), patch(
            "tools.company_trend_tool._fill_missing_series_with_dart", return_value=enriched
        ) as dart_fallback, patch("tools.valuation_tool._fetch_listed_shares", return_value=10.0), patch(
            "tools.valuation_tool._fetch_year_end_close", side_effect=[1_000.0, 1_200.0]
        ):
            result = calculate_market_ratio_trend("유한양행의 최근 2개년 PER 추이를 계산해줘")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(dart_fallback.call_count, 1)
        self.assertEqual([row["ratios"]["per"]["value"] for row in result["market_ratio_series"]], [100.0, 60.0])


if __name__ == "__main__":
    unittest.main()
