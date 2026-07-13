from __future__ import annotations

import re
from typing import Any

from company_data.financial_store import FinancialStatementStore
from dart_client import DartClient, load_dart_api_key
from news_client import NewsClient, get_env as get_news_env
from rag.external_rag import search_external_docs


MAJOR_ACCOUNT_ORDER = [
    "revenue",
    "cost_of_sales",
    "gross_profit",
    "selling_admin_expenses",
    "operating_income",
    "net_income",
    "total_assets",
    "current_assets",
    "current_liabilities",
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
            "summary": "KOSPI_financial_statements.xlsx 파일을 찾지 못했습니다.",
            "steps": [str(exc)],
        }

    if result["status"] != "ok":
        dart_result = _try_fetch_dart_accounts(result, year)
        if dart_result:
            return dart_result
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
        f"데이터 원천: KOSPI_financial_statements.xlsx -> backend/data/financials.sqlite 캐시",
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

    news_fetch_result = _try_fetch_company_news(company, question) if _should_fetch_company_news(question) else None
    external_references = []
    if news_fetch_result and news_fetch_result.get("status") == "ok":
        external_references = _news_documents_only(search_external_docs(_news_query(company["company_name"], question), company["company_name"], limit=10))[:5]
        if external_references:
            steps.append("뉴스에서 확인되는 내용: " + " | ".join(f"{doc['title']}: {doc['snippet']}" for doc in external_references[:3]))
    elif news_fetch_result:
        steps.append(f"뉴스 수집: {news_fetch_result.get('message', '뉴스 수집에 실패했습니다.')}")

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
        "external_references": external_references,
        "news_fetch": news_fetch_result,
    }


def _extract_year(question: str) -> int | None:
    match = re.search(r"(20[1-2]\d)", question)
    return int(match.group(1)) if match else None


def _try_fetch_dart_accounts(result: dict[str, Any], requested_year: int | None) -> dict[str, Any] | None:
    if result.get("status") != "no_data" or not load_dart_api_key():
        return None
    company = result.get("company") or {}
    fiscal_year = requested_year or max(result.get("available_years") or [2025])
    try:
        dart_result = DartClient().fetch_financial_accounts(
            stock_code=company.get("stock_code"),
            corp_name=company.get("company_name"),
            fiscal_year=fiscal_year,
        )
    except Exception:
        return None
    if dart_result.get("status") != "ok":
        return None

    accounts = _map_dart_accounts(dart_result.get("accounts") or [])
    steps = [
        f"DART 즉시 조회: {company.get('company_name')} {fiscal_year}년 사업보고서 계정을 조회했습니다.",
        "주요계정: " + " | ".join(_format_major_accounts(accounts)),
    ]
    return {
        "status": "ok",
        "summary": f"{company.get('company_name')}의 {fiscal_year}년 주요 재무계정을 DART에서 즉시 조회했습니다.",
        "steps": steps,
        "company": company,
        "year": fiscal_year,
        "accounts": accounts,
        "ratios": _calculate_basic_ratios(accounts),
        "source": "dart",
    }


def _map_dart_accounts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rules = {
        "revenue": ("매출액", ["매출", "매출액", "영업수익", "수익(매출액)"]),
        "cost_of_sales": ("매출원가", ["매출원가"]),
        "gross_profit": ("매출총이익", ["매출총이익", "매출총이익(손실)"]),
        "selling_admin_expenses": ("판매비와관리비", ["판매비와관리비", "판매비와 관리비", "판매비및관리비", "판매 및 일반관리비"]),
        "operating_income": ("영업이익", ["영업이익", "영업이익(손실)"]),
        "net_income": ("당기순이익", ["당기순이익", "당기순이익(손실)"]),
        "total_assets": ("자산총계", ["자산총계", "자산 총계"]),
        "current_assets": ("유동자산", ["유동자산"]),
        "current_liabilities": ("유동부채", ["유동부채"]),
        "total_liabilities": ("부채총계", ["부채총계", "부채 총계"]),
        "total_equity": ("자본총계", ["자본총계", "자본 총계", "자본합계"]),
    }
    accounts = {}
    for key, (label, names) in rules.items():
        row = _find_dart_row(rows, names)
        if row:
            accounts[key] = {"label": label, "amount": _parse_dart_amount(row.get("thstrm_amount"))}
    return accounts


