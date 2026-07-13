from __future__ import annotations

import json
import re
import sqlite3
import gzip
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCEL_PATH = PROJECT_ROOT / "KOSPI_financial_statements.xlsx"
DEFAULT_DB_PATH = BACKEND_ROOT / "data" / "financials.sqlite"
DEFAULT_PACKAGED_DB_PATH = BACKEND_ROOT / "data" / "financials.sqlite.gz"
ACCOUNT_MAPPING_PATH = BACKEND_ROOT / "data" / "account_mapping.json"

META_COLUMNS = [
    "재무제표종류",
    "종목코드",
    "회사명",
    "시장구분",
    "업종",
    "업종명",
    "결산월",
    "결산기준일",
    "보고서종류",
    "통화",
    "항목코드",
    "항목명",
]


@dataclass(frozen=True)
class CompanyMatch:
    stock_code: str
    company_name: str
    market: str | None
    industry_name: str | None
    latest_year: int


class FinancialStatementStore:
    def __init__(
        self,
        excel_path: Path = DEFAULT_EXCEL_PATH,
        db_path: Path = DEFAULT_DB_PATH,
        mapping_path: Path = ACCOUNT_MAPPING_PATH,
        packaged_db_path: Path = DEFAULT_PACKAGED_DB_PATH,
    ) -> None:
        self.excel_path = excel_path
        self.db_path = db_path
        self.mapping_path = mapping_path
        self.packaged_db_path = packaged_db_path

    def ensure_database(self) -> None:
        database_is_usable = self._database_is_usable()
        if database_is_usable and (not self.excel_path.exists() or self._database_is_fresh()):
            return
        if not database_is_usable and self._restore_packaged_database() and self._database_is_usable():
            return
        if not self.excel_path.exists():
            raise FileNotFoundError(f"Usable financial database and Excel source not found: {self.excel_path}")

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.db_path.with_suffix(".sqlite.tmp")
        if tmp_path.exists():
            tmp_path.unlink()

        conn = sqlite3.connect(tmp_path)
        try:
            self._import_excel(conn)
            self._create_indexes(conn)
            conn.commit()
        finally:
            conn.close()

        tmp_path.replace(self.db_path)
        if not self._database_is_usable():
            raise RuntimeError("financial_items table was not created")

    def search_companies(self, query: str, limit: int = 10) -> list[CompanyMatch]:
        self.ensure_database()
        compact_query = _compact(query)
        code = _extract_stock_code(query)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if code:
                rows = conn.execute(
                    """
                    SELECT stock_code, company_name, market, industry_name, MAX(fiscal_year) AS latest_year
                    FROM financial_items
                    WHERE stock_code = ?
                    GROUP BY stock_code, company_name
                    LIMIT ?
                    """,
                    (code, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT stock_code, company_name, market, industry_name, MAX(fiscal_year) AS latest_year
                    FROM financial_items
                    WHERE REPLACE(LOWER(company_name), ' ', '') LIKE ?
                    GROUP BY stock_code, company_name
                    ORDER BY latest_year DESC, company_name
                    LIMIT ?
                    """,
                    (f"%{compact_query}%", limit),
                ).fetchall()
        finally:
            conn.close()

        return [
            CompanyMatch(
                stock_code=row["stock_code"],
                company_name=row["company_name"],
                market=row["market"],
                industry_name=row["industry_name"],
                latest_year=int(row["latest_year"]),
            )
            for row in rows
        ]

    def get_major_accounts(self, company_query: str, year: int | None = None) -> dict[str, Any]:
        self.ensure_database()
        company = self._resolve_company(company_query)
        if not company:
            return {
                "status": "needs_company",
                "message": "엑셀 데이터에서 회사명을 찾지 못했습니다. 회사명 또는 6자리 종목코드를 함께 입력해 주세요.",
                "examples": self._sample_companies(),
            }

        fiscal_year = year or company.latest_year
        rows = self._load_company_year_rows(company.stock_code, fiscal_year)
        if not rows:
            return {
                "status": "no_data",
                "message": f"{company.company_name}의 {fiscal_year}년 당기 재무제표 데이터를 찾지 못했습니다.",
                "company": company.__dict__,
                "available_years": self._available_years(company.stock_code),
            }

        previous_rows = self._load_company_year_rows(company.stock_code, fiscal_year - 1)
        mapping = self._load_mapping()
        accounts = {
            account_key: self._pick_account(rows, rule)
            for account_key, rule in mapping.items()
        }
        previous_accounts = {
            account_key: self._pick_account(previous_rows, rule)
            for account_key, rule in mapping.items()
        }

        return {
            "status": "ok",
            "company": company.__dict__,
            "year": fiscal_year,
            "accounts": accounts,
            "previous_year": fiscal_year - 1 if previous_rows else None,
            "previous_accounts": previous_accounts if previous_rows else {},
            "ratios": _calculate_ratios(accounts, previous_accounts if previous_rows else {}),
        }

    def resolve_company(self, query: str) -> CompanyMatch | None:
        self.ensure_database()
        return self._resolve_company(query)

    def available_years(self, stock_code: str) -> list[int]:
        self.ensure_database()
        return self._available_years(stock_code)

    def get_account_series(
        self,
        stock_code: str,
        account_keys: list[str],
        start_year: int,
        end_year: int,
    ) -> list[dict[str, Any]]:
        self.ensure_database()
        mapping = self._load_mapping()
        rows = []
        for fiscal_year in range(start_year, end_year + 1):
            year_rows = self._load_company_year_rows(stock_code, fiscal_year)
            if not year_rows:
                continue
            row: dict[str, Any] = {"year": fiscal_year}
            for account_key in account_keys:
                rule = mapping.get(account_key)
                if not rule:
                    continue
                row[account_key] = self._pick_account(year_rows, rule)
            rows.append(row)
        return rows

    def _database_is_fresh(self) -> bool:
        return (
            self._database_is_usable()
            and self.excel_path.exists()
            and self.db_path.stat().st_mtime >= self.excel_path.stat().st_mtime
        )

    def _database_is_usable(self) -> bool:
        if not self.db_path.exists() or self.db_path.stat().st_size == 0:
            return False
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'financial_items'"
                ).fetchone()
                if not row:
                    return False
                return conn.execute("SELECT 1 FROM financial_items LIMIT 1").fetchone() is not None
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            return False

    def _restore_packaged_database(self) -> bool:
        if not self.packaged_db_path.exists():
            return False

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.db_path.with_suffix(".sqlite.tmp")
        if tmp_path.exists():
            tmp_path.unlink()

        with gzip.open(self.packaged_db_path, "rb") as src, tmp_path.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        tmp_path.replace(self.db_path)
        return True

    def _import_excel(self, conn: sqlite3.Connection) -> None:
        workbook = pd.ExcelFile(self.excel_path)
        for sheet_name in workbook.sheet_names:
            parsed = _parse_sheet_name(sheet_name)
            if not parsed:
                continue
            fiscal_year, statement_type = parsed
            if statement_type == "CE":
                continue
            frame = pd.read_excel(workbook, sheet_name=sheet_name)
            normalized = _normalize_sheet(frame, fiscal_year, statement_type)
            if normalized.empty:
                continue
            normalized.to_sql("financial_items", conn, if_exists="append", index=False)

    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_company_year ON financial_items(stock_code, fiscal_year)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_name ON financial_items(company_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_account ON financial_items(statement_type, account_code, account_name)")

    def _resolve_company(self, query: str) -> CompanyMatch | None:
        code = _extract_stock_code(query)
        if code:
            matches = self.search_companies(code, limit=1)
            return matches[0] if matches else None

        compact_query = _compact(query)
        embedded = self._find_embedded_company(compact_query)
        if embedded:
            return embedded

        matches = self.search_companies(query, limit=5)
        if not matches:
            return None
        for match in matches:
            if _compact(match.company_name) == compact_query:
                return match
        return matches[0]

    def _find_embedded_company(self, compact_query: str) -> CompanyMatch | None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT stock_code, company_name, market, industry_name, MAX(fiscal_year) AS latest_year
                FROM financial_items
                GROUP BY stock_code, company_name
                """
            ).fetchall()
        finally:
            conn.close()

        candidates = []
        for row in rows:
            company_key = _compact(row["company_name"])
            if company_key and company_key in compact_query:
                candidates.append(row)
        if not candidates:
            return None
        row = max(candidates, key=lambda item: len(_compact(item["company_name"])))
        return CompanyMatch(
            stock_code=row["stock_code"],
            company_name=row["company_name"],
            market=row["market"],
            industry_name=row["industry_name"],
            latest_year=int(row["latest_year"]),
        )

    def _sample_companies(self) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT stock_code, company_name, market, MAX(fiscal_year) AS latest_year
                FROM financial_items
                GROUP BY stock_code, company_name
                ORDER BY latest_year DESC, company_name
                LIMIT 8
                """
            ).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]

    def _available_years(self, stock_code: str) -> list[int]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT fiscal_year FROM financial_items WHERE stock_code = ? ORDER BY fiscal_year",
                (stock_code,),
            ).fetchall()
        finally:
            conn.close()
        return [int(row[0]) for row in rows]

    def get_peers_in_industry(self, industry_name: str, exclude_code: str, limit: int = 3) -> list[dict[str, Any]]:
        self.ensure_database()
        if not industry_name:
            return []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT stock_code, company_name, COUNT(*) as data_count
                FROM financial_items
                WHERE industry_name = ? AND stock_code != ?
                GROUP BY stock_code, company_name
                ORDER BY data_count DESC, company_name
                LIMIT ?
                """,
                (industry_name, exclude_code, limit),
            ).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]

    def _load_company_year_rows(self, stock_code: str, fiscal_year: int) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM financial_items
                WHERE stock_code = ? AND fiscal_year = ?
                """,
                (stock_code, fiscal_year),
            ).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]

    def _load_mapping(self) -> dict[str, Any]:
        return json.loads(self.mapping_path.read_text(encoding="utf-8"))

    def _pick_account(self, rows: list[dict[str, Any]], rule: dict[str, Any]) -> dict[str, Any] | None:
        candidates = [
            row
            for row in rows
            if row["statement_type"] in set(rule.get("statements", []))
        ]
        if not candidates:
            return None

        code_exact = {_casefold(code) for code in rule.get("code_exact", [])}
        if code_exact:
            for row in candidates:
                if _casefold(row.get("account_code")) in code_exact:
                    return _account_result(row, rule["label"])

        for exact_name in rule.get("name_exact", []):
            for row in candidates:
                if _compact(row.get("account_name")) == _compact(exact_name):
                    return _account_result(row, rule["label"])

        for token in rule.get("name_contains", []):
            compact_token = _compact(token)
            for row in candidates:
                if compact_token in _compact(row.get("account_name")):
                    return _account_result(row, rule["label"])

        for token in rule.get("code_contains", []):
            token = _casefold(token)
            for row in candidates:
                if token in _casefold(row.get("account_code")):
                    return _account_result(row, rule["label"])

        return None


def _parse_sheet_name(sheet_name: str) -> tuple[int, str] | None:
    match = re.fullmatch(r"(\d{4})_(BS|PL|CF|CE)", sheet_name)
    if not match:
        return None
    return int(match.group(1)), match.group(2)


def _normalize_sheet(frame: pd.DataFrame, fiscal_year: int, statement_type: str) -> pd.DataFrame:
    if "항목명" not in frame.columns or "당기" not in frame.columns:
        return pd.DataFrame()

    columns = [column for column in META_COLUMNS + ["당기"] if column in frame.columns]
    normalized = frame.loc[:, columns].copy()
    normalized["amount"] = pd.to_numeric(normalized["당기"], errors="coerce")
    normalized = normalized.dropna(subset=["amount", "항목명", "회사명"])
    if normalized.empty:
        return pd.DataFrame()

    normalized["fiscal_year"] = fiscal_year
    normalized["statement_type"] = statement_type
    normalized["stock_code"] = _optional_column(normalized, "종목코드").map(_normalize_stock_code)
    normalized["company_name"] = normalized["회사명"].astype(str).str.strip()
    normalized["market"] = _optional_column(normalized, "시장구분").astype(str).str.strip()
    normalized["industry_code"] = _optional_column(normalized, "업종").astype(str).str.strip()
    normalized["industry_name"] = _optional_column(normalized, "업종명").astype(str).str.strip()
    normalized["report_date"] = _optional_column(normalized, "결산기준일").astype(str).str.strip()
    normalized["report_type"] = _optional_column(normalized, "보고서종류").astype(str).str.strip()
    normalized["currency"] = _optional_column(normalized, "통화").astype(str).str.strip()
    normalized["account_code"] = _optional_column(normalized, "항목코드").astype(str).str.strip()
    normalized["account_name"] = normalized["항목명"].astype(str).str.strip()

    return normalized[
        [
            "fiscal_year",
            "statement_type",
            "stock_code",
            "company_name",
            "market",
            "industry_code",
            "industry_name",
            "report_date",
            "report_type",
            "currency",
            "account_code",
            "account_name",
            "amount",
        ]
    ]


def _optional_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series("", index=frame.index)


def _normalize_stock_code(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value))
    return digits.zfill(6) if digits else ""


def _extract_stock_code(query: str) -> str | None:
    match = re.search(r"\b\d{6}\b", query)
    return match.group(0) if match else None


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _casefold(value: Any) -> str:
    return str(value or "").strip().casefold()


def _account_result(row: dict[str, Any], label: str) -> dict[str, Any]:
    return {
        "label": label,
        "amount": float(row["amount"]),
        "statement_type": row["statement_type"],
        "account_name": row["account_name"],
        "account_code": row["account_code"],
        "currency": row["currency"],
    }


def _amount(account: dict[str, Any] | None) -> float | None:
    if not account:
        return None
    return account.get("amount")


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _calculate_ratios(accounts: dict[str, Any], previous_accounts: dict[str, Any]) -> dict[str, float | None]:
    revenue = _amount(accounts.get("revenue"))
    previous_revenue = _amount(previous_accounts.get("revenue"))
    operating_income = _amount(accounts.get("operating_income"))
    net_income = _amount(accounts.get("net_income"))
    cost_of_sales = _amount(accounts.get("cost_of_sales"))
    selling_admin_expenses = _amount(accounts.get("selling_admin_expenses"))
    total_liabilities = _amount(accounts.get("total_liabilities"))
    total_equity = _amount(accounts.get("total_equity"))
    current_assets = _amount(accounts.get("current_assets"))
    current_liabilities = _amount(accounts.get("current_liabilities"))
    operating_cash_flow = _amount(accounts.get("operating_cash_flow"))

    return {
        "revenue_growth": _safe_divide(revenue - previous_revenue, abs(previous_revenue)) if revenue is not None and previous_revenue not in (None, 0) else None,
        "cost_of_sales_ratio": _safe_divide(cost_of_sales, revenue),
        "selling_admin_expense_ratio": _safe_divide(selling_admin_expenses, revenue),
        "operating_margin": _safe_divide(operating_income, revenue),
        "net_margin": _safe_divide(net_income, revenue),
        "debt_to_equity": _safe_divide(total_liabilities, total_equity),
        "current_ratio": _safe_divide(current_assets, current_liabilities),
        "cfo_to_net_income": _safe_divide(operating_cash_flow, net_income),
    }
