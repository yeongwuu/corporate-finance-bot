from __future__ import annotations

import re
from typing import Any

from company_data.financial_store import FinancialStatementStore


MAJOR_ACCOUNT_ORDER = [
    "revenue",
    "operating_income",
    "net_income",
    "total_assets",
    "current_assets",
    "cash",
    "receivables",
    "inventories",
    "total_liabilities",
    "total_equity",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
]

RATIO_LABELS = {
    "revenue_growth": "매출 성장률",
    "operating_margin": "영업이익률",
    "net_margin": "순이익률",
    "debt_to_equity": "부채비율",
    "current_ratio": "유동비율",
    "cfo_to_net_income": "영업현금흐름/순이익",
}


def analyze_company_financials(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    year = _extract_year(question)

    try:
        result = store.get_major_accounts(question, year=year)
    except FileNotFoundError as exc:
        return {
            "status": "missing_data",
            "summary": "KOSDAQ_financial_statements.xlsx 파일을 찾지 못했습니다.",
            "steps": [str(exc)],
        }

    if result["status"] != "ok":
        steps = [result["message"]]
        if result.get("examples"):
            sample = ", ".join(f"{row['company_name']}({row['stock_code']})" for row in result["examples"][:5])
            steps.append(f"조회 가능한 회사 예시: {sample}")
        if result.get("available_years"):
            steps.append(f"가용 연도: {', '.join(map(str, result['available_years']))}")
        return {"status": result["status"], "summary": result["message"], "steps": steps}

    company = result["company"]
    year = result["year"]
    accounts = result["accounts"]
    ratios = result["ratios"]

    steps = [
        f"데이터 원천: KOSDAQ_financial_statements.xlsx -> backend/data/financials.sqlite 캐시",
        f"조회 대상: {company['company_name']}({company['stock_code']}), {year}년 당기 기준",
    ]
    if company.get("market") or company.get("industry_name"):
        steps.append(f"시장/업종: {company.get('market') or '-'} / {company.get('industry_name') or '-'}")

    account_lines = _format_major_accounts(accounts)
    if account_lines:
        steps.append("주요계정: " + " | ".join(account_lines))

    ratio_lines = _format_ratios(ratios)
    if ratio_lines:
        steps.append("간단 분석: " + " | ".join(ratio_lines))

    summary = f"{company['company_name']}의 {year}년 주요 재무계정을 조회했습니다."
    if ratio_lines:
        summary += " 매출성장률, 수익성, 안정성, 현금흐름 지표까지 함께 계산했습니다."

    return {
        "status": "ok",
        "summary": summary,
        "steps": steps,
        "company": company,
        "year": year,
        "accounts": accounts,
        "ratios": ratios,
    }


def _extract_year(question: str) -> int | None:
    match = re.search(r"(20[1-2]\d)", question)
    return int(match.group(1)) if match else None


def _format_major_accounts(accounts: dict[str, Any]) -> list[str]:
    lines = []
    for key in MAJOR_ACCOUNT_ORDER:
        account = accounts.get(key)
        if not account:
            continue
        lines.append(f"{account['label']} {_format_amount(account['amount'])}")
    return lines


def _format_ratios(ratios: dict[str, float | None]) -> list[str]:
    lines = []
    for key, label in RATIO_LABELS.items():
        value = ratios.get(key)
        if value is None:
            continue
        lines.append(f"{label} {_format_ratio(value)}")
    return lines


def _format_amount(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1_0000_0000_0000:
        return f"{sign}{amount / 1_0000_0000_0000:.2f}조원"
    if amount >= 1_0000_0000:
        return f"{sign}{amount / 1_0000_0000:.2f}억원"
    if amount >= 10_000:
        return f"{sign}{amount / 10_000:.2f}만원"
    return f"{sign}{amount:,.0f}원"


def _format_ratio(value: float) -> str:
    return f"{value * 100:.2f}%"
