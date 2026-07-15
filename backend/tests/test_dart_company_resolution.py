import unittest
from unittest.mock import patch

from dart_client import DartClient, DartCompany


class DartCompanyResolutionTest(unittest.TestCase):
    def test_mismatched_stock_code_falls_back_to_company_name(self):
        client = DartClient(api_key="test")
        companies = [
            DartCompany(corp_code="1", corp_name="두산", stock_code="000150", modify_date=""),
            DartCompany(corp_code="2", corp_name="페스카로", stock_code="999999", modify_date=""),
        ]
        with patch.object(client, "load_corp_codes", return_value=companies):
            company = client.find_company(stock_code="000150", corp_name="페스카로")

        self.assertIsNotNone(company)
        self.assertEqual(company.corp_name, "페스카로")
        self.assertEqual(company.stock_code, "999999")


if __name__ == "__main__":
    unittest.main()
