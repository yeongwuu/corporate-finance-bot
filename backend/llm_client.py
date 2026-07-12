from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent


def build_final_answer(question: str, tool_name: str, calculation: dict, references: list[dict]) -> str:
    if calculation.get("status") == "latest_news":
        return build_latest_news_answer(calculation)
    if calculation.get("status") == "needs_latest_disclosure":
        return build_rule_based_answer(tool_name, calculation, [])
    if tool_name == "industry_rank_tool" and calculation.get("status") == "ok":
        return build_industry_rank_answer(calculation)
    if calculation.get("mode") == "industry_growth_comparison":
        return build_industry_growth_comparison_answer(calculation)
    if calculation.get("mode") == "market_ratio_trend":
        return build_market_ratio_trend_answer(calculation)
    if calculation.get("ratio_series"):
        return build_ratio_trend_answer(calculation)
    if calculation.get("comparison"):
        return build_company_comparison_answer(calculation)
    if tool_name == "stock_price_tool" and calculation.get("status") == "ok":
        return build_stock_price_answer(calculation)
    if tool_name == "company_analysis_tool" and calculation.get("status") == "ok":
        return build_company_accounts_answer(calculation)

    provider = normalize_provider(get_env("LLM_PROVIDER"))
    if provider == "openai":
        try:
            return build_openai_answer(question, tool_name, calculation, references)
        except Exception:
            return build_rule_based_answer(tool_name, calculation, references)
    if provider == "gemini":
        try:
            return build_gemini_answer(question, tool_name, calculation, references)
        except Exception:
            return build_rule_based_answer(tool_name, calculation, references)
    return build_rule_based_answer(tool_name, calculation, references)


def build_attachment_answer(question: str, attachment: dict[str, Any]) -> str:
    provider = normalize_provider(get_env("LLM_PROVIDER"))
    if not provider and (get_env("LLM_API_KEY") or get_env("GEMINI_API_KEY")):
        provider = "gemini"
    prompt = build_attachment_prompt(question, attachment)
    if provider == "gemini":
        api_key = get_env("LLM_API_KEY") or get_env("GEMINI_API_KEY")
        model = (get_env("LLM_MODEL") or "gemini-3.1-flash-lite").removeprefix("models/")
        if not api_key:
            raise ValueError("LLM_API_KEY 또는 GEMINI_API_KEY가 설정되지 않았습니다.")
        return call_gemini_generate_content(api_key=api_key, model=model, prompt=prompt, attachment=attachment).strip()
    if provider == "openai":
        api_key = get_env("LLM_API_KEY") or get_env("OPENAI_API_KEY")
        model = get_env("LLM_MODEL") or "gpt-4.1-mini"
        if not api_key:
            raise ValueError("LLM_API_KEY 또는 OPENAI_API_KEY가 설정되지 않았습니다.")
        if not model:
            raise ValueError("LLM_MODEL이 설정되지 않았습니다.")
        return call_openai_responses(api_key=api_key, model=model, prompt=prompt, attachment=attachment).strip()
    raise ValueError("파일 문제 풀이는 LLM_PROVIDER와 LLM_API_KEY 설정이 필요합니다. Gemini를 쓰려면 LLM_PROVIDER=gemini로 설정하세요.")


def build_attachment_prompt(question: str, attachment: dict[str, Any]) -> str:
    text = attachment.get("text") or ""
    file_name = attachment.get("name") or "uploaded file"
    file_type = attachment.get("type") or "unknown"
    body = (
        "너는 재무관리/기업재무 문제를 푸는 튜터다.\n"
        "사용자가 업로드한 파일 또는 이미지의 문제를 읽고, 사용자가 지정한 번호나 조건에 맞춰 답한다.\n\n"
        "답변 원칙:\n"
        "1. 사용자가 특정 번호를 지정하면 해당 문제만 먼저 푼다.\n"
        "2. 계산 문제는 공식, 대입, 계산 결과를 순서대로 보여준다.\n"
        "3. 이미지/파일에서 문제 문구가 불명확하면 보이는 범위에서 해석한 가정을 먼저 말한다.\n"
        "4. 수식은 LaTeX 형식으로 작성한다.\n"
        "5. 답변은 한국어로 간결하게 작성한다.\n\n"
        f"사용자 질문: {question}\n"
        f"파일명: {file_name}\n"
        f"파일 형식: {file_type}\n"
    )
    if text:
        body += f"\n파일 텍스트:\n{text[:12000]}"
    elif attachment.get("data"):
        body += "\n파일은 이미지/PDF 바이너리로 첨부되어 있다. 첨부 내용을 직접 읽어 문제를 풀이한다."
    return body


