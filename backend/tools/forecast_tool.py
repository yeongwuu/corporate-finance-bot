from __future__ import annotations

import re
import logging
from statistics import median
from typing import Any

logger = logging.getLogger("corporate_finance_bot")

from company_data.financial_store import FinancialStatementStore
from tools.company_analysis_tool import _format_amount, _format_ratio
from tools.company_trend_tool import ACCOUNT_LABELS


FORECASTABLE_ACCOUNTS = {
    "revenue": ["매출", "매출액", "영업수익", "revenue"],
    "operating_income": ["영업이익", "operating income"],
    "net_income": ["순이익", "당기순이익", "net income"],
    "operating_cash_flow": ["영업현금흐름", "영업활동현금흐름", "cfo"],
    "total_assets": ["자산", "자산총계"],
    "total_liabilities": ["부채", "부채총계"],
    "total_equity": ["자본", "자본총계"],
}


def forecast_company_metric(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    try:
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
            "summary": "전망할 회사명을 찾지 못했습니다.",
            "steps": ["예: 삼성전자 최근 5개년 매출 추이로 2026년 매출을 전망해줘"],
        }

    available_years = store.available_years(company.stock_code)
    if len(available_years) < 3:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 전망 계산에 필요한 연속 연도 데이터가 부족합니다.",
            "steps": [f"가용 연도: {', '.join(map(str, available_years))}"],
            "company": company.__dict__,
        }

    account_key = _extract_account(question)
    target_year = _extract_target_year(question, available_years)
    history_count = _extract_history_count(question) or 5
    base_years = [year for year in available_years if year < target_year]
    if len(base_years) < 3:
        return {
            "status": "no_data",
            "summary": f"{target_year}년 전망에 사용할 과거 데이터가 부족합니다.",
            "steps": [f"가용 연도: {', '.join(map(str, available_years))}"],
            "company": company.__dict__,
            "target_year": target_year,
        }

    selected_years = sorted(base_years)[-history_count:]
    start_year = selected_years[0]
    end_year = selected_years[-1]
    series = store.get_account_series(company.stock_code, [account_key], start_year, end_year)
    values = [
        {"year": row["year"], "amount": row[account_key]["amount"], "label": row[account_key]["label"]}
        for row in series
        if row.get(account_key) and row[account_key].get("amount") is not None
    ]

    if len(values) < 3 and account_key in ["revenue", "operating_income", "net_income"]:
        try:
            import yfinance as yf
            import pandas as pd
            from tools.stock_price_tool import _to_yahoo_ticker
            ticker = _to_yahoo_ticker(company.stock_code, company.market)
            t = yf.Ticker(ticker)
            df_income = t.income_stmt
            if not df_income.empty:
                row_candidates = []
                if account_key == "revenue":
                    row_candidates = ["Total Revenue", "Operating Revenue", "Revenue"]
                elif account_key == "operating_income":
                    row_candidates = ["Operating Income", "Operating Income or Loss"]
                elif account_key == "net_income":
                    row_candidates = ["Net Income", "Net Income Common Stockholders"]
                
                matched_row = None
                for cand in row_candidates:
                    if cand in df_income.index:
                        matched_row = cand
                        break
                
                if matched_row is not None:
                    yfinance_values = []
                    for col in df_income.columns:
                        year = col.year if hasattr(col, "year") else int(str(col)[:4])
                        if start_year <= year <= end_year:
                            val = df_income.loc[matched_row, col]
                            if hasattr(val, "iloc"):
                                val = val.iloc[0]
                            if val is not None and not pd.isna(val):
                                yfinance_values.append({
                                    "year": int(year),
                                    "amount": float(val),
                                    "label": ACCOUNT_LABELS.get(account_key, account_key)
                                })
                    if len(yfinance_values) >= 3:
                        values = sorted(yfinance_values, key=lambda x: x["year"])
        except Exception as e:
            logger.error(f"yfinance income stmt fallback failed: {e}")

    if len(values) < 3:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 {ACCOUNT_LABELS.get(account_key, account_key)} 전망에 필요한 데이터가 부족합니다.",
            "steps": [],
            "company": company.__dict__,
            "target_year": target_year,
        }

    methods = _forecast_methods(values, target_year)
    base_forecast = median([method["value"] for method in methods])
    low_forecast = min(method["value"] for method in methods)
    high_forecast = max(method["value"] for method in methods)
    label = ACCOUNT_LABELS.get(account_key, account_key)

    steps = [
        f"전망 대상: {company.company_name}({company.stock_code}) {target_year}년 {label}",
        f"사용 기간: {values[0]['year']}~{values[-1]['year']}년 최근 {len(values)}개년",
        "전망 방식: CAGR, 선형 추세, 최근 성장률 가중평균을 함께 비교했습니다.",
        "과거 추이: " + " / ".join(f"{item['year']}년 {_format_amount(item['amount'])}" for item in values),
        "전망 결과: "
        f"보수 {_format_amount(low_forecast)}, 기준 {_format_amount(base_forecast)}, 낙관 {_format_amount(high_forecast)}",
    ]
    for method in methods:
        steps.append(f"{method['label']}: {_format_amount(method['value'])} ({method['description']})")

    return {
        "status": "ok",
        "summary": (
            f"{company.company_name}의 {target_year}년 {label} 기준 전망치는 "
            f"{_format_amount(base_forecast)}입니다. 단순 추세 기반 추정치이므로 공식 가이던스나 시장 컨센서스와는 다를 수 있습니다."
        ),
        "steps": steps,
        "company": company.__dict__,
        "account": account_key,
        "account_label": label,
        "target_year": target_year,
        "history_years": len(values),
        "series": values,
        "forecast": {
            "base": base_forecast,
            "low": low_forecast,
            "high": high_forecast,
            "methods": methods,
        },
    }


