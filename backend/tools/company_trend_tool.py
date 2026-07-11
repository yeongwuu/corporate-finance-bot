from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from company_data.financial_store import FinancialStatementStore
from dart_client import DartClient, load_dart_api_key
from news_client import NewsClient, get_env as get_news_env
from rag.external_rag import search_external_docs
from tools.company_analysis_tool import _format_amount, _format_ratio


ACCOUNT_LABELS = {
    "revenue": "매출액",
    "operating_income": "영업이익",
    "net_income": "당기순이익",
    "operating_cash_flow": "영업활동현금흐름",
    "total_assets": "자산총계",
    "total_liabilities": "부채총계",
    "total_equity": "자본총계",
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
        comparison_companies = _resolve_comparison_companies(store, question) if news_requested else []
        if len(comparison_companies) >= 2:
            return _analyze_market_comparison(question, store, comparison_companies[:3])
        company = store.resolve_company(question)
    except FileNotFoundError as exc:
        return {
            "status": "missing_data",
            "summary": "KOSDAQ_financial_statements.xlsx 파일을 찾지 못했습니다.",
            "steps": [str(exc)],
        }
    if not company:
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
    account_keys = _extract_accounts(question)
    series = store.get_account_series(company.stock_code, account_keys, period.start_year, period.end_year)
    if not series:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 {period.start_year}~{period.end_year}년 추이 데이터를 찾지 못했습니다.",
            "steps": [f"가용 연도: {', '.join(map(str, available_years))}"],
        }

    metrics = _build_metric_summary(series, account_keys)
    news_fetch_result = None
    documents = []
    if get_news_env("NAVER_CLIENT_ID") and get_news_env("NAVER_CLIENT_SECRET"):
        news_fetch_result = _try_fetch_news(company, question)
        if news_fetch_result.get("status") == "ok":
            documents = _news_documents_only(search_external_docs(news_fetch_result.get("query", question), company.company_name, limit=10))[:5]
    else:
        news_fetch_result = {
            "status": "missing_config",
            "message": "뉴스 근거 수집에는 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET 설정이 필요합니다.",
        }

    dart_fetch_result = None
    if not documents and not news_requested:
        documents = search_external_docs(question, company.company_name, limit=5)
    if not documents and not news_requested and load_dart_api_key():
        dart_fetch_result = _try_fetch_dart_report(company, period.end_year)
        if dart_fetch_result.get("status") == "ok":
            documents = search_external_docs(question, company.company_name, limit=5)

    insight_lines = _build_insights(metrics, documents)
    evidence_lines = _build_evidence_based_explanation(metrics, documents)

    steps = [
        f"조회 대상: {company.company_name}({company.stock_code}), {period.start_year}~{period.end_year}년",
        f"기간 해석: {period.source}",
        _format_series_table(series, account_keys),
    ]
    if metrics:
        steps.append("계산 요약: " + " | ".join(_format_metric(metric) for metric in metrics))
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

    summary = f"{company.company_name}의 {period.start_year}~{period.end_year}년 추이를 분석했습니다."
    if news_requested and not documents:
        summary = f"{company.company_name}의 최근 주가 변동 원인은 뉴스 근거 확보 후 판단해야 합니다."

    return {
        "status": "ok",
        "summary": summary,
        "steps": steps,
        "company": company.__dict__,
        "period": period.__dict__,
        "accounts": account_keys,
        "series": series,
        "metrics": metrics,
        "external_references": documents,
        "dart_fetch": dart_fetch_result,
        "news_fetch": news_fetch_result,
    }


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
    if company_name and company_name in question:
        return question.strip()
    return f"{company_name or ''} {question}".strip()


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


def _resolve_comparison_companies(store: FinancialStatementStore, question: str) -> list[Any]:
    candidates = []
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
        if company and company.stock_code and company.stock_code not in {item.stock_code for item in candidates}:
            candidates.append(company)
    return candidates


def _analyze_market_comparison(question: str, store: FinancialStatementStore, companies: list[Any]) -> dict[str, Any]:
    company_summaries = []
    news_results = []
    documents = []
    for company in companies:
        available_years = store.available_years(company.stock_code)
        if not available_years:
            continue
        period = _extract_period(question, available_years)
        account_keys = ["revenue", "operating_income", "net_income"]
        series = store.get_account_series(company.stock_code, account_keys, period.start_year, period.end_year)
        metrics = _build_metric_summary(series, account_keys)
        company_summaries.append(
            {
                "company": company.__dict__,
                "period": period.__dict__,
                "series": series,
                "metrics": metrics,
            }
        )
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
        "summary": "두 기업 중 어느 주가가 더 오를지 단정하지 않고, 최신 뉴스와 재무 추이를 나눠 비교해야 합니다.",
        "steps": steps,
        "comparison": company_summaries,
        "external_references": documents,
        "news_fetch": {
            "status": "ok" if any(result.get("status") == "ok" for result in news_results) else "missing_config",
            "count": sum(result.get("count", 0) for result in news_results),
            "results": news_results,
        },
    }


def _clip_period(start_year: int, end_year: int, available_years: list[int], source: str) -> Period:
    min_year, max_year = min(available_years), max(available_years)
    return Period(max(start_year, min_year), min(end_year, max_year), source)


def _extract_accounts(question: str) -> list[str]:
    account_keys = []
    patterns = [
        ("revenue", ["매출", "영업수익", "revenue"]),
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


def _build_evidence_based_explanation(metrics: list[dict[str, Any]], documents: list[dict]) -> list[str]:
    if not documents:
        return []

    lines = []
    revenue = _find_metric(metrics, "revenue")
    operating_income = _find_metric(metrics, "operating_income")
    evidence_text = " ".join(doc.get("snippet", "") for doc in documents).lower()
    evidence_topics = _extract_evidence_topics(evidence_text)

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


def _extract_evidence_topics(text: str) -> list[str]:
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