def build_ratio_trend_answer(calculation: dict) -> str:
    company = calculation.get("company") or {}
    period = calculation.get("period") or {}
    ratio_series = calculation.get("ratio_series") or []
    company_name = company.get("company_name", "해당 기업")
    start_year = period.get("start_year") or (ratio_series[0]["year"] if ratio_series else "")
    end_year = period.get("end_year") or (ratio_series[-1]["year"] if ratio_series else "")
    ratio_labels = []
    for row in ratio_series:
        for key, item in row.items():
            if key != "year" and isinstance(item, dict) and item.get("label") not in ratio_labels:
                ratio_labels.append(item.get("label"))
    title_label = " 및 ".join(ratio_labels[:3]) if ratio_labels else "재무 비율"
    lines = [f"{company_name}의 {start_year}~{end_year}년 {title_label} 추이는 다음과 같습니다."]

    for row in ratio_series:
        values = []
        for key, item in row.items():
            if key == "year" or not isinstance(item, dict):
                continue
            values.append(f"{item['label']} {item['display']}")
        if values:
            lines.append(f"{row['year']}년: " + ", ".join(values))

    ratio_keys = []
    for row in ratio_series:
        for key, item in row.items():
            if key != "year" and isinstance(item, dict) and key not in ratio_keys:
                ratio_keys.append(key)
    for key in ratio_keys:
        values = [row[key] | {"year": row["year"]} for row in ratio_series if row.get(key)]
        if len(values) < 2:
            continue
        first, last = values[0], values[-1]
        direction = "상승" if last["value"] > first["value"] else "하락" if last["value"] < first["value"] else "유지"
        lines.append(f"{last['label']}은 {first['year']}년 {first['display']}에서 {last['year']}년 {last['display']}로 {direction}했습니다.")

    lines.append("계산에는 보유 재무제표의 손익계산서와 재무상태표 주요 계정을 사용했습니다.")
    return "\n".join(lines)


def build_market_ratio_trend_answer(calculation: dict) -> str:
    company = calculation.get("company") or {}
    period = calculation.get("period") or {}
    rows = calculation.get("market_ratio_series") or []
    ratio_keys = calculation.get("ratio_keys") or []
    company_name = company.get("company_name", "해당 기업")
    labels = ", ".join({"per": "PER", "pbr": "PBR", "psr": "PSR"}.get(key, key.upper()) for key in ratio_keys)
    lines = [
        f"{company_name}의 {period.get('start_year')}~{period.get('end_year')}년 {labels} 추이는 다음과 같습니다."
    ]

    for row in rows:
        values = ", ".join(f"{item['label']} {item['display']}배" for item in row.get("ratios", {}).values())
        if values:
            lines.append(f"{row['year']}년: {values}")

    for ratio_key in ratio_keys:
        values = [
            {"year": row["year"], **row["ratios"][ratio_key]}
            for row in rows
            if ratio_key in row.get("ratios", {})
        ]
        if len(values) < 2:
            continue
        first, last = values[0], values[-1]
        direction = "상승" if last["value"] > first["value"] else "하락" if last["value"] < first["value"] else "유지"
        lines.append(
            f"{last['label']}은 {first['year']}년 {first['display']}배에서 "
            f"{last['year']}년 {last['display']}배로 {direction}했습니다."
        )

    lines.append("계산은 연도말 종가와 상장주식수로 시가총액을 추정한 뒤 재무제표의 순이익, 자본총계, 매출액과 결합했습니다.")
    return "\n".join(lines)


