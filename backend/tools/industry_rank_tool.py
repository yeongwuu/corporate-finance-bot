from __future__ import annotations

import re
import sqlite3
from typing import Any

from company_data.financial_store import FinancialStatementStore
from dart_client import DartClient, load_dart_api_key
from tools.company_analysis_tool import _format_amount
from tools.company_analysis_tool import _map_dart_accounts


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

SEMICONDUCTOR_KEYWORDS = [
    "반도체",
    "전자집적회로",
    "다이오드",
    "트랜지스터",
    "메모리",
    "웨이퍼",
    "집적회로",
]

SEMICONDUCTOR_COMPANY_NAMES = [
    "삼성전자",
    "SK하이닉스",
    "DB하이텍",
    "LX세미콘",
    "SK실트론",
    "한미반도체",
    "리노공업",
    "원익IPS",
]

REPRESENTATIVE_SECTOR_COMPANIES = {
    "증권": [
        ("미래에셋증권", "006800"),
        ("NH투자증권", "005940"),
        ("삼성증권", "016360"),
        ("키움증권", "039490"),
        ("대신증권", "003540"),
    ],
    "은행": [
        ("KB금융", "105560"),
        ("신한지주", "055550"),
        ("하나금융지주", "086790"),
        ("우리금융지주", "316140"),
        ("기업은행", "024110"),
    ],
    "보험": [
        ("삼성생명", "032830"),
        ("삼성화재", "000810"),
        ("DB손해보험", "005830"),
        ("현대해상", "001450"),
        ("한화생명", "088350"),
    ],
    "자동차": [
        ("현대차", "005380"),
        ("기아", "000270"),
        ("현대모비스", "012330"),
        ("HL만도", "204320"),
        ("한온시스템", "018880"),
    ],
    "2차전지": [
        ("LG에너지솔루션", "373220"),
        ("삼성SDI", "006400"),
        ("에코프로비엠", "247540"),
        ("포스코퓨처엠", "003670"),
        ("엘앤에프", "066970"),
    ],
    "엔터테인먼트": [
        ("하이브", "352820"),
        ("에스엠", "041510"),
        ("JYP Ent.", "035900"),
        ("와이지엔터테인먼트", "122870"),
        ("디어유", "376300"),
    ],
}

SECTOR_ALIASES = {
    "증권": ["증권", "증권사", "금융투자", "브로커리지"],
    "은행": ["은행", "은행주", "금융지주"],
    "보험": ["보험", "보험사", "생명보험", "손해보험"],
    "자동차": ["자동차", "완성차", "모빌리티"],
    "2차전지": ["2차전지", "이차전지", "배터리"],
    "엔터테인먼트": ["엔터테인먼트", "엔터사", "엔터 기업", "연예기획사"],
}


def resolve_representative_sector(text: str) -> str | None:
    compact = text.replace(" ", "").lower()
    for sector, aliases in SECTOR_ALIASES.items():
        if any(alias.replace(" ", "").lower() in compact for alias in aliases):
            return sector
    return None


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

    if _asks_representative_companies(question):
        return _representative_industry_companies(store, question)

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


