import unittest
from unittest.mock import patch

from llm_client import build_final_answer
from main_agent import select_tool
from tools.industry_rank_tool import (
    _extract_industry,
    _query_industry_candidates,
    rank_industry_companies,
)
from company_data.financial_store import FinancialStatementStore


QUESTION = "기타 비금속 광물제품 제조업 업종에서 가장 매출액이 큰 기업 5개사를 알려줘"


class IndustryRankToolTest(unittest.TestCase):
    def test_question_routes_to_industry_rank_tool(self):
        self.assertEqual(select_tool(QUESTION), "industry_rank_tool")
        self.assertEqual(_extract_industry(QUESTION), "기타 비금속 광물제품 제조업")

    def test_industry_candidates_are_available_even_without_pl_rows(self):
        rows = _query_industry_candidates(
            FinancialStatementStore(), "기타 비금속 광물제품 제조업", 5
        )
        self.assertGreaterEqual(len(rows), 5)
        self.assertTrue(
            all(row["industry_name"] == "기타 비금속 광물제품 제조업" for row in rows)
        )

    def test_rank_falls_back_to_dart_revenue(self):
        revenues = {
            "HC보광산업": 5,
            "SG": 4,
            "동국알앤에스": 3,
            "벽산": 10,
            "삼표시멘트": 9,
            "쎄노텍": 2,
            "제일연마": 1,
            "티씨케이": 8,
            "한국석유공업": 7,
        }
        with patch("tools.industry_rank_tool.load_dart_api_key", return_value="key"), patch(
            "tools.industry_rank_tool._dart_revenue",
            side_effect=lambda _code, name, _year: revenues.get(name),
        ):
            result = rank_industry_companies(QUESTION)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["revenue_source"], "dart")
        self.assertEqual(
            [row["company_name"] for row in result["ranking"]],
            ["벽산", "삼표시멘트", "티씨케이", "한국석유공업", "HC보광산업"],
        )

    def test_industry_no_data_message_is_not_a_company_lookup_error(self):
        calculation = {
            "status": "no_data",
            "industry": "기타 비금속 광물제품 제조업",
            "summary": "기타 비금속 광물제품 제조업 관련 기업 목록을 찾지 못했습니다.",
        }
        answer = build_final_answer(QUESTION, "industry_rank_tool", calculation, [])
        self.assertEqual(answer, calculation["summary"])
        self.assertNotIn("해당 기업의 재무 데이터", answer)


if __name__ == "__main__":
    unittest.main()
