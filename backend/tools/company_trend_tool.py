from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from company_data.financial_store import CompanyMatch, FinancialStatementStore
from dart_client import DartClient, load_dart_api_key
from news_client import NewsClient, get_env as get_news_env
from rag.external_rag import search_external_docs
from tools.company_analysis_tool import _format_amount, _format_ratio, _map_dart_accounts
from tools.industry_rank_tool import (
    REPRESENTATIVE_SECTOR_COMPANIES,
    resolve_representative_sector,
    select_representative_companies,
    _major_industry,
)


ACCOUNT_LABELS = {
    "revenue": "매출액",
    "gross_profit": "매출총이익",
    "cost_of_sales": "매출원가",
    "selling_admin_expenses": "판매비와관리비",
    "operating_income": "영업이익",
    "net_income": "당기순이익",
    "operating_cash_flow": "영업활동현금흐름",
    "total_assets": "자산총계",
    "total_liabilities": "부채총계",
    "total_equity": "자본총계",
}


PROFITABILITY_RATIO_DEFINITIONS = {
    "cost_of_sales_ratio": {
        "label": "매출원가율",
        "required": ["revenue", "cost_of_sales"],
    },
    "gross_margin": {
        "label": "매출총이익률",
        "required": ["revenue", "gross_profit"],
    },
    "selling_admin_expense_ratio": {
        "label": "판관비율",
        "required": ["revenue", "selling_admin_expenses"],
    },
    "operating_margin": {
        "label": "영업이익률",
        "required": ["revenue", "operating_income"],
    },
    "net_margin": {
        "label": "당기순이익률",
        "required": ["revenue", "net_income"],
    },
    "roa": {
        "label": "총자산이익률",
        "required": ["net_income", "total_assets"],
    },
    "roe": {
        "label": "자기자본이익률",
        "required": ["net_income", "total_equity"],
    },
    "operating_roa": {
        "label": "투하자본수익률",
        "required": ["operating_income", "total_assets"],
    },
    "current_ratio": {
        "label": "유동비율",
        "required": ["current_assets", "current_liabilities"],
    },
    "quick_ratio": {
        "label": "당좌비율",
        "required": ["current_assets", "current_liabilities", "inventories"],
    },
    "debt_ratio": {
        "label": "부채비율",
        "required": ["total_liabilities", "total_equity"],
    },
}


@dataclass(frozen=True)
class Period:
    start_year: int
    end_year: int
    source: str


def analyze_company_trend(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    news_requested = _should_fetch_news(question)
    try:
        if _asks_representative_industry_analysis(question):
            return _analyze_representative_industry_growth_comparison(question, store)
        comparison_companies = _resolve_comparison_companies(store, question) if _is_company_comparison_question(question) else []
        if _asks_industry_peer_growth_comparison(question) and len(comparison_companies) >= 1:
            return _analyze_industry_peer_growth_comparison(question, store, comparison_companies[0])
        if len(comparison_companies) >= 2:
            limit = 7 if _asks_defense_peer_group(question) else 3
            return _analyze_market_comparison(question, store, comparison_companies[:limit])
        company = store.resolve_company(question)
    except FileNotFoundError as exc:
        return {
            "status": "missing_data",
            "summary": "KRX_financial_statements.xlsx 파일을 찾지 못했습니다.",
            "steps": [str(exc)],
        }
    if not company:
        industry = _extract_peer_industry(question, None)
        if industry and industry != "산업" and any(word in question for word in ["성장률", "추이", "비교", "분석"]) and any(word in question for word in ["매출", "영업이익", "순이익"]):
            peers = _query_peer_companies(store, industry, None, limit=10)
            if peers:
                return _analyze_industry_peers_growth_direct(question, store, industry, peers)
        
        if industry and industry != "산업":
            news_fetch_result = None
            documents = []
            if get_news_env("NAVER_CLIENT_ID") and get_news_env("NAVER_CLIENT_SECRET"):
                query = f"{industry} 산업 동향"
                try:
                    news_fetch_result = NewsClient().save_news_for_rag(query, company_name=None, display=10)
                    news_fetch_result["query"] = query
                    if news_fetch_result.get("status") == "ok":
                        documents = _news_documents_only(search_external_docs(query, None, limit=10))[:5]
                except Exception as exc:
                    news_fetch_result = {"status": "error", "message": f"뉴스 API 호출 실패: {exc}"}
            else:
                news_fetch_result = {
                    "status": "missing_config",
                    "message": "산업 동향 확인에는 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET 설정이 필요합니다.",
                }

            if documents:
                steps = [
                    f"뉴스 검색 대상: {industry} 산업 동향",
                    "해당 산업의 최신 동향 관련 뉴스 근거를 확인했습니다.",
                    "뉴스에서 확인되는 내용: " + " | ".join(f"{doc['title']}: {doc['snippet']}" for doc in documents[:3])
                ]
                return {
                    "status": "latest_news",
                    "summary": f"{industry} 산업의 최근 동향 관련 뉴스 근거를 확인했습니다.",
                    "steps": steps,
                    "industry": industry,
                    "external_references": documents,
                    "news_fetch": news_fetch_result,
                }

        return {
            "status": "needs_company",
            "summary": "회사명 또는 6자리 종목코드를 찾지 못했습니다.",
            "steps": ["예: 삼성전자 2019~2024 매출 추이 분석, 005930 최근 5개년 영업이익 추이"],
        }

    available_years = store.available_years(company.stock_code)
    if not available_years:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 가용 연도 데이터가 없습니다.",
            "steps": [],
        }

    if _asks_latest_quarter(question):
        latest_year = max(available_years)
        news_fetch_result = None
        documents = []
        if get_news_env("NAVER_CLIENT_ID") and get_news_env("NAVER_CLIENT_SECRET"):
            news_fetch_result = _try_fetch_latest_quarter_news(company, question)
            if news_fetch_result.get("status") == "ok":
                documents = _news_documents_only(
                    search_external_docs(news_fetch_result.get("query", question), company.company_name, limit=10)
                )[:5]
        else:
            news_fetch_result = {
                "status": "missing_config",
                "message": "최신 분기 실적 확인에는 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET 설정이 필요합니다.",
            }
        if documents:
            steps = [
                f"뉴스 검색 대상: {company.company_name}",
                "최신 분기 실적은 보유 엑셀 데이터가 아니라 뉴스/공시 근거를 우선 확인했습니다.",
                "뉴스에서 확인되는 내용: " + " | ".join(f"{doc['title']}: {doc['snippet']}" for doc in documents[:5]),
            ]
            return {
                "status": "latest_news",
                "summary": f"{company.company_name}의 최신 분기 실적 관련 뉴스 근거를 확인했습니다.",
                "steps": steps,
                "company": company.__dict__,
                "external_references": documents,
                "news_fetch": news_fetch_result,
            }
        return {
            "status": "needs_latest_disclosure",
            "summary": (
                f"현재 보유한 재무제표 데이터는 {latest_year}년 연간 데이터까지라서 "
                f"{company.company_name}의 가장 최근 분기 영업이익은 직접 확인할 수 없습니다."
            ),
            "steps": [
                "가장 최신의 정확한 분기 실적은 DART의 잠정실적 공시, 분기보고서 또는 회사 IR 실적 발표 자료에서 확인해야 합니다.",
                "특정 과거 연도나 보유 데이터 범위의 연간 영업이익은 회사명과 연도를 함께 질문하면 조회할 수 있습니다.",
            ],
            "company": company.__dict__,
            "available_years": available_years,
            "external_references": documents,
            "news_fetch": news_fetch_result,
        }

    period = _extract_period(question, available_years)
    ratio_keys = _extract_ratio_accounts(question)
    account_keys = _extract_accounts(question, ratio_keys)
    series = store.get_account_series(company.stock_code, account_keys, period.start_year, period.end_year)
    series = _fill_missing_series_with_yfinance(company, account_keys, series, period)

    # Filter out years that have no valid account data to keep periods accurate
    valid_series = []
    for row in series:
        has_data = False
        for key in account_keys:
            val = row.get(key)
            if val and isinstance(val, dict) and val.get("amount") is not None:
                has_data = True
                break
        if has_data:
            valid_series.append(row)

    if valid_series:
        from dataclasses import replace
        new_start = min(row["year"] for row in valid_series)
        new_end = max(row["year"] for row in valid_series)
        period = replace(period, start_year=new_start, end_year=new_end, source=f"{new_start}~{new_end}년" if new_start != new_end else f"{new_start}년")
        series = [row for row in series if period.start_year <= row["year"] <= period.end_year]

    if not series:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 {period.start_year}~{period.end_year}년 추이 데이터를 찾지 못했습니다.",
            "steps": [f"가용 연도: {', '.join(map(str, available_years))}"],
        }

    ratio_series = _build_ratio_series(series, ratio_keys)
    metrics = [] if ratio_series else _build_metric_summary(series, account_keys)
    news_fetch_result = None
    documents = []
    if news_requested:
        if get_news_env("NAVER_CLIENT_ID") and get_news_env("NAVER_CLIENT_SECRET"):
            news_fetch_result = _try_fetch_news(company, question)
            if news_fetch_result.get("status") == "ok":
                documents = _filter_industry_documents(
                    _news_documents_only(search_external_docs(news_fetch_result.get("query", question), company.company_name, limit=10)),
                    company,
                )[:5]
        else:
            news_fetch_result = {
                "status": "missing_config",
                "message": "뉴스 근거 수집에는 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET 설정이 필요합니다.",
            }

    dart_fetch_result = None

    insight_lines = [] if ratio_series else _build_insights(metrics, documents)
    evidence_lines = [] if ratio_series else _build_evidence_based_explanation(metrics, documents, company)

    steps = [
        f"조회 대상: {company.company_name}({company.stock_code}), {period.start_year}~{period.end_year}년",
        f"업종 맥락: {company.industry_name or '-'}",
        f"기간 해석: {period.source}",
        _format_ratio_series_table(ratio_series) if ratio_series else _format_series_table(series, account_keys),
    ]
    if metrics:
        steps.append("계산 요약: " + " | ".join(_format_metric(metric) for metric in metrics))
    if ratio_series:
        steps.extend(_build_ratio_insights(ratio_series))
    steps.extend(insight_lines)
    steps.extend(evidence_lines)
    if documents:
        steps.append("뉴스/공시에서 확인되는 내용: " + " | ".join(f"{doc['title']}: {doc['snippet']}" for doc in documents[:3]))
    elif news_fetch_result and news_fetch_result.get("status") != "ok":
        steps.append(f"뉴스 수집: {news_fetch_result.get('message', '뉴스 수집에 실패했습니다.')}")
    elif dart_fetch_result and dart_fetch_result.get("status") != "ok":
        steps.append(f"DART 원문 수집: {dart_fetch_result.get('message', '사업보고서 수집에 실패했습니다.')}")
    else:
        steps.append("재무제표 패턴을 중심으로 해석했습니다.")

    if ratio_series:
        ratio_group = _ratio_group_label(ratio_keys)
        summary = f"{company.company_name}의 {period.start_year}~{period.end_year}년 {ratio_group} 추이를 분석했습니다."
    else:
        summary = f"{company.company_name}의 {period.start_year}~{period.end_year}년 추이를 분석했습니다."
    if news_requested and not documents:
        summary = f"{company.company_name}의 최근 주가 변동 원인은 뉴스 근거 확보 후 판단해야 합니다."

    return {
        "status": "ok",
        "summary": summary,
        "steps": steps,
        "company": company.__dict__,
        "industry_context": _industry_context(company),
        "period": period.__dict__,
        "accounts": account_keys,
        "series": series,
        "ratio_series": ratio_series,
        "metrics": metrics,
        "external_references": documents,
        "dart_fetch": dart_fetch_result,
        "news_fetch": news_fetch_result,
    }


