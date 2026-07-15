import unittest

from tools.company_trend_tool import _extract_peer_industry


class IndustryNameParsingTest(unittest.TestCase):
    def test_long_industry_name_is_preserved(self):
        question = "컴퓨터 프로그래밍, 시스템 통합 및 관리업 산업 대표 기업의 매출을 비교해줘"
        self.assertEqual(
            _extract_peer_industry(question, None),
            "컴퓨터 프로그래밍, 시스템 통합 및 관리업",
        )


if __name__ == "__main__":
    unittest.main()
