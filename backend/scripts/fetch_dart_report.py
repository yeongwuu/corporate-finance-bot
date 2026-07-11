import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_client import DartClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a DART business report and save it for local RAG.")
    parser.add_argument("--stock-code", help="6-digit stock code, e.g. 005930")
    parser.add_argument("--corp-name", help="Company name, e.g. 삼성전자")
    parser.add_argument("--year", type=int, help="Fiscal year, e.g. 2024")
    args = parser.parse_args()

    if not args.stock_code and not args.corp_name:
        parser.error("--stock-code 또는 --corp-name 중 하나는 필요합니다.")

    try:
        result = DartClient().save_business_report_for_rag(
            stock_code=args.stock_code,
            corp_name=args.corp_name,
            fiscal_year=args.year,
        )
    except ValueError as exc:
        print(f"error: {exc}")
        return
    print(result)


if __name__ == "__main__":
    main()