def _ratio_group_label(ratio_keys: list[str]) -> str:
    liquidity = {"current_ratio", "quick_ratio", "cash_ratio"}
    stability = {"debt_ratio", "equity_ratio", "interest_coverage_ratio"}
    keys = set(ratio_keys)
    if keys & liquidity and keys & stability:
        return "유동성·안정성 비율"
    if keys & liquidity:
        return "유동성 비율"
    if keys & stability:
        return "안정성 비율"
    return "수익성 비율"


def _extract_period(question: str, available_years: list[int]) -> Period:
    years = [int(year) for year in re.findall(r"20[1-2]\d", question)]
    if len(years) >= 2:
        start_year, end_year = min(years[:2]), max(years[:2])
        return _clip_period(start_year, end_year, available_years, "질문에 명시된 연도 범위")
    if len(years) == 1:
        year = years[0]
        return _clip_period(year, year, available_years, "질문에 명시된 단일 연도")

    recent_match = re.search(r"최근\s*(\d+)\s*(?:개년|년)", question)
    if recent_match:
        count = max(1, int(recent_match.group(1)))
        end_year = max(available_years)
        return _clip_period(end_year - count + 1, end_year, available_years, f"최근 {count}개년")

    end_year = max(available_years)
    return _clip_period(end_year - 4, end_year, available_years, "기본값: 최근 5개년")


def _try_fetch_dart_report(company: Any, fiscal_year: int) -> dict[str, Any]:
    try:
        return DartClient().save_business_report_for_rag(
            stock_code=getattr(company, "stock_code", None),
            corp_name=getattr(company, "company_name", None),
            fiscal_year=fiscal_year,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"DART 사업보고서 자동 수집 실패: {exc}",
        }


def _should_fetch_news(question: str) -> bool:
    lowered = question.lower()
    return any(
        token in lowered
        for token in [
            "뉴스",
            "기사",
            "최근 이슈",
            "시장 반응",
            "업황",
            "동향",
            "원인",
            "이유",
            "배경",
            "전망",
            "주가",
            "주식",
            "상승",
            "하락",
            "급등",
            "급락",
            "강세",
            "약세",
            "호재",
            "악재",
            "잠정실적",
            "분기실적",
            "분기 영업이익",
            "최신 분기",
            "최근 분기",
        ]
    )


def _asks_latest_quarter(question: str) -> bool:
    lowered = question.lower()
    return any(token in lowered for token in ["최근 분기", "최신 분기", "분기 영업이익", "분기실적", "1분기", "2분기", "3분기", "4분기"]) and any(
        token in lowered for token in ["영업이익", "실적", "매출", "순이익"]
    )


def _try_fetch_news(company: Any, question: str) -> dict[str, Any]:
    company_name = getattr(company, "company_name", None)
    query = _news_query(company_name, question)
    try:
        result = NewsClient().save_news_for_rag(query, company_name=company_name, display=10)
        result["query"] = query
        return result
    except Exception as exc:
        return {
            "status": "error",
            "message": "뉴스 API 호출에 실패했습니다. 배포 환경의 NAVER_CLIENT_ID/NAVER_CLIENT_SECRET 설정과 외부 네트워크 연결을 확인해야 합니다.",
        }


def _try_fetch_latest_quarter_news(company: Any, question: str) -> dict[str, Any]:
    company_name = getattr(company, "company_name", None)
    queries = _latest_quarter_news_queries(company_name, question)
    last_result = None
    for query in queries:
        result = _try_fetch_news(company, query)
        result["query"] = query
        if result.get("status") == "ok":
            return result
        last_result = result
    return last_result or {"status": "not_found", "message": "뉴스 검색 결과가 없습니다.", "query": queries[0] if queries else question}


def _news_query(company_name: str | None, question: str) -> str:
    question = _normalize_short_year(question)
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


def _latest_quarter_news_query(company_name: str | None, question: str) -> str:
    return _latest_quarter_news_queries(company_name, question)[0]


def _latest_quarter_news_queries(company_name: str | None, question: str) -> list[str]:
    normalized = _news_query(company_name, question)
    quarter = _extract_quarter(question) or "분기"
    year = _extract_requested_year(question)
    extras = ["잠정실적", quarter, "영업이익", "매출"]
    for token in extras:
        if token not in normalized:
            normalized = f"{normalized} {token}"
    base_company = company_name or ""
    period = f"{year}년 {quarter}" if year else quarter
    return [
        normalized.strip(),
        f"{base_company} {period} 잠정실적 영업이익".strip(),
        f"{base_company} {period} 실적 영업이익".strip(),
        f"{base_company} 잠정실적 영업이익".strip(),
        f"{base_company} 분기 영업이익".strip(),
    ]


def _normalize_short_year(text: str) -> str:
    return re.sub(r"(?<!\d)(2[0-9])년", lambda match: f"20{match.group(1)}년", text)


def _extract_quarter(question: str) -> str | None:
    match = re.search(r"([1-4])\s*분기", question)
    return f"{match.group(1)}분기" if match else None


def _extract_requested_year(question: str) -> int | None:
    normalized = _normalize_short_year(question)
    match = re.search(r"(20[1-3]\d)\s*년", normalized)
    return int(match.group(1)) if match else None


def _news_documents_only(documents: list[dict]) -> list[dict]:
    return [doc for doc in documents if str(doc.get("title", "")).startswith("news_")]