def build_company_accounts_answer(calculation: dict) -> str:
    company = calculation.get("company") or {}
    accounts = calculation.get("accounts") or {}
    ratios = calculation.get("ratios") or {}
    year = calculation.get("year")
    company_name = company.get("company_name", "해당 기업")
    account_order = [
        "revenue",
        "cost_of_sales",
        "gross_profit",
        "selling_admin_expenses",
        "operating_income",
        "net_income",
        "total_assets",
        "current_assets",
        "current_liabilities",
        "total_liabilities",
        "total_equity",
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
    ]
    lines = [f"{company_name}의 {year}년 주요 계정은 다음과 같습니다."]
    for key in account_order:
        account = accounts.get(key)
        if account:
            lines.append(f"- {account['label']}: {_format_display_amount(account['amount'])}")

    ratio_lines = []
    ratio_labels = {
        "cost_of_sales_ratio": "매출원가율",
        "selling_admin_expense_ratio": "판관비율",
        "operating_margin": "매출액영업이익률",
        "net_margin": "매출액순이익률",
        "debt_to_equity": "부채비율",
        "current_ratio": "유동비율",
        "cfo_to_net_income": "영업현금흐름/순이익",
    }
    for key, label in ratio_labels.items():
        value = ratios.get(key)
        if value is not None:
            ratio_lines.append(f"{label} {_format_display_ratio(value)}")
    if ratio_lines:
        lines.append("주요 비율은 " + ", ".join(ratio_lines) + "입니다.")

    return "\n".join(lines)


def build_company_comparison_answer(calculation: dict) -> str:
    comparison = calculation.get("comparison") or []
    if not comparison:
        return calculation.get("summary") or "비교할 기업 데이터를 찾지 못했습니다."
    lines = ["질문에 나온 순서대로 각 기업을 먼저 계산한 뒤 비교했습니다."]
    for index, item in enumerate(comparison, start=1):
        company = item.get("company") or {}
        period = item.get("period") or {}
        name = company.get("company_name", f"{index}번째 기업")
        lines.append(f"{index}. {name}({company.get('stock_code', '-')})")
        if period:
            lines.append(f"기간: {period.get('start_year')}~{period.get('end_year')}년")
        if item.get("ratio_series"):
            latest = item["ratio_series"][-1]
            values = []
            for key, value in latest.items():
                if key != "year" and isinstance(value, dict):
                    values.append(f"{value['label']} {value['display']}")
            if values:
                lines.append(f"{latest['year']}년 기준: " + ", ".join(values))
        elif item.get("ratio_keys"):
            dart_fetch = item.get("dart_fetch") or {}
            if dart_fetch.get("status") and dart_fetch.get("status") != "ok":
                lines.append(
                    "수익성 비율 계산에 필요한 매출액, 영업이익 또는 당기순이익 데이터가 부족합니다. "
                    f"{dart_fetch.get('message', '')}".strip()
                )
            else:
                lines.append("수익성 비율 계산에 필요한 매출액, 영업이익 또는 당기순이익 데이터가 부족합니다.")
        elif item.get("metrics"):
            for metric in item["metrics"]:
                lines.append(
                    f"{metric['label']}: {metric['start_year']}년 {_format_display_amount(metric['start_amount'])} -> "
                    f"{metric['end_year']}년 {_format_display_amount(metric['end_amount'])}"
                )
    lines.append("비교 결과는 보유 재무제표 기준이며, 투자 추천이나 목표주가 의견은 아닙니다.")
    return "\n".join(lines)


