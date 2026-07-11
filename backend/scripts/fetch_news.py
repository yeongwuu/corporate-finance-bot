import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from news_client import NewsClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch news search results and save them for local RAG.")
    parser.add_argument("query", help="Search query, e.g. 삼성전자 반도체 매출")
    parser.add_argument("--company-name", help="Company name for saved RAG metadata")
    parser.add_argument("--display", type=int, default=10)
    args = parser.parse_args()

    try:
        result = NewsClient().save_news_for_rag(args.query, company_name=args.company_name, display=args.display)
    except Exception as exc:
        print(f"error: {exc}")
        return
    print(result)


if __name__ == "__main__":
    main()
