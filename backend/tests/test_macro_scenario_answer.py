import unittest

from llm_client import build_final_answer


class MacroScenarioAnswerTest(unittest.TestCase):
    def test_macro_scenario_does_not_turn_into_dcf_sensitivity_range(self):
        calculation = {
            "status": "ok",
            "mode": "macro_scenario",
            "company": {"company_name": "현대자동차"},
            "base_operating_income": 3_515_052_000_000.0,
            "scenario_operating_income": 3_690_016_196_479.0,
            "value_change": 0.0151,
            "scenario_price": None,
            "assumptions": {
                "rate_shock": 0.01,
                "fx_shock": 0.10,
                "debt_ratio": 0.29,
                "fx_elasticity": 0.55,
                "rate_elasticity": 0.52,
            },
        }

        answer = build_final_answer(
            "기준금리가 1%p 상승하고 원/달러 환율이 10% 오르면 현대차는 어떻게 변할까?",
            "advanced_analysis_tool",
            calculation,
            [],
        )

        self.assertIn("영업이익 3.52조원 → 3.69조원", answer)
        self.assertIn("적정가치 대용 변화율: +1.51%", answer)
        self.assertNotIn("7.0%~11.0%", answer)
        self.assertNotIn("240,544원", answer)


if __name__ == "__main__":
    unittest.main()
