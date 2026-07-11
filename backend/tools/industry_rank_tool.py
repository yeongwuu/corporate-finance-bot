from __future__ import annotations

import re
import sqlite3
from typing import Any

from company_data.financial_store import FinancialStatementStore
from tools.company_analysis_tool import _format_amount


BIO_KEYWORDS = [
    "바이오",
    "제약",
    "의약",
    "의료",
    "생명",
    "헬스",
    "신약",
    "생물학적",
    "연구개발",
]


def rank_industry_companies(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    try:
        store.ensure_database()
    except FileNotFoundError as exc:
        return {
            "status": "missing_data",
            "summary": "재무제표 데이터에서 산업별 기업 목록을 확인하지 못했습니다.",
            "steps": [str(exc)],
        }

    if _asks_industry_grouping(question):
        return _group_industry_companies(store, question)

    industry = _extract_industry(question)
    limit = _extract_limit(question)
    rows = _query_ranked_companies(store, industry, limit)
    if not rows:
        return {
            "status": "no_data",
            "summary": f"{industry} 관련 기업 목록을 찾지 못했습니다.",
            "steps": ["현재 데이터는 업종명이 표준 산업분류 기준이라 사용자가 말한 산업명과 정확히 일치하지 않을 수 있습니다."],
            "industry": industry,
        }

    latest_year = max(row["fiscal_year"] for row in rows)
    lines = [
        f"{index + 1}. {row['company_name']}({row['stock_code']}): 매출액 {_format_amount(row['revenue'])}, 업종 {row['industry_name'] or '-'}"
        for index, row in enumerate(rows)
    ]
    summary = f"{latest_year}년 매출액 기준 {industry} 관련 상위 {len(rows)}개 기업입니다."
    return {
        "status": "ok",
        "summary": summary,
        "steps": [
            f"분류 기준: 회사명 또는 업종명에 {', '.join(_keywords_for_industry(industry))} 키워드가 포함된 기업",
            f"정렬 기준: {latest_year}년 매출액 내림차순",
            "상위 기업: " + " / ".join(lines),
        ],
        "industry": industry,
        "ranking": rows,
        "year": latest_year,
    }


def _group_industry_companies(store: FinancialStatementStore, question: str) -> dict[str, Any]:
    company = store.resolve_company(question)
    limit = _extract_limit(question)
    if company:
        rows = _query_same_industry_companies(store, company.industry_name or "", limit)
        if not rows:
            return {
                "status": "no_data",
                "summary": f"{company.company_name}의 업종({company.industry_name})에 속한 기업을 찾지 못했습니다.",
                "steps": [],
                "industry": company.industry_name,
            }
        return {
            "status": "ok",
            "mode": "industry_group",
            "summary": (
                f"{company.company_name}의 세부 업종은 '{company.industry_name}'이고, "
                f"대분류 산업군은 '{_major_industry(company.industry_name or company.company_name)}'입니다."
            ),
            "company": company.__dict__,
            "industry": company.industry_name,
            "major_industry": _major_industry(company.industry_name or company.company_name),
            "groups": [
                {
                    "industry_name": company.industry_name,
                    "major_industry": _major_industry(company.industry_name or company.company_name),
                    "count": len(rows),
                    "companies": rows,
                }
            ],
        }

    industry = _extract_industry(question)
    groups = _query_keyword_industry_groups(store, industry, limit)
    if not groups:
        return {
            "status": "no_data",
            "summary": f"{industry} 관련 업종 그룹을 찾지 못했습니다.",
            "steps": ["회사명 또는 업종명에 포함된 키워드를 기준으로 업종을 그룹화합니다."],
            "industry": industry,
        }
    return {
        "status": "ok",
        "mode": "industry_group",
        "summary": f"{industry} 관련 기업을 업종명 기준으로 그룹화했습니다.",
        "industry": industry,
        "groups": groups,
    }


def _query_same_industry_companies(store: FinancialStatementStore, industry_name: str, limit: int) -> list[dict[str, Any]]:
    if not industry_name:
        return []
    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT stock_code, company_name, market, industry_name, MAX(fiscal_year) AS latest_year
            FROM financial_items
            WHERE industry_name = ?
              AND stock_code != ''
            GROUP BY stock_code, company_name, market, industry_name
            ORDER BY company_name
            LIMIT ?
            """,
            (industry_name, limit),
        ).fetchall()
    finally:
        conn.close()
    return [_company_row(row) for row in rows]


def _query_keyword_industry_groups(store: FinancialStatementStore, industry: str, limit: int) -> list[dict[str, Any]]:
    keywords = _keywords_for_industry(industry)
    where_parts = []
    params: list[Any] = []
    for keyword in keywords:
        where_parts.append("(company_name LIKE ? OR industry_name LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"""
            WITH companies AS (
                SELECT stock_code, company_name, market, industry_name, MAX(fiscal_year) AS latest_year
                FROM financial_items
                WHERE stock_code != ''
                  AND industry_name != ''
                  AND ({' OR '.join(where_parts)})
                GROUP BY stock_code, company_name, market, industry_name
            ),
            ranked AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (PARTITION BY industry_name ORDER BY company_name) AS rn,
                    COUNT(*) OVER (PARTITION BY industry_name) AS industry_count
                FROM companies
            )
            SELECT *
            FROM ranked
            WHERE rn <= ?
            ORDER BY industry_count DESC, industry_name, rn
            """,
            (*params, max(3, limit)),
        ).fetchall()
    finally:
        conn.close()

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        industry_name = row["industry_name"]
        group = grouped.setdefault(
            industry_name,
            {
                "industry_name": industry_name,
                "major_industry": _major_industry(industry_name),
                "count": int(row["industry_count"]),
                "companies": [],
            },
        )
        if len(group["companies"]) < limit:
            group["companies"].append(_company_row(row))
    return sorted(grouped.values(), key=lambda item: item["count"], reverse=True)


def _query_ranked_companies(store: FinancialStatementStore, industry: str, limit: int) -> list[dict[str, Any]]:
    keywords = _keywords_for_industry(industry)
    where_parts = []
    params: list[Any] = []
    for keyword in keywords:
        where_parts.append("(company_name LIKE ? OR industry_name LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    query = f"""
        WITH latest AS (
            SELECT stock_code, MAX(fiscal_year) AS fiscal_year
            FROM financial_items
            GROUP BY stock_code
        ),
        revenue AS (
            SELECT
                f.fiscal_year,
                f.stock_code,
                f.company_name,
                f.market,
                f.industry_name,
                MAX(ABS(f.amount)) AS revenue
            FROM financial_items f
            JOIN latest l
              ON f.stock_code = l.stock_code
             AND f.fiscal_year = l.fiscal_year
            WHERE f.statement_type = 'PL'
              AND f.amount IS NOT NULL
              AND (
                f.account_code IN ('ifrs-full_Revenue', 'ifrs_Revenue')
                OR f.account_name IN ('매출액', '영업수익', '수익(매출액)')
                OR f.account_name LIKE '%매출액%'
                OR f.account_name LIKE '%영업수익%'
              )
              AND ({' OR '.join(where_parts)})
            GROUP BY f.fiscal_year, f.stock_code, f.company_name, f.market, f.industry_name
        )
        SELECT *
        FROM revenue
        ORDER BY revenue DESC
        LIMIT ?
    """
    params.append(limit)

    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    return [
        {
            "rank": index + 1,
            "fiscal_year": int(row["fiscal_year"]),
            "stock_code": row["stock_code"],
            "company_name": row["company_name"],
            "market": row["market"],
            "industry_name": row["industry_name"],
            "revenue": float(row["revenue"]),
            "revenue_display": _format_amount(float(row["revenue"])),
        }
        for index, row in enumerate(rows)
    ]


def _company_row(row: sqlite3.Row) -> dict[str, Any]:
    industry_name = row["industry_name"]
    return {
        "stock_code": row["stock_code"],
        "company_name": row["company_name"],
        "market": row["market"],
        "industry_name": industry_name,
        "major_industry": _major_industry(industry_name),
        "latest_year": int(row["latest_year"]),
    }


def _extract_industry(question: str) -> str:
    if "바이오" in question:
        return "바이오"
    if any(term in question for term in ["방산", "방위산업", "국방", "항공우주", "우주항공"]):
        return "방산"
    match = re.search(r"([가-힣A-Za-z0-9]+)\s*(?:산업|업종|섹터)", question)
    return match.group(1) if match else "산업"


def _extract_limit(question: str) -> int:
    match = re.search(r"상위\s*(\d+)", question)
    if match:
        return max(1, min(30, int(match.group(1))))
    return 10


def _asks_industry_grouping(question: str) -> bool:
    compact = question.replace(" ", "")
    return any(
        token in compact
        for token in [
            "업종별",
            "산업군",
            "그룹화",
            "그룹핑",
            "같은업종",
            "속한업종",
            "무슨업종",
            "어떤업종",
            "어느업종",
            "무슨산업",
            "어떤산업",
            "어느산업",
        ]
    )


def _keywords_for_industry(industry: str) -> list[str]:
    if industry == "바이오":
        return BIO_KEYWORDS
    if industry == "방산":
        return ["방산", "방위", "국방", "항공", "우주", "무기", "탄약", "군수"]
    return [industry]


def _major_industry(industry_name: str) -> str:
    text = industry_name.lower()
    rules = [
        ("바이오/제약", ["바이오", "제약", "의약", "생물학", "의료용 물질", "기초 의약", "신약", "헬스케어"]),
        ("의료기기/헬스케어", ["의료용 기기", "의료기기", "진단", "치과", "정형외과"]),
        ("반도체/전자부품", ["반도체", "전자부품", "전자집적회로", "다이오드", "트랜지스터"]),
        ("디스플레이/통신장비", ["디스플레이", "통신", "방송장비", "영상", "음향"]),
        ("소프트웨어/IT서비스", ["소프트웨어", "정보서비스", "컴퓨터 프로그래밍", "시스템 통합", "데이터베이스"]),
        ("방산/항공우주", ["항공기", "우주선", "방위", "탄약", "무기", "군수"]),
        ("자동차/모빌리티", ["자동차", "차체", "트레일러", "운송장비", "자동차 부품"]),
        ("화학/소재", ["화학", "플라스틱", "고무", "섬유", "금속", "비금속", "유리", "시멘트"]),
        ("기계/장비", ["기계", "장비", "공작", "펌프", "압축기", "산업용"]),
        ("에너지/전기장비", ["전기", "전지", "배터리", "발전", "에너지", "전동기"]),
        ("건설/부동산", ["건설", "토목", "건축", "부동산"]),
        ("금융", ["금융", "보험", "투자", "신탁"]),
        ("유통/소비재", ["도매", "소매", "유통", "음식료", "식료품", "의복", "화장품"]),
        ("미디어/엔터", ["영화", "방송", "음악", "게임", "출판", "광고", "콘텐츠"]),
    ]
    for label, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return label
    return "기타 제조/서비스"