def build_industry_growth_comparison_answer(calculation: dict) -> str:
    comparison = calculation.get("comparison") or []
    company = calculation.get("company") or {}
    industry = calculation.get("industry") or "동종 업종"
    base_name = company.get("company_name", "기준 기업")
    base_item = next((item for item in comparison if item.get("is_base")), None)
    lines = []
    if base_item:
        metric = (base_item.get("metrics") or [{}])[0]
        lines.append(
            f"{base_name}는 {industry} 비교군 {len(comparison)}개사 중 매출 CAGR 기준 "
            f"{base_item.get('rank')}위입니다."
        )
        lines.append(
            f"{metric.get('start_year')}~{metric.get('end_year')}년 누적 매출상승률은 "
            f"{_format_display_percent(metric.get('growth'))}, CAGR은 "
            f"{_format_display_percent(metric.get('cagr'))}입니다."
        )
    else:
        lines.append(calculation.get("summary") or f"{industry} 기업들의 매출상승률을 비교했습니다.")
    if calculation.get("selection_note"):
        lines.append(calculation["selection_note"])

    lines.append("매출상승률 상위 기업은 다음과 같습니다.")
    for item in comparison[:7]:
        name = (item.get("company") or {}).get("company_name", "-")
        marker = " (기준 기업)" if item.get("is_base") else ""
        metrics = item.get("metrics") or []
        if not metrics:
            lines.append(f"{item.get('rank')}. {name}{marker}: {item.get('missing_reason') or '매출액 데이터 부족으로 계산 보류'}")
            continue
        metric = metrics[0]
        lines.append(
            f"{item.get('rank')}. {name}{marker}: "
            f"누적 {_format_display_percent(metric.get('growth'))}, "
            f"CAGR {_format_display_percent(metric.get('cagr'))}"
        )

    lines.append("아래 그래프는 각 기업의 매출 CAGR을 비교한 막대그래프입니다.")
    lines.append("분류는 재무제표 업종명과 회사명 키워드 기준이므로 공식 산업 분류와 일부 차이가 있을 수 있습니다.")
    return "\n".join(lines)


def build_stock_price_answer(calculation: dict) -> str:
    company = calculation.get("company") or {}
    stats = calculation.get("stats") or {}
    period = calculation.get("period") or {}
    company_name = company.get("company_name", "해당 기업")
    period_label = period.get("label") or "조회 기간"
    price_source = calculation.get("price_source") or "Yahoo Finance"
    lines = [
        f"{company_name}의 {period_label} 주가 흐름은 {price_source} 종가 기준으로 조회했습니다.",
    ]
    if period.get("fallback"):
        lines.append(
            f"요청 기간({period.get('requested_start')}~{period.get('requested_end')})의 가격 데이터가 비어 있어 "
            f"확인 가능한 구간({period.get('start')}~{period.get('end')})으로 재조회했습니다."
        )
    if stats:
        lines.append(
            f"시작 종가는 {_format_display_price(stats.get('first_close'))}, "
            f"최근 종가는 {_format_display_price(stats.get('last_close'))}이며, "
            f"기간 수익률은 {stats.get('cumulative_return_display', '-')}입니다."
        )
        lines.append(
            f"조회 기간의 최저 종가는 {_format_display_price(stats.get('min_close'))}, "
            f"최고 종가는 {_format_display_price(stats.get('max_close'))}, "
            f"종가 평균은 {_format_display_price(stats.get('close_mean'))}, "
            f"종가 표준편차는 {_format_display_price(stats.get('close_std'))}, "
            f"최대낙폭은 {stats.get('max_drawdown_display', '-')}입니다."
        )
    lines.append("아래 그래프는 같은 기간의 종가 추이를 나타냅니다. 투자 추천이나 목표주가 의견은 아닙니다.")
    return "\n".join(lines)


def _format_display_price(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.0f}원"


