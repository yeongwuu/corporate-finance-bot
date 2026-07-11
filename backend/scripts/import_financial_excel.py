import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company_data.financial_store import FinancialStatementStore


def main() -> None:
    store = FinancialStatementStore()
    store.ensure_database()
    print(f"Imported financial statements into {store.db_path}")


if __name__ == "__main__":
    main()