def _filter_industry_documents(documents: list[dict], company: Any) -> list[dict]:
    context = _industry_context(company)
    if not context:
        return documents

    filtered = []
    for doc in documents:
        text = f"{doc.get('title', '')} {doc.get('snippet', '')}".lower()
        allowed_hits = sum(1 for keyword in context["allowed"] if keyword in text)
        blocked_hits = sum(1 for keyword in context["blocked"] if keyword in text)
        if blocked_hits and not allowed_hits:
            continue
        filtered.append(doc)
    return filtered


def _industry_context(company: Any) -> dict[str, list[str]] | None:
    industry = str(getattr(company, "industry_name", "") or "").lower()
    company_name = str(getattr(company, "company_name", "") or "").lower()
    if any(token in industry for token in ["의약", "바이오", "생물학", "제약"]):
        return {
            "allowed": [
                company_name,
                "바이오",
                "바이오시밀러",
                "시밀러",
                "의약",
                "제약",
                "신약",
                "치료제",
                "항체",
                "램시마",
                "유플라이마",
                "짐펜트라",
                "임상",
                "fda",
                "ema",
                "허가",
                "헬스케어",
            ],
            "blocked": [
                "반도체",
                "메모리",
                "hbm",
                "gpu",
                "데이터센터",
                "서버",
                "파운드리",
                "스마트폰",
                "모바일",
                "디스플레이",
                "자동차",
            ],
        }
    return None


def _resolve_comparison_companies(store: FinancialStatementStore, question: str) -> list[Any]:
    candidates = []
    seen = set()
    if _asks_defense_peer_group(question):
        target = store.resolve_company(question)
        if target:
            seen.add(target.stock_code)
            candidates.append(target)
        for name in ["한화에어로스페이스", "한국항공우주", "LIG넥스원", "한화시스템", "현대로템", "SNT다이내믹스", "퍼스텍"]:
            company = store.resolve_company(name)
            if company and company.stock_code not in seen:
                seen.add(company.stock_code)
                candidates.append(company)
        return candidates

    chunks = re.split(r"\s*(?:와|과|랑|하고|및|vs\.?|VS|비교)\s*", question)
    for chunk in chunks:
        if not chunk.strip():
            continue
        company = store.resolve_company(chunk)
        if company and company.stock_code not in seen:
            seen.add(company.stock_code)
            candidates.append(company)

    aliases = [
        "삼성전자",
        "SK하이닉스",
        "sk하이닉스",
        "하이닉스",
        "셀트리온",
        "LG에너지솔루션",
        "lg에너지솔루션",
        "현대차",
        "기아",
    ]
    lowered = question.lower()
    for alias in aliases:
        if alias.lower() not in lowered:
            continue
        query = "SK하이닉스" if alias.lower() == "하이닉스" else alias
        company = store.resolve_company(query)
        if company and company.stock_code and company.stock_code not in seen:
            seen.add(company.stock_code)
            candidates.append(company)
    return candidates


def _asks_defense_peer_group(question: str) -> bool:
    compact = question.replace(" ", "")
    return any(token in compact for token in ["방산기업", "방위산업", "방산업체", "방산주"])


def _asks_industry_peer_growth_comparison(question: str) -> bool:
    compact = question.replace(" ", "").lower()
    peer_terms = ["다른", "동종", "업종", "산업", "섹터", "기업들", "peer", "피어"]
    growth_terms = ["매출상승률", "매출성장률", "매출액상승률", "매출액성장률", "cagr", "성장률"]
    return (
        "비교" in compact
        and any(term in compact for term in peer_terms)
        and any(term in compact for term in growth_terms)
        and any(term in compact for term in ["반도체", "동종", "업종", "산업", "섹터"])
    )


def _asks_representative_industry_analysis(question: str) -> bool:
    compact = question.replace(" ", "").lower()
    representative_terms = ["대표기업", "대표회사", "대표종목"]
    analysis_terms = ["비교", "분석", "추이", "성장률", "상승률", "cagr", "매출", "영업이익", "순이익"]
    return any(term in compact for term in representative_terms) and any(term in compact for term in analysis_terms)


def _is_company_comparison_question(question: str) -> bool:
    compact = question.replace(" ", "").lower()
    return any(token in compact for token in ["비교", "vs", "대비"]) and not any(
        token in compact for token in ["비교기업", "대용기업"]
    )


def _analyze_industry_peer_growth_comparison(
    question: str, store: FinancialStatementStore, base_company: Any
) -> dict[str, Any]:
    industry = _extract_peer_industry(question, base_company)
    peer_companies = _query_peer_companies(store, industry, base_company, limit=14)
    summaries = []
    for company in peer_companies:
        available_years = store.available_years(company.stock_code)
        if not available_years:
            continue
        period = _extract_period(question, available_years)
        series = store.get_account_series(company.stock_code, ["revenue"], period.start_year, period.end_year)
        metrics = _build_metric_summary(series, ["revenue"])
        revenue_metric = _find_metric(metrics, "revenue")
        if not revenue_metric or revenue_metric.get("growth") is None:
            continue
        summaries.append(
            {
                "company": company.__dict__,
                "period": period.__dict__,
                "series": series,
                "metrics": [revenue_metric],
                "growth": revenue_metric.get("growth"),
                "cagr": revenue_metric.get("cagr"),
                "start_amount": revenue_metric.get("start_amount"),
                "end_amount": revenue_metric.get("end_amount"),
                "is_base": company.stock_code == base_company.stock_code,
            }
        )

    summaries.sort(
        key=lambda item: (
            item.get("cagr") if item.get("cagr") is not None else float("-inf"),
            item.get("growth") if item.get("growth") is not None else float("-inf"),
        ),
        reverse=True,
    )
    for index, item in enumerate(summaries, start=1):
        item["rank"] = index

    base_summary = next((item for item in summaries if item.get("is_base")), None)
    if not summaries:
        return {
            "status": "no_data",
            "summary": f"{industry} 업종의 매출 성장률 비교 데이터를 찾지 못했습니다.",
            "steps": ["비교에는 각 기업의 시작연도와 종료연도 매출액 데이터가 필요합니다."],
            "company": base_company.__dict__,
            "industry": industry,
        }

    steps = [
        f"기준 기업: {base_company.company_name}({base_company.stock_code})",
        f"비교 업종: {industry}",
        f"비교 기준: 각 기업의 가용 최근 5개년 매출액 누적 성장률과 CAGR",
    ]
    for item in summaries[:10]:
        metric = item["metrics"][0]
        steps.append(
            f"{item['rank']}. {item['company']['company_name']}: "
            f"{metric['start_year']}년 {_format_amount(metric['start_amount'])} -> "
            f"{metric['end_year']}년 {_format_amount(metric['end_amount'])}, "
            f"누적 {_format_ratio(metric['growth'])}, CAGR {_format_ratio(metric['cagr']) if metric.get('cagr') is not None else '-'}"
        )

    summary = f"{industry} 기업 {len(summaries)}개사의 최근 매출상승률을 비교했습니다."
    if base_summary:
        metric = base_summary["metrics"][0]
        summary = (
            f"{base_company.company_name}는 {industry} 비교군 {len(summaries)}개사 중 "
            f"CAGR 기준 {base_summary['rank']}위입니다. "
            f"누적 매출상승률은 {_format_ratio(metric['growth'])}, CAGR은 "
            f"{_format_ratio(metric['cagr']) if metric.get('cagr') is not None else '-'}입니다."
        )

    return {
        "status": "ok",
        "mode": "industry_growth_comparison",
        "summary": summary,
        "steps": steps,
        "industry": industry,
        "company": base_company.__dict__,
        "comparison": summaries,
        "chart_metric": "cagr",
    }