def _find_dart_row(rows: list[dict[str, Any]], names: list[str]) -> dict[str, Any] | None:
    for row in rows:
        account_name = str(row.get("account_nm") or "").strip()
        statement = str(row.get("sj_div") or "").strip()
        if statement not in {"BS", "IS", "CIS"}:
            continue
        if account_name in names:
            return row
    for row in rows:
        account_name = str(row.get("account_nm") or "").strip()
        if any(name in account_name for name in names):
            return row
    return None


def _parse_dart_amount(value: Any) -> float:
    if value is None:
        return 0.0
    cleaned = re.sub(r"[^0-9.-]", "", str(value))
    return float(cleaned) if cleaned else 0.0


def _calculate_basic_ratios(accounts: dict[str, Any]) -> dict[str, float | None]:
    def amount(key: str) -> float | None:
        item = accounts.get(key)
        return item.get("amount") if item else None

    revenue = amount("revenue")
    operating_income = amount("operating_income")
    net_income = amount("net_income")
    cost_of_sales = amount("cost_of_sales")
    selling_admin_expenses = amount("selling_admin_expenses")
    total_liabilities = amount("total_liabilities")
    total_equity = amount("total_equity")
    current_assets = amount("current_assets")
    current_liabilities = amount("current_liabilities")
    return {
        "cost_of_sales_ratio": _safe_divide(cost_of_sales, revenue),
        "selling_admin_expense_ratio": _safe_divide(selling_admin_expenses, revenue),
        "operating_margin": _safe_divide(operating_income, revenue),
        "net_margin": _safe_divide(net_income, revenue),
        "debt_to_equity": _safe_divide(total_liabilities, total_equity),
        "current_ratio": _safe_divide(current_assets, current_liabilities),
    }


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


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


def _try_fetch_company_news(company: dict[str, Any], question: str) -> dict[str, Any] | None:
    if not (get_news_env("NAVER_CLIENT_ID") and get_news_env("NAVER_CLIENT_SECRET")):
        return {
            "status": "missing_config",
            "message": "뉴스 근거 수집에는 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET 설정이 필요합니다.",
        }
    query = _news_query(company.get("company_name"), question)
    try:
        result = NewsClient().save_news_for_rag(query, company_name=company.get("company_name"), display=10)
        result["query"] = query
        return result
    except Exception:
        return {
            "status": "error",
            "message": "뉴스 API 호출에 실패했습니다. 배포 환경의 NAVER_CLIENT_ID/NAVER_CLIENT_SECRET 설정과 외부 네트워크 연결을 확인해야 합니다.",
            "query": query,
        }


def _should_fetch_company_news(question: str) -> bool:
    lowered = question.lower()
    return any(
        token in lowered
        for token in [
            "뉴스",
            "기사",
            "이슈",
            "시장 반응",
            "업황",
            "원인",
            "이유",
            "배경",
            "호재",
            "악재",
            "전망",
            "동향",
            "잠정실적",
            "분기실적",
            "최신 분기",
            "최근 분기",
        ]
    )


def _news_query(company_name: str | None, question: str) -> str:
    cleaned = question
    # Remove postpositions and particles (의, 을, 를, 이, 가, 은, 는, 에, 에 대한 등)
    cleaned = re.sub(r"(?:의|을|를|이|가|은|는|에|에\s*대한|에\s*대해|관한|관해)\s+", " ", cleaned)
    # Remove common conversational verbs and polite endings (알려줘, 설명해줘, 분석해줘 등)
    cleaned = re.sub(r"(?:알려줘|알려줘요|알려주세요|설명해줘|설명해줘요|설명해주세요|분석해줘|분석해줘요|분석해주세요|알려|설명|분석|요구|요청|제공)\b.*", "", cleaned)
    # Remove punctuation
    cleaned = re.sub(r"[?.,!]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if company_name and company_name not in cleaned:
        cleaned = f"{company_name} {cleaned}"
    return cleaned


def _news_documents_only(documents: list[dict]) -> list[dict]:
    return [doc for doc in documents if str(doc.get("title", "")).startswith("news_")]