def _extract_account(question: str) -> str:
    lowered = question.lower()
    for account_key, tokens in FORECASTABLE_ACCOUNTS.items():
        if any(token in lowered for token in tokens):
            return account_key
    return "revenue"


def _extract_target_year(question: str, available_years: list[int]) -> int:
    years = [int(match) for match in re.findall(r"20[1-3]\d", question)]
    if years:
        return max(years)
    return max(available_years) + 1


def _extract_history_count(question: str) -> int | None:
    match = re.search(r"최근\s*(\d+)\s*(?:개년|년)", question)
    if not match:
        return None
    return max(3, int(match.group(1)))


def _forecast_methods(values: list[dict[str, Any]], target_year: int) -> list[dict[str, Any]]:
    return [
        _cagr_forecast(values, target_year),
        _linear_forecast(values, target_year),
        _weighted_growth_forecast(values, target_year),
    ]


def _cagr_forecast(values: list[dict[str, Any]], target_year: int) -> dict[str, Any]:
    first = values[0]
    last = values[-1]
    years = max(1, last["year"] - first["year"])
    if first["amount"] > 0 and last["amount"] > 0:
        growth = (last["amount"] / first["amount"]) ** (1 / years) - 1
        forecast = last["amount"] * ((1 + growth) ** (target_year - last["year"]))
        description = f"{first['year']}~{last['year']}년 CAGR {_format_ratio(growth)} 적용"
    else:
        growth = 0
        forecast = last["amount"]
        description = "음수 또는 0 이하 값이 포함되어 마지막 연도 값을 기준으로 사용"
    return {"key": "cagr", "label": "CAGR 기준", "value": forecast, "growth": growth, "description": description}


def _linear_forecast(values: list[dict[str, Any]], target_year: int) -> dict[str, Any]:
    xs = [item["year"] for item in values]
    ys = [item["amount"] for item in values]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator if denominator else 0
    intercept = y_mean - slope * x_mean
    forecast = intercept + slope * target_year
    return {
        "key": "linear",
        "label": "선형 추세 기준",
        "value": forecast,
        "growth": None,
        "description": "연도별 금액의 직선 추세를 연장",
    }


def _weighted_growth_forecast(values: list[dict[str, Any]], target_year: int) -> dict[str, Any]:
    growth_rates = []
    for prev, current in zip(values, values[1:]):
        if prev["amount"]:
            growth_rates.append((current["amount"] - prev["amount"]) / abs(prev["amount"]))
    if not growth_rates:
        growth = 0
    else:
        weights = list(range(1, len(growth_rates) + 1))
        growth = sum(rate * weight for rate, weight in zip(growth_rates, weights)) / sum(weights)
    last = values[-1]
    forecast = last["amount"] * ((1 + growth) ** (target_year - last["year"]))
    return {
        "key": "weighted_growth",
        "label": "최근 성장률 기준",
        "value": forecast,
        "growth": growth,
        "description": f"최근 연도 성장률에 더 높은 가중치 적용({_format_ratio(growth)})",
    }