def _analyze_representative_industry_growth_comparison(question: str, store: FinancialStatementStore) -> dict[str, Any]:
    industry = resolve_representative_sector(question) or _extract_peer_industry(question, None)
    if not _asks_growth_comparison(question):
        return _analyze_representative_sector_snapshot(question, industry, store)
    representative_rows = select_representative_companies(store, industry, limit=5)
    companies = [
        CompanyMatch(
            stock_code=row["stock_code"],
            company_name=row["company_name"],
            market=row["market"],
            industry_name=row["industry_name"],
            latest_year=int(row["fiscal_year"]),
        )
        for row in representative_rows
    ]
    summaries = _build_revenue_growth_summaries(question, store, companies, include_missing=True)
    for index, item in enumerate(summaries, start=1):
        item["rank"] = index

    if not summaries:
        return {
            "status": "no_data",
            "summary": f"{industry} 대표 기업의 매출 성장률 비교 데이터를 찾지 못했습니다.",
            "steps": ["대표기업 선정 후 각 기업의 시작연도와 종료연도 매출액을 확인해야 합니다."],
            "industry": industry,
        }

    latest_year = max(row["fiscal_year"] for row in representative_rows) if representative_rows else "-"
    selection_note = (
        f"대표 기업은 엑셀 기준 {industry} 후보군에서 {latest_year}년 매출 상위 5개사로 선정하되, "
        "삼성전자·SK하이닉스처럼 주요 반도체 기업은 후보군에 포함했습니다."
    )
    steps = [
        selection_note,
        "분석 기준: 선정된 대표 기업의 가용 최근 5개년 매출액 누적 성장률과 CAGR",
    ]
    for item in summaries:
        if not item.get("metrics"):
            steps.append(
                f"{item['rank']}. {item['company']['company_name']}: "
                f"{item.get('missing_reason') or '매출액 데이터 부족으로 계산 보류'}"
            )
            continue
        metric = item["metrics"][0]
        steps.append(
            f"{item['rank']}. {item['company']['company_name']}: "
            f"{metric['start_year']}년 {_format_amount(metric['start_amount'])} -> "
            f"{metric['end_year']}년 {_format_amount(metric['end_amount'])}, "
            f"누적 {_format_ratio(metric['growth'])}, CAGR {_format_ratio(metric['cagr']) if metric.get('cagr') is not None else '-'}"
        )

    return {
        "status": "ok",
        "mode": "industry_growth_comparison",
        "summary": f"{industry} 대표 기업 {len(summaries)}개사의 매출상승률을 비교했습니다.",
        "steps": steps,
        "industry": industry,
        "selection_note": selection_note,
        "comparison": summaries,
        "chart_metric": "cagr",
    }


def _asks_growth_comparison(question: str) -> bool:
    compact = question.replace(" ", "").lower()
    return any(token in compact for token in ["성장률", "상승률", "cagr", "추이", "최근3년", "최근5년", "개년"])


def _analyze_representative_sector_snapshot(
    question: str, industry: str, store: FinancialStatementStore
) -> dict[str, Any]:
    account_keys = _extract_accounts(question) or ["revenue"]
    fiscal_year = max([int(year) for year in re.findall(r"20[1-2]\d", question)] or [2025])
    comparison = []
    failures = []

    if industry in REPRESENTATIVE_SECTOR_COMPANIES:
        companies_list = REPRESENTATIVE_SECTOR_COMPANIES[industry]
    else:
        rows = select_representative_companies(store, industry, limit=5)
        companies_list = [(row["company_name"], row["stock_code"]) for row in rows]

    for company_name, stock_code in companies_list:
        accounts = {}
        data_source = "DART"
        dart_result = None
        if load_dart_api_key():
            try:
                dart_result = DartClient().fetch_financial_accounts(
                    stock_code=stock_code,
                    corp_name=company_name,
                    fiscal_year=fiscal_year,
                )
            except Exception as exc:
                dart_result = {"status": "error", "message": str(exc)}
            if dart_result.get("status") == "ok":
                accounts = _map_dart_accounts(dart_result.get("accounts") or [])

        if not accounts:
            company = store.resolve_company(company_name)
            if company:
                stored = store.get_major_accounts(company_name, year=fiscal_year)
                if stored.get("status") == "ok":
                    accounts = stored.get("accounts") or {}
                    data_source = "재무제표 DB"

        metrics = []
        series_row: dict[str, Any] = {"year": fiscal_year}
        for account_key in account_keys:
            account = accounts.get(account_key)
            if not account or account.get("amount") is None:
                continue
            amount = float(account["amount"])
            series_row[account_key] = {**account, "amount": amount, "source": data_source.lower()}
            metrics.append(
                {
                    "key": account_key,
                    "label": ACCOUNT_LABELS.get(account_key, account_key),
                    "start_year": fiscal_year,
                    "end_year": fiscal_year,
                    "start_amount": amount,
                    "end_amount": amount,
                    "growth": None,
                    "cagr": None,
                }
            )

        if not metrics:
            failures.append(f"{company_name}: {(dart_result or {}).get('message', '요청 계정 데이터 없음')}")
            continue

        comparison.append(
            {
                "company": {
                    "company_name": company_name,
                    "stock_code": stock_code,
                    "market": "코스피(유가증권시장)",
                    "industry_name": industry,
                    "latest_year": fiscal_year,
                },
                "period": {"start_year": fiscal_year, "end_year": fiscal_year, "source": data_source},
                "series": [series_row],
                "metrics": metrics,
                "data_source": data_source,
            }
        )

    comparison.sort(
        key=lambda item: (item.get("metrics") or [{}])[0].get("end_amount") or float("-inf"),
        reverse=True,
    )
    if not comparison:
        return {
            "status": "no_data",
            "summary": f"{industry} 대표 기업의 {fiscal_year}년 재무 데이터를 확인하지 못했습니다.",
            "steps": failures or ["DART_API_KEY와 해당 연도 사업보고서 계정을 확인해야 합니다."],
            "industry": industry,
        }

    metric_labels = ", ".join(ACCOUNT_LABELS.get(key, key) for key in account_keys)
    return {
        "status": "ok",
        "mode": "representative_sector_comparison",
        "summary": f"{industry} 대표 기업 {len(comparison)}개사의 {fiscal_year}년 {metric_labels}을 비교했습니다.",
        "steps": [
            f"대표 기업군: {', '.join(name for name, _ in companies_list)}",
            f"비교 기준: {fiscal_year}년 연결재무제표 {metric_labels}",
            *[
                f"{index}. {item['company']['company_name']}: "
                + ", ".join(f"{metric['label']} {_format_amount(metric['end_amount'])}" for metric in item['metrics'])
                for index, item in enumerate(comparison, start=1)
            ],
            *(["조회 보류: " + " | ".join(failures)] if failures else []),
        ],
        "industry": industry,
        "comparison": comparison,
        "external_references": [],
    }


def _analyze_market_comparison(question: str, store: FinancialStatementStore, companies: list[Any]) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor

    def analyze_one_company(company: Any) -> dict[str, Any] | None:
        available_years = store.available_years(company.stock_code)
        if not available_years:
            return None
        period = _extract_period(question, available_years)
        ratio_keys = _extract_ratio_accounts(question)
        account_keys = _extract_accounts(question, ratio_keys)
        if not account_keys:
            account_keys = ["revenue", "operating_income", "net_income"]
        series = store.get_account_series(company.stock_code, account_keys, period.start_year, period.end_year)

        # DART is the authoritative fallback for Korean statements. Query missing
        # fiscal years first and use Yahoo only for values DART could not provide.
        series = _fill_missing_series_with_dart(company, account_keys, series, period)
        series = _fill_missing_series_with_yfinance(company, account_keys, series, period)
        ratio_series = _build_ratio_series(series, ratio_keys)
        dart_fetch = None
        if ratio_keys and not ratio_series:
            dart_fetch, dart_ratio_row = _try_build_dart_ratio_row(company, period.end_year, ratio_keys)
            if dart_ratio_row:
                ratio_series = [dart_ratio_row]
        metrics = [] if ratio_series else _build_metric_summary(series, account_keys)
        return {
            "company": company.__dict__,
            "period": period.__dict__,
            "series": series,
            "ratio_series": ratio_series,
            "ratio_keys": ratio_keys,
            "metrics": metrics,
            "dart_fetch": dart_fetch,
        }

    with ThreadPoolExecutor(max_workers=min(4, len(companies))) as executor:
        company_summaries = [item for item in executor.map(analyze_one_company, companies) if item]

    news_results = []
    documents = []
    if _should_fetch_news(question):
        for company in companies:
            if get_news_env("NAVER_CLIENT_ID") and get_news_env("NAVER_CLIENT_SECRET"):
                news_result = _try_fetch_news(company, question)
                news_results.append({"company": company.company_name, **news_result})
                if news_result.get("status") == "ok":
                    documents.extend(_news_documents_only(search_external_docs(news_result.get("query", question), company.company_name, limit=10))[:3])
            else:
                news_results.append(
                    {
                        "company": company.company_name,
                        "status": "missing_config",
                        "message": "최근 주가/뉴스 비교에는 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET 설정이 필요합니다.",
                    }
                )

    steps = [
        "비교 대상: " + ", ".join(f"{item['company']['company_name']}({item['company']['stock_code']})" for item in company_summaries),
    ]
    for item in company_summaries:
        company = item["company"]
        period = item["period"]
        steps.append(f"{company['company_name']} 기간: {period['start_year']}~{period['end_year']}년")
        if item.get("ratio_series"):
            steps.append(_format_ratio_series_table(item["ratio_series"]))
            steps.extend(f"{company['company_name']} {line}" for line in _build_ratio_insights(item["ratio_series"]))
        else:
            steps.append(_format_series_table(item["series"], ["revenue", "operating_income", "net_income"]))
        if item["metrics"]:
            steps.append(f"{company['company_name']} 계산 요약: " + " | ".join(_format_metric(metric) for metric in item["metrics"]))
    for result in news_results:
        if result.get("status") != "ok":
            steps.append(f"{result['company']} 뉴스 수집: {result.get('message', '뉴스 수집에 실패했습니다.')}")
    if documents:
        steps.append("뉴스에서 확인되는 내용: " + " | ".join(f"{doc['title']}: {doc['snippet']}" for doc in documents[:5]))

    return {
        "status": "ok",
        "summary": "질문에 나온 앞 기업부터 순서대로 재무 지표를 계산해 비교했습니다.",
        "steps": steps,
        "comparison": company_summaries,
        "external_references": documents,
        "news_fetch": {
            "status": (
                "not_requested"
                if not _should_fetch_news(question)
                else "ok" if any(result.get("status") == "ok" for result in news_results) else "missing_config"
            ),
            "count": sum(result.get("count", 0) for result in news_results),
            "results": news_results,
        },
    }