def _representative_industry_companies(store: FinancialStatementStore, question: str) -> dict[str, Any]:
    industry = _extract_industry(question)
    rows = select_representative_companies(store, industry, limit=5)
    if not rows:
        return {
            "status": "no_data",
            "summary": f"{industry} 대표 기업을 선정할 재무 데이터를 찾지 못했습니다.",
            "steps": ["업종명, 회사명 키워드, 최신연도 매출액을 함께 확인합니다."],
            "industry": industry,
        }

    latest_year = max(row["fiscal_year"] for row in rows)
    return {
        "status": "ok",
        "mode": "representative_companies",
        "summary": f"{industry} 대표 기업은 최신연도 매출액 기준 상위 {len(rows)}개사로 선정했습니다.",
        "steps": [
            f"선정 방식: 업종명에 {industry} 관련 키워드가 포함된 기업과, 삼성전자처럼 업종명은 다르지만 반도체 사업을 영위하는 주요 기업을 후보군에 포함한 뒤 매출액이 확인되는 기업을 기준으로 정렬했습니다.",
            f"정렬 기준: {latest_year}년 매출액 내림차순",
            "선정 기업: "
            + " / ".join(
                f"{row['rank']}. {row['company_name']}({row['stock_code'] or '-'}) {_format_amount(row['revenue'])}"
                for row in rows
            ),
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


def select_representative_companies(store: FinancialStatementStore, industry: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = _query_ranked_companies(store, industry, max(limit, 12), include_representatives=True)
    if industry == "반도체":
        rows = _merge_required_semiconductor_companies(store, rows)
    rows = sorted(rows, key=lambda row: row.get("revenue") or 0, reverse=True)
    if industry == "반도체":
        sk_hynix = next((row for row in rows if row.get("company_name") == "SK하이닉스"), None)
        if sk_hynix and sk_hynix not in rows[:limit]:
            selected = rows[: max(0, limit - 1)]
            if all(row.get("company_name") != "SK하이닉스" for row in selected):
                selected.append(sk_hynix)
            rows = selected + [row for row in rows if row not in selected and row is not sk_hynix]
    for index, row in enumerate(rows[:limit], start=1):
        row["rank"] = index
    return rows[:limit]


def _merge_required_semiconductor_companies(store: FinancialStatementStore, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {row["company_name"]: row for row in rows}
    for name in ["삼성전자", "SK하이닉스"]:
        if name in by_name:
            continue
        company = store.resolve_company(name)
        if not company:
            continue
        latest_year = company.latest_year
        revenue = _dart_revenue(company.stock_code, company.company_name, latest_year)
        by_name[name] = {
            "rank": 0,
            "fiscal_year": latest_year,
            "stock_code": company.stock_code,
            "company_name": company.company_name,
            "market": company.market,
            "industry_name": company.industry_name,
            "revenue": revenue or 0.0,
            "revenue_display": _format_amount(revenue) if revenue else "보완 필요",
            "revenue_source": "dart" if revenue else "missing",
        }
    return list(by_name.values())


def _dart_revenue(stock_code: str | None, company_name: str | None, fiscal_year: int) -> float | None:
    if not load_dart_api_key():
        return None
    try:
        result = DartClient().fetch_financial_accounts(
            stock_code=stock_code,
            corp_name=company_name,
            fiscal_year=fiscal_year,
        )
    except Exception:
        return None
    if result.get("status") != "ok":
        return None
    accounts = _map_dart_accounts(result.get("accounts") or [])
    revenue = accounts.get("revenue")
    if not revenue:
        return None
    return revenue.get("amount")


def _query_ranked_companies(
    store: FinancialStatementStore, industry: str, limit: int, include_representatives: bool = False
) -> list[dict[str, Any]]:
    keywords = _keywords_for_industry(industry)
    where_parts = []
    params: list[Any] = []
    for keyword in keywords:
        where_parts.append("(company_name LIKE ? OR industry_name LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if include_representatives and industry == "반도체":
        placeholders = ", ".join("?" for _ in SEMICONDUCTOR_COMPANY_NAMES)
        where_parts.append(f"company_name IN ({placeholders})")
        params.extend(SEMICONDUCTOR_COMPANY_NAMES)

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
    representative_sector = resolve_representative_sector(question)
    if representative_sector:
        return representative_sector
    if "반도체" in question:
        return "반도체"
    if "바이오" in question:
        return "바이오"
    if any(term in question for term in ["방산", "방위산업", "국방", "항공우주", "우주항공"]):
        return "방산"

    # Clean conversational phrases and grab the core noun
    cleaned = question
    cleaned = re.sub(r"(?:의|을|를|이|가|은|는|에|에\s*대한|에\s*대해)\s+", " ", cleaned)
    cleaned = re.sub(r"(?:대표기업|대표회사|대표종목|대표|상위|관련|기업들|기업|회사|종목|알려줘|알려|알려주세요|알려줘요|알려주라|추천|추천해줘|분석|분석해줘|알아봐)\b.*", "", cleaned)
    cleaned = re.sub(r"[?.,!]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) >= 2:
        return cleaned

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


def _asks_representative_companies(question: str) -> bool:
    compact = question.replace(" ", "")
    return any(token in compact for token in ["대표기업", "대표회사", "대표종목"])


def _keywords_for_industry(industry: str) -> list[str]:
    if industry == "바이오":
        return BIO_KEYWORDS
    if industry == "반도체":
        return SEMICONDUCTOR_KEYWORDS
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
