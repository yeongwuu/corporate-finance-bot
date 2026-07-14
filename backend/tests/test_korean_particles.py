import unittest

from korean_particles import has_final_consonant, normalize_company_pair_particles, with_particle


class KoreanParticlesTest(unittest.TestCase):
    def test_hangul_final_consonant(self):
        self.assertTrue(has_final_consonant("삼성물산"))
        self.assertFalse(has_final_consonant("에코프로"))
        self.assertEqual(with_particle("삼성물산", "과", "와"), "삼성물산과")
        self.assertEqual(with_particle("삼성전자", "과", "와"), "삼성전자와")

    def test_non_hangul_company_override(self):
        self.assertEqual(with_particle("S-Oil", "과", "와"), "S-Oil과")

    def test_normalize_company_pair_question(self):
        self.assertEqual(
            normalize_company_pair_particles("삼성물산와 에코프로의 최근 2년 주가 흐름을 비교해줘"),
            "삼성물산과 에코프로의 최근 2년 주가 흐름을 비교해줘",
        )
        self.assertEqual(
            normalize_company_pair_particles("삼성전자와 SK하이닉스의 최근 2년 주가 흐름을 비교해줘"),
            "삼성전자와 SK하이닉스의 최근 2년 주가 흐름을 비교해줘",
        )


if __name__ == "__main__":
    unittest.main()