def _build_revenue_growth_summaries(
    question: str, store: FinancialStatementStore, companies: list[Any], include_missing: bool = False
) -> list[dict[str, Any]]:
    summaries = []
    for company in companies:
        available_years = store.available_years(company.stock_code)
        if not available_years:
            continue
        period = _extract_period(question, available_years)
        series = store.get_account_series(company.stock_code, ["revenue"], period.start_year, period.end_year)
        metrics = _build_metric_summary(series, ["revenue"])
        revenue_metric = _find_metric(metrics, "revenue")
        if not revenue_metric:
            dart_series = _try_build_dart_revenue_series(company, period.start_year, period.end_year)
            if dart_series:
                series = dart_series
                metrics = _build_metric_summary(series, ["revenue"])
                revenue_metric = _find_metric(metrics, "revenue")
        if not revenue_metric or revenue_metric.get("growth") is None:
            if include_missing:
                summaries.append(
                    {
                        "company": company.__dict__,
                        "period": period.__dict__,
                        "series": series,
                        "metrics": [],
                        "growth": None,
                        "cagr": None,
                        "missing_reason": "엑셀 손익계산서 매출액 데이터가 없어 계산을 보류했습니다.",
                    }
                )
            continue
        summaries.append(
            {
                "company": company.__dict__,
                "period": period.__dict__,
                "series": series,
                "metrics": [revenue_metric],
                "growth": revenue_metric.get("growth"),
                "cagr": revenue_metric.get("cagr"),
                "start_amount": revenue_metric.get("start_amount"),
                "end_amount": revenue_metric.get("end_amount"),
            }
        )
    summaries.sort(
        key=lambda item: (
            item.get("cagr") if item.get("cagr") is not None else float("-inf"),
            item.get("growth") if item.get("growth") is not None else float("-inf"),
        ),
        reverse=True,
    )
    return summaries


