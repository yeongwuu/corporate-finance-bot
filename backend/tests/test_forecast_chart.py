import unittest

from chart_builder import build_chart_spec


class ForecastChartTest(unittest.TestCase):
    def setUp(self):
        self.calculation = {
            "status": "ok",
            "company": {"company_name": "엔켐"},
            "account_label": "영업이익",
            "target_year": 2026,
            "series": [
                {"year": 2023, "amount": 5_120_000_000},
                {"year": 2024, "amount": -50_360_000_000},
                {"year": 2025, "amount": -78_390_000_000},
            ],
            "forecast": {
                "low": -124_720_000_000,
                "base": -78_390_000_000,
                "high": 233_780_000_000,
            },
        }

    def test_forecast_scenarios_branch_from_last_actual_year(self):
        chart = build_chart_spec("forecast_tool", self.calculation)
        self.assertEqual([dataset["key"] for dataset in chart["datasets"]], [
            "actual", "low_forecast", "base_forecast", "high_forecast"
        ])
        for dataset in chart["datasets"][1:]:
            self.assertEqual(len(dataset["points"]), 2)
            self.assertEqual(dataset["points"][0]["label"], "2025년")
            self.assertEqual(dataset["points"][-1]["label"], "2026년")
        self.assertEqual(chart["datasets"][1]["points"][-1]["y"], self.calculation["forecast"]["low"])
        self.assertEqual(chart["datasets"][2]["points"][-1]["y"], self.calculation["forecast"]["base"])
        self.assertEqual(chart["datasets"][3]["points"][-1]["y"], self.calculation["forecast"]["high"])

    def test_base_forecast_uses_shared_second_bar_color(self):
        chart = build_chart_spec("forecast_tool", self.calculation)
        base = next(dataset for dataset in chart["datasets"] if dataset["key"] == "base_forecast")
        self.assertEqual(base["color"], "#E59A2F")


if __name__ == "__main__":
    unittest.main()