def _format_display_percent(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def _format_display_amount(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    amount = abs(float(amount))
    if amount >= 1_0000_0000_0000:
        return f"{sign}{amount / 1_0000_0000_0000:.2f}조원"
    if amount >= 1_0000_0000:
        return f"{sign}{amount / 1_0000_0000:.2f}억원"
    if amount >= 10_000:
        return f"{sign}{amount / 10_000:.2f}만원"
    return f"{sign}{amount:,.0f}원"


def _format_display_ratio(value: float) -> str:
    return f"{value * 100:.2f}%"


def build_industry_rank_answer(calculation: dict) -> str:
    if calculation.get("mode") == "representative_companies":
        return build_representative_companies_answer(calculation)
    if calculation.get("mode") == "industry_group":
        return build_industry_group_answer(calculation)

    ranking = calculation.get("ranking") or []
    industry = calculation.get("industry") or "산업"
    year = calculation.get("year")
    if not ranking:
        return calculation.get("summary") or f"{industry} 관련 기업 목록을 찾지 못했습니다."

    lines = [f"{year}년 매출액 기준 {industry} 관련 상위 {len(ranking)}개 기업은 다음과 같습니다."]
    for row in ranking:
        lines.append(
            f"{row['rank']}. {row['company_name']}({row['stock_code']}) - "
            f"매출액 {row['revenue_display']}, 업종 {row.get('industry_name') or '-'}"
        )
    lines.append("분류는 회사명 또는 업종명 키워드 기준이므로, 공식 산업 분류와는 차이가 있을 수 있습니다.")
    return "\n".join(lines)


def build_representative_companies_answer(calculation: dict) -> str:
    industry = calculation.get("industry") or "산업"
    ranking = calculation.get("ranking") or []
    year = calculation.get("year") or "-"
    if not ranking:
        return calculation.get("summary") or f"{industry} 대표 기업을 찾지 못했습니다."

    lines = [
        f"{industry} 대표 기업은 {year}년 매출 상위 기업과 주요 반도체 기업을 함께 반영해 {len(ranking)}개사로 선정했습니다.",
        f"선정 기준은 엑셀 기준 {industry} 후보군에서 매출 상위 기업을 고르되, 삼성전자·SK하이닉스처럼 주요 반도체 기업은 후보군에 포함하는 방식입니다.",
    ]
    for row in ranking:
        lines.append(
            f"{row['rank']}. {row['company_name']}({row.get('stock_code') or '-'}): "
            f"매출액 {row['revenue_display']}, 업종 {row.get('industry_name') or '-'}"
        )
    lines.append("이후 반도체 대표 기업 분석이 필요한 질문은 위 선정 기업을 기준으로 비교합니다.")
    return "\n".join(lines)


def build_industry_group_answer(calculation: dict) -> str:
    groups = calculation.get("groups") or []
    if not groups:
        return calculation.get("summary") or "업종 그룹을 찾지 못했습니다."

    lines = [calculation.get("summary") or "업종명 기준으로 기업을 그룹화했습니다."]
    for group in groups[:8]:
        companies = group.get("companies") or []
        names = ", ".join(f"{item['company_name']}({item['stock_code']})" for item in companies[:8])
        major = group.get("major_industry")
        industry = group.get("industry_name") or "-"
        label = f"{major} / {industry}" if major else industry
        lines.append(f"- {label}: {group.get('count', len(companies))}개 기업")
        if names:
            lines.append(f"  예시: {names}")
    lines.append("대분류 산업군은 재무제표의 세부 업종명을 규칙 기반으로 묶은 값입니다.")
    return "\n".join(lines)


def build_latest_news_answer(calculation: dict) -> str:
    documents = calculation.get("external_references") or []
    company = (calculation.get("company") or {}).get("company_name") or "해당 기업"
    query = ((calculation.get("news_fetch") or {}).get("query") or "").strip()
    period = _extract_period_label(query)
    matched_doc = _select_news_doc(documents, period)
    if not matched_doc:
        return (
            f"{company}{_period_suffix(period)} 영업이익은 뉴스 검색 결과에서 직접 확인할 수 있는 수치를 찾지 못했습니다.\n\n"
            "정확한 수치는 DART 잠정실적 공시나 회사 IR 실적 발표 자료에서 확인하는 것이 좋습니다."
        )

    snippet = _clean_news_text(matched_doc.get("snippet") or matched_doc.get("title") or "")
    operating_income = _extract_operating_income(snippet)
    if operating_income:
        first_sentence = f"{company}{_period_suffix(period)} 영업이익은 뉴스 기준으로 {operating_income}{_amount_copula(operating_income)}"
    else:
        first_sentence = f"{company}{_period_suffix(period)} 영업이익은 뉴스에서 직접 수치를 확인해야 합니다."

    evidence = snippet
    if len(evidence) > 260:
        evidence = f"{evidence[:260].rstrip()}..."
    return "\n\n".join(
        [
            first_sentence,
            f"뉴스 요약에서는 {evidence}",
            "확정 수치는 원문 기사와 DART 잠정실적 공시를 함께 확인하는 것이 좋습니다.",
        ]
    )


def _extract_period_label(text: str) -> str | None:
    year_match = re.search(r"(20[1-3]\d)\s*년", text)
    quarter_match = re.search(r"([1-4])\s*분기", text)
    if year_match and quarter_match:
        return f"{year_match.group(1)}년 {quarter_match.group(1)}분기"
    if quarter_match:
        return f"{quarter_match.group(1)}분기"
    return None


def _period_suffix(period: str | None) -> str:
    return f"의 {period}" if period else "의 최신 분기"


def _select_news_doc(documents: list[dict], period: str | None) -> dict | None:
    if not documents:
        return None
    if period:
        compact_period = period.replace(" ", "")
        for doc in documents:
            text = _clean_news_text(f"{doc.get('title', '')} {doc.get('snippet', '')}").replace(" ", "").lower()
            if compact_period.lower() in text and "영업이익" in text:
                return doc
        quarter_match = re.search(r"([1-4])분기", compact_period)
        if quarter_match:
            quarter = quarter_match.group(0)
            quarter_alias = f"{quarter_match.group(1)}q"
            for doc in documents:
                text = _clean_news_text(f"{doc.get('title', '')} {doc.get('snippet', '')}").replace(" ", "").lower()
                if (quarter in text or quarter_alias in text) and "영업이익" in text:
                    return doc
        return None
    return next((doc for doc in documents if "영업이익" in _clean_news_text(doc.get("snippet", ""))), documents[0])


def _clean_news_text(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", str(text))
    cleaned = re.sub(r"#+\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_operating_income(text: str) -> str | None:
    cleaned = _clean_news_text(text)
    patterns = [
        r"영업이익(?:은|은\s|이|이\s|은\s*약|은\s*전년.*?|[:：]|\s)+([+-]?[0-9,.]+\s*조\s*[0-9,.]*\s*억?원)",
        r"영업이익(?:은|이|[:：]|\s)+([+-]?[0-9,.]+\s*조원)",
        r"영업이익(?:은|이|[:：]|\s)+([+-]?[0-9,.]+\s*억원)",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return re.sub(r"\s+", "", match.group(1))
    return None


def _amount_copula(amount: str) -> str:
    return "이었습니다." if amount.endswith("원") else "였습니다."


def build_rule_based_answer(tool_name: str, calculation: dict, references: list[dict]) -> str:
    summary = calculation.get("summary") or calculation.get("message") or "질문을 해석했지만 충분한 계산 결과를 찾지 못했습니다."
    paragraphs = [summary]
    needs_structure = _needs_structured_answer(calculation)

    steps = calculation.get("steps", [])
    if steps:
        narrative_steps = []
        for step in steps:
            cleaned = _clean_step(step)
            if cleaned:
                narrative_steps.append(cleaned)
        if narrative_steps:
            if needs_structure:
                paragraphs.extend(narrative_steps[:5])
            else:
                paragraphs.append(" ".join(narrative_steps[:3]))

    if references and calculation.get("status") not in {"needs_latest_disclosure", "missing_data", "needs_company", "no_data"}:
        has_news = any(str(reference.get("title", "")).startswith("news_") for reference in references)
        paragraphs.append(
            "재무제표와 관련 뉴스에서 확인되는 범위 안에서 해석했습니다."
            if has_news
            else "재무제표와 확보된 근거 자료 범위 안에서 해석했습니다."
        )

    return "\n\n".join(paragraphs)


def _needs_structured_answer(calculation: dict) -> bool:
    return bool(calculation.get("metrics") or calculation.get("series") or calculation.get("comparison"))


def _clean_step(step: str) -> str:
    cleaned = str(step).strip()
    prefixes = [
        "조회 대상:",
        "시장/업종:",
        "주요계정:",
        "간단 분석:",
        "계산 요약:",
        "기간 해석:",
        "RAG 근거 후보:",
    ]
    if cleaned.startswith("데이터 원천:"):
        return ""
    if cleaned.startswith("RAG 근거 후보:"):
        return ""
    if cleaned.startswith("뉴스 근거 후보:"):
        cleaned = cleaned.replace("뉴스 근거 후보:", "뉴스에서 확인되는 내용:", 1).strip()
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned.replace(prefix, "", 1).strip()
            break
    cleaned = cleaned.replace(" | ", ", ")
    cleaned = cleaned.replace(" / ", "\n")
    if cleaned and cleaned[-1] not in ".!?。":
        cleaned = f"{cleaned}."
    return cleaned


def build_openai_answer(question: str, tool_name: str, calculation: dict, references: list[dict]) -> str:
    api_key = get_env("LLM_API_KEY")
    model = get_env("LLM_MODEL")
    if not api_key:
        raise ValueError("LLM_API_KEY가 설정되지 않았습니다.")
    if not model:
        raise ValueError("LLM_MODEL이 설정되지 않았습니다.")

    prompt = build_analysis_prompt(question, tool_name, calculation, references)
    response = call_openai_responses(api_key=api_key, model=model, prompt=prompt)
    return response.strip()


def build_gemini_answer(question: str, tool_name: str, calculation: dict, references: list[dict]) -> str:
    api_key = get_env("LLM_API_KEY")
    model = (get_env("LLM_MODEL") or "gemini-3.1-flash-lite").removeprefix("models/")
    if not api_key:
        raise ValueError("LLM_API_KEY가 설정되지 않았습니다.")

    prompt = build_analysis_prompt(question, tool_name, calculation, references)
    response = call_gemini_generate_content(api_key=api_key, model=model, prompt=prompt)
    return response.strip()


def build_analysis_prompt(question: str, tool_name: str, calculation: dict, references: list[dict]) -> str:
    payload = {
        "question": question,
        "tool_name": tool_name,
        "calculation": calculation,
        "references": references,
    }
    return (
        "너는 한국 상장기업을 분석하는 재무 애널리스트 AI다.\n"
        "아래 JSON에는 사용자의 질문, 계산 결과, 재무제표 추이, 뉴스와 공시 후보가 들어 있다.\n\n"
        "답변 원칙:\n"
        "1. 사용자가 단순 사실 확인이나 특정 수치를 물으면 자연스러운 문단형 답변으로 짧게 답한다.\n"
        "2. calculation.conversation_context가 있으면 현재 질문이 이전 회사, 기간, 지표를 이어받는지 자연스럽게 판단한다.\n"
        "3. 근거 문서에 없는 산업명, 제품명, 업황 원인은 새로 만들어내지 않는다.\n"
        "4. 자료가 부족하면 '현재 확보된 자료만으로는 단정하기 어렵다'고 말하고, 사용자가 바로 이해할 수 있는 범위에서만 설명한다.\n"
        "5. 뉴스나 공시 후보가 있으면 '뉴스에서는 ...'처럼 자연스럽게 연결하되 출처 시스템 이름을 노출하지 않는다.\n"
        "6. calculation.stats가 있으면 주가 백테스팅 결과로 보고, 기간 수익률, 평균, 표준편차, 변동성, 최대낙폭을 간결히 요약한다.\n"
        "7. 투자 추천, 목표주가, 매수/매도 의견은 내지 않는다.\n"
        "8. 답변은 한국어로, 실무 보고서처럼 간결하게 작성한다.\n\n"
        "9. calculation.company.industry_name과 맞지 않는 산업 이슈를 전망 근거로 쓰지 않는다. "
        "예를 들어 바이오/의약품 기업에는 반도체, GPU, 데이터센터, 모바일, 디스플레이 업황을 언급하지 않는다. "
        "업종과 맞는 근거가 없으면 재무 추이 중심으로만 설명하고 근거 부족을 명확히 말한다.\n\n"
        "금지 표현:\n"
        "- RAG, backend, frontend, API, tool, calculation, 내부 지식 문서, 추가 근거, 확인 문서 같은 구현 용어를 답변에 쓰지 않는다.\n"
        "- 불필요한 Markdown 볼드체, 장식 이모티콘, 체크리스트형 '확인해야 할 추가 근거' 섹션을 만들지 않는다.\n\n"
        "- 출처 URL은 프론트엔드 하단 출처 카드에서 별도로 표시되므로 본문에 URL을 길게 나열하지 않는다.\n\n"
        "형식 원칙:\n"
        "- 기본은 소제목 없이 1~3개 자연스러운 문단으로 답한다.\n"
        "- 사용자가 비교, 추이, 원인 분석, 여러 지표 분석을 요청한 경우에만 필요한 소제목을 사용한다.\n"
        "- 소제목을 쓰더라도 Markdown 표시는 최소화하고, 중요한 소제목에만 짧게 쓴다.\n\n"
        "수식 표기:\n"
        "- 수식이 필요하면 일반 텍스트로 깨지게 쓰지 말고 LaTeX 형식으로 작성한다.\n"
        "- 짧은 수식은 `$P_0 = \\frac{D_1}{k-g}$`처럼 `$...$` 안에 넣는다.\n"
        "- 긴 수식은 `$$...$$` 블록으로 작성한다.\n\n"
        f"JSON:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


def call_openai_responses(api_key: str, model: str, prompt: str, attachment: dict[str, Any] | None = None) -> str:
    base_url = (get_env("LLM_BASE_URL") or "https://api.openai.com/v1/responses").rstrip("/")
    content = [
        {
            "type": "input_text",
            "text": prompt,
        }
    ]
    if attachment and _is_image_attachment(attachment) and attachment.get("data"):
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{attachment.get('type')};base64,{attachment.get('data')}",
            }
        )
    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": content,
            }
        ],
    }
    request = urllib.request.Request(
        base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45, context=_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {error_body[:500]}") from exc

    text = extract_response_text(data)
    if not text:
        raise RuntimeError("OpenAI 응답에서 텍스트를 찾지 못했습니다.")
    return text


def call_gemini_generate_content(api_key: str, model: str, prompt: str, attachment: dict[str, Any] | None = None) -> str:
    base_url = (get_env("LLM_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    url = f"{base_url}/models/{model}:generateContent?key={api_key}"
    parts = [{"text": prompt}]
    if attachment and attachment.get("data") and _is_inline_attachment(attachment):
        parts.append(
            {
                "inlineData": {
                    "mimeType": attachment.get("type") or "application/octet-stream",
                    "data": attachment.get("data"),
                }
            }
        )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1200,
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45, context=_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API HTTP {exc.code}: {error_body[:500]}") from exc

    parts = []
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if part.get("text"):
                parts.append(part["text"])
    if not parts:
        raise RuntimeError("Gemini 응답에서 텍스트를 찾지 못했습니다.")
    return "\n".join(parts)


def _is_image_attachment(attachment: dict[str, Any]) -> bool:
    return str(attachment.get("type") or "").startswith("image/")


def _is_inline_attachment(attachment: dict[str, Any]) -> bool:
    mime_type = str(attachment.get("type") or "")
    return mime_type.startswith("image/") or mime_type == "application/pdf"


def extract_response_text(data: dict[str, Any]) -> str:
    if data.get("output_text"):
        return data["output_text"]

    parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts)


def normalize_provider(provider: str | None) -> str | None:
    if not provider:
        return None
    lowered = provider.strip().lower()
    if "gemini" in lowered:
        return "gemini"
    if "openai" in lowered:
        return "openai"
    return lowered


def get_env(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value.strip()

    for env_path in [BACKEND_ROOT / ".env", PROJECT_ROOT / ".env"]:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            if key.strip() == name:
                cleaned = raw_value.strip().strip('"').strip("'")
                return cleaned or None
    return None


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None