def _extract_peer_industry(question: str, base_company: Any) -> str:
    compact = question.replace(" ", "")
    if "반도체" in compact:
        return "반도체"
    related_company_match = re.search(r"^\s*(.+?)\s+관련\s+(?:기업들|기업|회사들|회사)", question)
    if related_company_match:
        return re.sub(r"^기타\s*", "", related_company_match.group(1)).strip()
    explicit_industry_match = re.search(
        r"^\s*(.+?)\s+(?:산업|업종|섹터)(?=(?:에서|의|내|중|별|에|으로)?(?:\s|$))",
        question,
    )
    if explicit_industry_match:
        return explicit_industry_match.group(1).strip(" ?.,!")
    match = re.search(r"([가-힣A-Za-z0-9]+)\s*(?:기업들|업종|산업|섹터)", question)
    if match:
        ret = match.group(1)
        return re.sub(r"^기타\s*", "", ret).strip()
    if base_company:
        return _major_industry(getattr(base_company, "industry_name", "") or getattr(base_company, "company_name", ""))

    cleaned = question
    cleaned = re.sub(r"(?:의|을|를|이|가|은|는|에|에\s*대한|에\s*대해)\s+", " ", cleaned)
    cleaned = re.sub(r"(?:대표기업|대표회사|대표종목|대표|상위|관련|기업들|기업|회사|종목|알려줘|알려|알려주세요|알려줘요|알려주라|추천|추천해줘|분석|분석해줘|알아봐)\b.*", "", cleaned)
    cleaned = re.sub(r"[?.,!]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) >= 2:
        return re.sub(r"^기타\s*", "", cleaned).strip()

    return "산업"


def _query_peer_companies(
    store: FinancialStatementStore, industry: str, base_company: Any, limit: int
) -> list[Any]:
    store.ensure_database()
    keywords = _peer_industry_keywords(industry)
    where_parts = []
    params: list[Any] = []
    for keyword in keywords:
        where_parts.append("(company_name LIKE ? OR industry_name LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    where_sql = " OR ".join(where_parts) if where_parts else "1=1"
    base_order = "CASE WHEN stock_code = ? THEN 0 ELSE 1 END," if base_company else ""
    query = f"""
        SELECT stock_code, company_name, market, industry_name, MAX(fiscal_year) AS latest_year
        FROM financial_items
        WHERE stock_code != ''
          AND ({where_sql})
        GROUP BY stock_code, company_name, market, industry_name
        HAVING COUNT(DISTINCT fiscal_year) >= 3
        ORDER BY
            {base_order}
            latest_year DESC,
            company_name
        LIMIT ?
    """
    if base_company:
        params.append(base_company.stock_code)
    params.append(limit)
    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    companies = []
    seen = set()
    if base_company and base_company.stock_code:
        companies.append(base_company)
        seen.add(base_company.stock_code)
    for row in rows:
        if row["stock_code"] in seen:
            continue
        seen.add(row["stock_code"])
        companies.append(
            CompanyMatch(
                stock_code=row["stock_code"],
                company_name=row["company_name"],
                market=row["market"],
                industry_name=row["industry_name"],
                latest_year=int(row["latest_year"]),
            )
        )
    return companies[:limit]


def _peer_industry_keywords(industry: str) -> list[str]:
    import re
    norm = industry.replace(" ", "")
    norm = re.sub(r"(?:산업|업종|업|분야|섹터)$", "", norm).strip()
    
    if norm in ["반도체", "메모리"]:
        return ["반도체", "전자집적회로", "다이오드", "트랜지스터", "메모리", "웨이퍼", "집적회로"]
    if norm in ["바이오", "제약", "의약", "헬스케어"]:
        return ["바이오", "의약", "제약", "생물학", "의약품", "의료"]
    if norm in ["방산", "방위", "방위산업"]:
        return ["방산", "방위", "항공기", "우주선", "무기", "탄약", "전투용", "함정"]
    if norm in ["조선", "해양", "선박"]:
        return ["조선", "선박", "건조", "함정", "보트", "해양"]
    if norm in ["화학", "화학제품", "석유화학"]:
        return ["화학", "석유", "고무", "플라스틱", "도료", "잉크", "화장품"]
    if norm in ["철강", "금속", "제강"]:
        return ["철강", "금속", "제철", "제강", "합금", "비철"]
    if norm in ["자동차", "완성차", "부품"]:
        return ["자동차", "트레일러", "섀시", "부품", "엔진"]
    if norm in ["항공", "여객", "운송"]:
        return ["항공", "여객", "운송", "화물", "공항"]
    if norm in ["게임", "소프트웨어", "콘텐츠"]:
        return ["게임", "소프트웨어", "개발", "퍼블리싱", "모바일게임", "온라인게임"]
    if norm in ["배터리", "이차전지", "2차전지"]:
        return ["이차전지", "2차전지", "축전지", "배터리", "양극재", "음극재", "전해액"]
    if norm in ["IT", "정보기술", "인터넷", "플랫폼"]:
        return ["소프트웨어", "인터넷", "포털", "플랫폼", "IT", "시스템 통합", "SI"]

    return list(dict.fromkeys([industry.strip(), norm]))


def _try_build_dart_revenue_series(company: Any, start_year: int, end_year: int) -> list[dict[str, Any]]:
    if not load_dart_api_key():
        return []
    rows = []
    for fiscal_year in range(start_year, end_year + 1):
        try:
            result = DartClient().fetch_financial_accounts(
                stock_code=getattr(company, "stock_code", None),
                corp_name=getattr(company, "company_name", None),
                fiscal_year=fiscal_year,
            )
        except Exception:
            continue
        if result.get("status") != "ok":
            continue
        accounts = _map_dart_accounts(result.get("accounts") or [])
        revenue = accounts.get("revenue")
        if revenue and revenue.get("amount") is not None:
            rows.append({"year": fiscal_year, "revenue": revenue | {"source": "dart"}})
    return rows


def _clip_period(start_year: int, end_year: int, available_years: list[int], source: str) -> Period:
    min_year, max_year = min(available_years), max(available_years)
    return Period(max(start_year, min_year), min(end_year, max_year), source)


def _extract_accounts(question: str, ratio_keys: list[str] | None = None) -> list[str]:
    if ratio_keys:
        required = []
        for ratio_key in ratio_keys:
            for account_key in PROFITABILITY_RATIO_DEFINITIONS[ratio_key]["required"]:
                if account_key not in required:
                    required.append(account_key)
        return required

    account_keys = []
    patterns = [
        ("revenue", ["매출", "영업수익", "revenue"]),
        ("cost_of_sales", ["매출원가", "원가"]),
        ("selling_admin_expenses", ["판매비와관리비", "판매비", "관리비", "판관비"]),
        ("gross_profit", ["매출총이익", "gross profit"]),
        ("operating_income", ["영업이익", "operating income"]),
        ("net_income", ["순이익", "당기순이익", "net income"]),
        ("operating_cash_flow", ["영업활동현금흐름", "영업현금흐름", "cfo"]),
        ("total_assets", ["자산총계", "자산 추이", "자산"]),
        ("total_liabilities", ["부채총계", "부채 추이", "부채"]),
        ("total_equity", ["자본총계", "자본 추이", "자본"]),
    ]
    lowered = question.lower()
    for account_key, tokens in patterns:
        if any(token in lowered for token in tokens):
            account_keys.append(account_key)
    return account_keys or ["revenue", "operating_income", "net_income"]


def _extract_ratio_accounts(question: str) -> list[str]:
    compact = question.replace(" ", "").lower()
    ratio_keys = []
    if any(token in compact for token in ["매출원가율", "원가율", "costofsalesratio", "cogsratio"]):
        ratio_keys.append("cost_of_sales_ratio")
    if any(token in compact for token in ["매출액총이익률", "매출총이익률", "grossmargin"]):
        ratio_keys.append("gross_margin")
    if any(token in compact for token in ["판관비율", "판매비와관리비율", "판매관리비율", "sg&a", "sgnaratio", "sellingadminratio"]):
        ratio_keys.append("selling_admin_expense_ratio")
    if any(token in compact for token in ["매출액영업이익률", "영업이익률", "영업마진", "operatingmargin"]):
        ratio_keys.append("operating_margin")
    if any(token in compact for token in ["매출액순이익률", "당기순이익률", "순이익률", "순이익마진", "netmargin"]):
        ratio_keys.append("net_margin")
    if any(token in compact for token in ["roa", "총자산이익률", "총자산순이익률"]):
        ratio_keys.append("roa")
    if any(token in compact for token in ["roe", "자기자본이익률", "자기자본순이익률"]):
        ratio_keys.append("roe")
    if any(token in compact for token in ["투하자본수익률", "roic", "총자본영업이익률", "자산영업이익률"]):
        ratio_keys.append("operating_roa")
    if any(token in compact for token in ["유동비율", "currentratio"]):
        ratio_keys.append("current_ratio")
    if any(token in compact for token in ["당좌비율", "quickratio"]):
        ratio_keys.append("quick_ratio")
    if any(token in compact for token in ["부채비율", "debtratio"]):
        ratio_keys.append("debt_ratio")
    if any(token in compact for token in ["매출액이익률", "profitmargin"]) and not ratio_keys:
        ratio_keys.extend(["operating_margin", "net_margin"])
    if any(token in compact for token in ["이익률추이", "수익성비율", "수익성지표", "수익성분석"]) and not ratio_keys:
        ratio_keys.extend(["cost_of_sales_ratio", "gross_margin", "selling_admin_expense_ratio", "operating_margin", "net_margin", "roa", "roe"])
    deduped = []
    for ratio_key in ratio_keys:
        if ratio_key not in deduped:
            deduped.append(ratio_key)
    return deduped


def _build_ratio_series(series: list[dict[str, Any]], ratio_keys: list[str]) -> list[dict[str, Any]]:
    if not ratio_keys:
        return []
    rows = []
    for row in series:
        ratio_row: dict[str, Any] = {"year": row["year"]}
        for ratio_key in ratio_keys:
            value = _calculate_profitability_ratio(row, ratio_key)
            if value is None:
                continue
            label = PROFITABILITY_RATIO_DEFINITIONS[ratio_key]["label"]
            ratio_row[ratio_key] = {
                "label": label,
                "value": value,
                "display": _format_ratio(value),
            }
        if len(ratio_row) > 1:
            rows.append(ratio_row)
    return rows


def _calculate_profitability_ratio(row: dict[str, Any], ratio_key: str) -> float | None:
    def amount(account_key: str) -> float | None:
        item = row.get(account_key)
        if not item:
            return None
        return item.get("amount")

    if ratio_key == "cost_of_sales_ratio":
        return _safe_ratio(amount("cost_of_sales"), amount("revenue"))
    if ratio_key == "gross_margin":
        return _safe_ratio(amount("gross_profit"), amount("revenue"))
    if ratio_key == "selling_admin_expense_ratio":
        return _safe_ratio(amount("selling_admin_expenses"), amount("revenue"))
    if ratio_key == "operating_margin":
        return _safe_ratio(amount("operating_income"), amount("revenue"))
    if ratio_key == "net_margin":
        return _safe_ratio(amount("net_income"), amount("revenue"))
    if ratio_key == "roa":
        return _safe_ratio(amount("net_income"), amount("total_assets"))
    if ratio_key == "roe":
        return _safe_ratio(amount("net_income"), amount("total_equity"))
    if ratio_key == "operating_roa":
        return _safe_ratio(amount("operating_income"), amount("total_assets"))
    if ratio_key == "current_ratio":
        return _safe_ratio(amount("current_assets"), amount("current_liabilities"))
    if ratio_key == "quick_ratio":
        curr_ast = amount("current_assets")
        curr_lib = amount("current_liabilities")
        inv = amount("inventories") or 0.0
        if curr_ast is not None and curr_lib:
            return _safe_ratio(curr_ast - inv, curr_lib)
        return None
    if ratio_key == "debt_ratio":
        return _safe_ratio(amount("total_liabilities"), amount("total_equity"))
    return None


def _try_build_dart_ratio_row(company: Any, fiscal_year: int, ratio_keys: list[str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not load_dart_api_key():
        return (
            {
                "status": "missing_config",
                "message": "로컬 재무제표에 손익계산서 데이터가 없어 DART_API_KEY가 필요합니다.",
            },
            None,
        )
    try:
        result = DartClient().fetch_financial_accounts(
            stock_code=getattr(company, "stock_code", None),
            corp_name=getattr(company, "company_name", None),
            fiscal_year=fiscal_year,
        )
    except Exception as exc:
        return {"status": "error", "message": f"DART 재무제표 조회 실패: {exc}"}, None
    if result.get("status") != "ok":
        return result, None

    accounts = _map_dart_accounts(result.get("accounts") or [])
    row: dict[str, Any] = {"year": fiscal_year}
    for key, account in accounts.items():
        row[key] = account
    ratio_rows = _build_ratio_series([row], ratio_keys)
    return {"status": "ok", "source": "dart"}, ratio_rows[0] if ratio_rows else None


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _format_ratio_series_table(ratio_series: list[dict[str, Any]]) -> str:
    rows = []
    for row in ratio_series:
        values = []
        for key in PROFITABILITY_RATIO_DEFINITIONS:
            item = row.get(key)
            if item:
                values.append(f"{item['label']} {item['display']}")
        rows.append(f"{row['year']}년: " + ", ".join(values))
    return "연도별 수익성 비율: " + " / ".join(rows)


def _build_ratio_insights(ratio_series: list[dict[str, Any]]) -> list[str]:
    insights = []
    for key in PROFITABILITY_RATIO_DEFINITIONS:
        values = [row[key] | {"year": row["year"]} for row in ratio_series if row.get(key)]
        if len(values) < 2:
            continue
        first = values[0]
        last = values[-1]
        diff = last["value"] - first["value"]
        direction = "상승" if diff > 0 else "하락" if diff < 0 else "유지"
        insights.append(
            f"인사이트: {last['label']}은 {first['year']}년 {first['display']}에서 "
            f"{last['year']}년 {last['display']}로 {direction}했습니다."
        )
    return insights


def _build_metric_summary(series: list[dict[str, Any]], account_keys: list[str]) -> list[dict[str, Any]]:
    metrics = []
    for account_key in account_keys:
        values = [
            {"year": row["year"], "amount": row[account_key]["amount"]}
            for row in series
            if row.get(account_key)
        ]
        if len(values) < 2:
            continue
        first = values[0]
        last = values[-1]
        change = last["amount"] - first["amount"]
        growth = change / abs(first["amount"]) if first["amount"] else None
        years = max(1, last["year"] - first["year"])
        cagr = (last["amount"] / first["amount"]) ** (1 / years) - 1 if first["amount"] > 0 and last["amount"] > 0 else None
        yoy = []
        for prev, current in zip(values, values[1:]):
            yoy.append(
                {
                    "year": current["year"],
                    "growth": (current["amount"] - prev["amount"]) / abs(prev["amount"]) if prev["amount"] else None,
                }
            )
        metrics.append(
            {
                "account": account_key,
                "label": ACCOUNT_LABELS.get(account_key, account_key),
                "start_year": first["year"],
                "end_year": last["year"],
                "start_amount": first["amount"],
                "end_amount": last["amount"],
                "change": change,
                "growth": growth,
                "cagr": cagr,
                "yoy": yoy,
            }
        )
    return metrics


def _build_insights(metrics: list[dict[str, Any]], documents: list[dict]) -> list[str]:
    if not metrics:
        return ["인사이트: 계정별 연속 데이터가 부족해 추세 판단을 제한합니다."]

    lines = []
    for metric in metrics:
        direction = "증가" if metric["change"] > 0 else "감소" if metric["change"] < 0 else "정체"
        line = f"인사이트: {metric['label']}은 {metric['start_year']}년 대비 {metric['end_year']}년에 {direction}했습니다"
        if metric["growth"] is not None:
            line += f"({ _format_ratio(metric['growth']) })."
        else:
            line += "."
        volatile_years = [
            f"{item['year']}년 { _format_ratio(item['growth']) }"
            for item in metric["yoy"]
            if item["growth"] is not None and abs(item["growth"]) >= 0.15
        ]
        if volatile_years:
            line += " 변동이 컸던 구간은 " + ", ".join(volatile_years[:3]) + "입니다."
        lines.append(line)

    revenue = _find_metric(metrics, "revenue")
    operating_income = _find_metric(metrics, "operating_income")
    net_income = _find_metric(metrics, "net_income")
    if revenue and operating_income:
        if revenue["change"] > 0 and operating_income["change"] < 0:
            lines.append("원인 후보: 매출은 늘었지만 영업이익이 줄어 비용률 상승, 판가 하락, 제품 믹스 악화, 일회성 비용 가능성을 확인해야 합니다.")
        elif revenue["change"] < 0 and operating_income["change"] < 0:
            lines.append("원인 후보: 매출과 영업이익이 함께 감소해 수요 둔화, 판매량 감소, 업황 악화 가능성이 우선 점검 대상입니다.")
        elif revenue["change"] > 0 and operating_income["change"] > 0:
            lines.append("원인 후보: 매출과 영업이익이 함께 증가해 외형 성장과 영업 레버리지 개선 가능성이 있습니다.")
    if operating_income and net_income and operating_income["change"] > 0 and net_income["change"] < 0:
        lines.append("원인 후보: 영업이익과 순이익 방향이 달라 금융손익, 관계기업손익, 법인세, 중단영업 등 영업외 요인을 확인해야 합니다.")
    if documents:
        lines.append("해석 기준: 사업부문 설명, 업황, 가격/물량 언급을 위 원인 후보와 대조해야 합니다.")
    return lines


def _build_evidence_based_explanation(metrics: list[dict[str, Any]], documents: list[dict], company: Any | None = None) -> list[str]:
    if not documents:
        return []

    lines = []
    revenue = _find_metric(metrics, "revenue")
    operating_income = _find_metric(metrics, "operating_income")
    evidence_text = " ".join(doc.get("snippet", "") for doc in documents).lower()
    evidence_topics = _extract_evidence_topics(evidence_text, company)

    if revenue:
        direction = "증가" if revenue["change"] > 0 else "감소" if revenue["change"] < 0 else "정체"
        topic_text = ", ".join(evidence_topics[:5]) if evidence_topics else "사업부문/업황 설명"
        lines.append(
            f"근거 기반 해석: {revenue['label']} {direction}는 사업보고서에서 확인되는 {topic_text}와 연결해 검토할 수 있습니다."
        )

    if revenue and operating_income:
        if revenue["change"] > 0 and operating_income["change"] < 0:
            lines.append("근거 기반 해석: 외형은 증가했지만 이익이 감소했으므로 원가, 가격, 제품 믹스, 일회성 비용 언급을 우선 확인해야 합니다.")
        elif revenue["change"] < 0 and operating_income["change"] > 0:
            lines.append("근거 기반 해석: 외형은 감소했지만 이익이 개선되어 고수익 제품 비중 확대, 비용 절감, 비효율 사업 축소 가능성을 점검해야 합니다.")

    top_sources = []
    for doc in documents[:3]:
        source = doc["title"]
        if doc.get("source_url"):
            source += f" ({doc['source_url']})"
        top_sources.append(source)
    if top_sources:
        lines.append("근거 출처: " + " | ".join(top_sources))
    return lines


def _extract_evidence_topics(text: str, company: Any | None = None) -> list[str]:
    context = _industry_context(company) if company else None
    if context:
        topic_keywords = [
            ("바이오시밀러/의약품", ["바이오시밀러", "시밀러", "의약", "제약", "치료제", "항체"]),
            ("신약/파이프라인", ["신약", "파이프라인", "임상", "허가", "fda", "ema"]),
            ("헬스케어 시장", ["헬스케어", "시장", "수요", "고객"]),
            ("가격/판가", ["가격", "판가", "약가"]),
            ("원가/비용", ["원가", "비용", "수익성"]),
        ]
        topics = []
        for label, keywords in topic_keywords:
            if any(keyword in text for keyword in keywords):
                topics.append(label)
        return topics

    topic_keywords = [
        ("메모리 반도체", ["메모리", "dram", "nand"]),
        ("반도체 업황", ["반도체", "파운드리", "시스템lsi"]),
        ("AI/서버 수요", ["ai", "서버", "hbm", "데이터센터"]),
        ("모바일 수요", ["모바일", "스마트폰", "mx"]),
        ("디스플레이", ["디스플레이", "oled", "lcd"]),
        ("가격/판가", ["가격", "판가", "asp"]),
        ("출하량/판매량", ["출하", "판매량", "물량"]),
        ("환율", ["환율", "원화", "달러"]),
        ("원가/원재료", ["원가", "원재료", "비용"]),
        ("시장 수요", ["수요", "시장", "고객"]),
    ]
    topics = []
    for label, keywords in topic_keywords:
        if any(keyword in text for keyword in keywords):
            topics.append(label)
    return topics


def _find_metric(metrics: list[dict[str, Any]], account_key: str) -> dict[str, Any] | None:
    return next((metric for metric in metrics if metric["account"] == account_key), None)


def _format_series_table(series: list[dict[str, Any]], account_keys: list[str]) -> str:
    rows = []
    for row in series:
        values = []
        for account_key in account_keys:
            account = row.get(account_key)
            if account:
                values.append(f"{ACCOUNT_LABELS.get(account_key, account_key)} {_format_amount(account['amount'])}")
            else:
                values.append(f"{ACCOUNT_LABELS.get(account_key, account_key)} -")
        rows.append(f"{row['year']}년: " + ", ".join(values))
    return "연도별 추이: " + " / ".join(rows)


def _format_metric(metric: dict[str, Any]) -> str:
    parts = [
        f"{metric['label']} {metric['start_year']}년 {_format_amount(metric['start_amount'])} -> {metric['end_year']}년 {_format_amount(metric['end_amount'])}"
    ]
    if metric["growth"] is not None:
        parts.append(f"누적 {_format_ratio(metric['growth'])}")
    if metric["cagr"] is not None:
        parts.append(f"CAGR {_format_ratio(metric['cagr'])}")
    return " ".join(parts)


def _fill_missing_series_with_yfinance(company: Any, account_keys: list[str], series: list[dict], period: Any) -> list[dict]:
    yf_mapping = {
        "operating_income": "Operating Income",
        "revenue": "Total Revenue",
        "net_income": "Net Income",
        "total_assets": "Total Assets",
        "total_equity": "Total Capital Equity",
        "total_liabilities": "Total Liabilities Net Minority Interest",
        "operating_cash_flow": "Operating Cash Flow",
        "current_assets": "Current Assets",
        "current_liabilities": "Current Liabilities",
        "inventories": "Inventories",
    }

    missing_keys = []
    for key in account_keys:
        if key in yf_mapping:
            has_missing_value = any(
                not isinstance(row.get(key), dict) or row[key].get("amount") is None
                for row in series
            )
            if has_missing_value:
                missing_keys.append(key)

    if not missing_keys:
        return series

    from tools.stock_price_tool import _to_yahoo_ticker
    ticker_str = _to_yahoo_ticker(company.stock_code, company.market)

    import yfinance as yf
    try:
        yf_ticker = yf.Ticker(ticker_str)
        dfs = []
        income_keys = {"operating_income", "revenue", "net_income"}
        balance_keys = {
            "total_assets", "total_equity", "total_liabilities", "current_assets",
            "current_liabilities", "inventories",
        }
        if income_keys.intersection(missing_keys):
            try:
                financials = yf_ticker.financials
                if financials is not None and not financials.empty:
                    dfs.append(financials)
            except Exception:
                pass
        if balance_keys.intersection(missing_keys):
            try:
                balance_sheet = yf_ticker.balance_sheet
                if balance_sheet is not None and not balance_sheet.empty:
                    dfs.append(balance_sheet)
            except Exception:
                pass
        if "operating_cash_flow" in missing_keys:
            try:
                cashflow = yf_ticker.cashflow
                if cashflow is not None and not cashflow.empty:
                    dfs.append(cashflow)
            except Exception:
                pass

        if not dfs:
            return series

        import pandas as pd
        combined_df = pd.concat(dfs)

        col_years = {}
        for col in combined_df.columns:
            if hasattr(col, "year"):
                col_years[col.year] = col

        for row in series:
            year = int(row["year"])
            col = col_years.get(year)
            if col is None:
                continue

            for key in missing_keys:
                yf_label = yf_mapping[key]
                if yf_label in combined_df.index:
                    val = combined_df.loc[yf_label, col]
                    if isinstance(val, pd.Series):
                        val = val.iloc[0]
                    if pd.notna(val):
                        row[key] = {
                            "label": {
                                "operating_income": "영업이익",
                                "revenue": "매출액",
                                "net_income": "당기순이익",
                                "total_assets": "자산총계",
                                "total_equity": "자본총계",
                                "total_liabilities": "부채총계",
                                "operating_cash_flow": "영업활동현금흐름",
                                "current_assets": "유동자산",
                                "current_liabilities": "유동부채",
                                "inventories": "재고자산"
                            }.get(key, key),
                            "amount": float(val),
                            "statement_type": "PL" if key in ["operating_income", "revenue", "net_income"] else "BS" if key in ["total_assets", "total_equity", "total_liabilities", "current_assets", "current_liabilities", "inventories"] else "CF",
                            "account_name": yf_label,
                            "account_code": yf_label,
                            "currency": "KRW",
                        }
    except Exception:
        pass

    return series


def _fill_missing_series_with_dart(company: Any, account_keys: list[str], series: list[dict], period: Any) -> list[dict]:
    if not load_dart_api_key():
        return series
    rows_by_year = {int(row["year"]): row for row in series}
    missing_years = [
        year
        for year in range(int(period.start_year), int(period.end_year) + 1)
        if any(
            not isinstance(rows_by_year.get(year, {}).get(key), dict)
            or rows_by_year[year][key].get("amount") is None
            for key in account_keys
        )
    ]
    if not missing_years:
        return series

    def fetch_year(fiscal_year: int) -> dict[str, Any]:
        client = DartClient()
        last_result: dict[str, Any] = {"status": "error", "message": "DART 조회에 실패했습니다."}
        for fs_div in ("CFS", "OFS"):
            try:
                result = client.fetch_financial_accounts(
                    stock_code=company.stock_code,
                    corp_name=company.company_name,
                    fiscal_year=fiscal_year,
                    fs_div=fs_div,
                )
                if result.get("status") == "ok":
                    return result
                last_result = result
            except Exception as exc:
                last_result = {"status": "error", "message": str(exc)}
        return last_result

    try:
        # A single annual DART response contains the current and two comparative
        # periods. Reuse those fields instead of issuing one request per year.
        anchor_year = max(missing_years)
        result = fetch_year(anchor_year)
        if result.get("status") != "ok":
            return series
        raw_accounts = result.get("accounts") or []
        amount_fields = {
            anchor_year: "thstrm_amount",
            anchor_year - 1: "frmtrm_amount",
            anchor_year - 2: "bfefrmtrm_amount",
        }
        for fiscal_year in missing_years:
            amount_field = amount_fields.get(fiscal_year)
            if not amount_field:
                continue
            normalized_accounts = [
                {**account, "thstrm_amount": account.get(amount_field)}
                for account in raw_accounts
                if str(account.get(amount_field) or "").strip()
            ]
            accounts = _map_dart_accounts(normalized_accounts)
            row = rows_by_year.setdefault(fiscal_year, {"year": fiscal_year})
            for key in account_keys:
                if isinstance(row.get(key), dict) and row[key].get("amount") is not None:
                    continue
                account = accounts.get(key)
                if account and account.get("amount") is not None:
                    row[key] = {**account, "source": "dart"}
    except Exception:
        return series
    return [rows_by_year[year] for year in sorted(rows_by_year)]


def _analyze_industry_peers_growth_direct(
    question: str, store: FinancialStatementStore, industry: str, peer_companies: list[Any]
) -> dict[str, Any]:
    summaries = []
    for company in peer_companies:
        available_years = store.available_years(company.stock_code)
        if not available_years:
            continue
        period = _extract_period(question, available_years)
        series = store.get_account_series(company.stock_code, ["revenue", "operating_income"], period.start_year, period.end_year)
        series = _fill_missing_series_with_yfinance(company, ["revenue", "operating_income"], series, period)
        revenue_count = sum(
            1
            for row in series
            if isinstance(row.get("revenue"), dict) and row["revenue"].get("amount") is not None
        )
        if revenue_count < 3:
            dart_rows = _try_build_dart_revenue_series(company, period.start_year, period.end_year)
            dart_by_year = {int(row["year"]): row.get("revenue") for row in dart_rows}
            for row in series:
                if not isinstance(row.get("revenue"), dict) or row["revenue"].get("amount") is None:
                    dart_revenue = dart_by_year.get(int(row["year"]))
                    if dart_revenue:
                        row["revenue"] = dart_revenue
        metrics = _build_metric_summary(series, ["revenue", "operating_income"])
        revenue_metric = _find_metric(metrics, "revenue")
        if not revenue_metric or revenue_metric.get("growth") is None:
            continue
        summaries.append(
            {
                "company": company.__dict__,
                "period": period.__dict__,
                "series": series,
                "metrics": metrics,
                "growth": revenue_metric.get("growth"),
                "cagr": revenue_metric.get("cagr"),
                "start_amount": revenue_metric.get("start_amount"),
                "end_amount": revenue_metric.get("end_amount"),
                "is_base": False,
            }
        )
        if len(summaries) >= 5:
            break

    summaries.sort(
        key=lambda item: (
            item.get("cagr") if item.get("cagr") is not None else float("-inf"),
            item.get("growth") if item.get("growth") is not None else float("-inf"),
        ),
        reverse=True,
    )
    for index, item in enumerate(summaries, start=1):
        item["rank"] = index

    if not summaries:
        return {
            "status": "no_data",
            "summary": f"{industry} 업종에 속한 기업들의 매출 성장률 비교 데이터를 찾지 못했습니다.",
            "steps": ["각 기업의 시작연도와 종료연도 매출액 데이터가 필요합니다."],
            "industry": industry,
        }

    steps = [
        f"비교 업종: {industry}",
    ]
    for item in summaries:
        comp_name = item["company"]["company_name"]
        period_lbl = f"{item['period']['start_year']}~{item['period']['end_year']}년"
        cagr_text = f"{item['cagr'] * 100:.2f}%" if item.get("cagr") is not None else "계산 불가"
        steps.append(
            f"{item['rank']}위. {comp_name} ({period_lbl}): "
            f"누적 매출성장률 {item['growth'] * 100:.2f}%, CAGR {cagr_text}"
        )
        for row in item["series"]:
            y = row["year"]
            rev = (row.get("revenue") or {}).get("amount")
            op = (row.get("operating_income") or {}).get("amount")
            rev_str = _format_amount(rev) if rev is not None else "데이터 없음"
            op_str = _format_amount(op) if op is not None else "데이터 없음"
            steps.append(f"  - {y}년: 매출액 {rev_str}, 영업이익 {op_str}")

    return {
        "status": "ok",
        "mode": "industry_growth_comparison",
        "summary": f"{industry} 업종에 속한 주요 기업들의 매출성장률을 분석해 비교했습니다.",
        "steps": steps,
        "comparison": summaries,
        "industry": industry,
        "external_references": [],
    }
