from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import numpy as np

from company_data.financial_store import FinancialStatementStore
from rag.external_rag import search_external_docs
from tools.company_trend_tool import _fill_missing_series_with_yfinance
from tools.stock_price_tool import _download_naver_price_data, _download_price_data, _to_yahoo_ticker
from tools.valuation_tool import _fetch_listed_shares


def analyze_advanced_question(question: str) -> dict[str, Any]:
    compact = question.replace(" ", "").lower()
    if any(token in compact for token in ["몬테카를로", "기대수익률분포", "유리할확률"]):
        return _monte_carlo_return_comparison(question)
    if "기준금리" in compact and "환율" in compact:
        return _macro_scenario_analysis(question)
    if any(token in compact for token in ["dcf", "현금흐름할인", "10년fcf", "적정주가"]):
        return _ten_year_dcf(question)
    return {"status": "no_calculation", "summary": "고급 분석 유형을 확인하지 못했습니다.", "steps": []}


def _ten_year_dcf(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    company = _resolve_company(store, question)
    if not company:
        return {"status": "needs_company", "summary": "DCF를 계산할 기업명을 확인하지 못했습니다.", "steps": []}
    years = store.available_years(company.stock_code)
    if not years:
        return {"status": "no_data", "summary": f"{company.company_name}의 재무 데이터를 찾지 못했습니다.", "steps": []}
    end_year = max(years)
    rows = store.get_account_series(
        company.stock_code,
        ["operating_income", "operating_cash_flow", "total_assets", "current_assets", "current_liabilities"],
        max(min(years), end_year - 4),
        end_year,
    )
    rows = _fill_missing_series_with_yfinance(
        company,
        ["operating_income", "operating_cash_flow", "total_assets", "current_assets", "current_liabilities"],
        rows,
        None,
    )
    op_values = [(row["year"], _amount(row, "operating_income")) for row in rows if _amount(row, "operating_income") is not None]
    ocf_values = [(row["year"], _amount(row, "operating_cash_flow")) for row in rows if _amount(row, "operating_cash_flow") is not None]
    if not op_values:
        return {"status": "no_data", "summary": f"{company.company_name}의 DCF 기준 영업이익을 확인하지 못했습니다.", "steps": []}

    latest_ebit = op_values[-1][1]
    historical_growth = _cagr([value for _, value in op_values])
    near_growth = min(0.12, max(-0.05, historical_growth if historical_growth is not None else 0.04))
    terminal_growth = 0.02
    tax_rate = 0.22
    wacc = 0.085
    latest_ocf = ocf_values[-1][1] if ocf_values else latest_ebit * (1 - tax_rate)
    observed_fcf = _yfinance_latest_fcf(company)
    base_fcf = observed_fcf if observed_fcf and observed_fcf > 0 else latest_ebit * min(0.9, max(0.4, latest_ocf / latest_ebit if latest_ebit else 0.65))
    cash_conversion = base_fcf / latest_ebit if latest_ebit else 0.65

    notes = search_external_docs(f"{company.company_name} CapEx 설비투자 순운전자본 사업보고서", company.company_name, limit=8)
    note_hits = [doc for doc in notes if any(token in f"{doc.get('title', '')} {doc.get('snippet', '')}" for token in ["CapEx", "CAPEX", "설비투자", "운전자본", "재고자산"])]
    note_text = " | ".join(f"{doc.get('title')}: {doc.get('snippet')}" for doc in note_hits[:2])

    projections = []
    fcf_values = []
    for index in range(1, 11):
        fade = (10 - index) / 9 if index < 10 else 0
        growth = terminal_growth + (near_growth - terminal_growth) * fade
        ebit = latest_ebit * np.prod([1 + (terminal_growth + (near_growth - terminal_growth) * ((10 - year) / 9 if year < 10 else 0)) for year in range(1, index + 1)])
        fcf = base_fcf * np.prod([1 + (terminal_growth + (near_growth - terminal_growth) * ((10 - year) / 9 if year < 10 else 0)) for year in range(1, index + 1)])
        pv = fcf / ((1 + wacc) ** index)
        projections.append({"year": end_year + index, "growth": float(growth), "ebit": float(ebit), "fcf": float(fcf), "pv": float(pv)})
        fcf_values.append(float(fcf))
    terminal_value = fcf_values[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
    enterprise_value = sum(row["pv"] for row in projections) + terminal_value / ((1 + wacc) ** 10)
    shares = _fetch_listed_shares(company.stock_code, company.market)
    fair_price = enterprise_value / shares if shares else None

    steps = [
        f"기준 재무연도: {end_year}년, 최근 영업이익 {_money(latest_ebit)}, 기준 FCF {_money(base_fcf)}, 현금전환계수 {cash_conversion:.2f}",
        f"영업이익 성장률은 최근 추이 {near_growth * 100:.2f}%에서 10년 차 {terminal_growth * 100:.2f}%로 점진 수렴",
        f"가정: 법인세율 {tax_rate * 100:.1f}%, WACC {wacc * 100:.1f}%, 영구성장률 {terminal_growth * 100:.1f}%",
        "FCF 대용치 = 영업이익 × 과거 영업현금흐름 전환계수",
        *[f"{row['year']}년 FCF {_money(row['fcf'])}, 현재가치 {_money(row['pv'])}" for row in projections],
        f"기업가치: {_money(enterprise_value)}",
        f"주당 적정가치: {fair_price:,.0f}원" if fair_price else "상장주식수를 확인하지 못해 주당 적정가치는 계산하지 못했습니다.",
        f"확인된 공시 주석 근거: {note_text}" if note_text else "CapEx·운전자본 계획을 담은 최신 공시 주석을 확보하지 못해 과거 현금전환율을 사용했습니다.",
    ]
    return {
        "status": "ok",
        "mode": "advanced_dcf",
        "summary": f"{company.company_name}의 10년 FCF 기반 기업가치는 {_money(enterprise_value)}" + (f", 주당 적정가치는 {fair_price:,.0f}원입니다." if fair_price else "입니다."),
        "steps": steps,
        "company": company.__dict__,
        "projections": projections,
        "enterprise_value": enterprise_value,
        "fair_price": fair_price,
        "assumptions": {"wacc": wacc, "terminal_growth": terminal_growth, "tax_rate": tax_rate, "cash_conversion": cash_conversion},
        "external_references": note_hits[:3],
    }


def _monte_carlo_return_comparison(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    companies = _resolve_companies(store, question)
    if len(companies) < 2:
        return {"status": "needs_company", "summary": "확률분포를 비교할 두 기업을 확인하지 못했습니다.", "steps": []}
    returns = []
    used = []
    end = date.today()
    start = end - timedelta(days=365 * 3 + 30)
    for company in companies[:2]:
        frame = _price_frame(company, start, end)
        if frame is None or len(frame) < 252:
            continue
        log_returns = np.diff(np.log(frame["Close"].astype(float).to_numpy()))
        returns.append(log_returns[np.isfinite(log_returns)])
        used.append(company)
    if len(returns) < 2:
        return {"status": "no_data", "summary": "두 기업의 몬테카를로 분석에 필요한 주가 이력을 확보하지 못했습니다.", "steps": []}

    simulations = 10_000
    horizon = 252
    rng = np.random.default_rng(42)
    terminal_returns = []
    for values in returns:
        sampled = rng.choice(values, size=(simulations, horizon), replace=True)
        terminal_returns.append(np.exp(sampled.sum(axis=1)) - 1)
    probability = float(np.mean(terminal_returns[0] > terminal_returns[1]))
    results = []
    for company, values in zip(used, terminal_returns):
        p10, median, p90 = np.percentile(values, [10, 50, 90])
        results.append({"company": company.__dict__, "mean": float(values.mean()), "p10": float(p10), "median": float(median), "p90": float(p90), "loss_probability": float(np.mean(values < 0))})
    steps = [
        "최근 약 3년의 일간 로그수익률을 복원추출해 252거래일 경로 10,000개를 생성했습니다.",
        *[f"{row['company']['company_name']}: 평균 {row['mean']*100:.2f}%, 중앙값 {row['median']*100:.2f}%, 10~90% 구간 {row['p10']*100:.2f}%~{row['p90']*100:.2f}%, 손실확률 {row['loss_probability']*100:.2f}%" for row in results],
        f"{used[0].company_name}의 1년 수익률이 {used[1].company_name}보다 높을 확률: {probability*100:.2f}%",
        "과거 수익률 분포가 유지된다는 가정의 부트스트랩 결과이며 미래 성과를 보장하지 않습니다.",
    ]
    return {"status": "ok", "mode": "monte_carlo_comparison", "summary": f"{used[0].company_name}가 {used[1].company_name}보다 유리할 추정 확률은 {probability*100:.2f}%입니다.", "steps": steps, "simulations": results, "probability_first_outperforms": probability, "horizon_days": horizon, "simulation_count": simulations}


def _macro_scenario_analysis(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    company = _resolve_company(store, question)
    if not company:
        return {"status": "needs_company", "summary": "시나리오를 분석할 기업명을 확인하지 못했습니다.", "steps": []}
    rate_shock = (_extract_percent(question, "기준금리") or 1.0) / 100
    fx_shock = (_extract_percent(question, "환율") or 10.0) / 100
    years = store.available_years(company.stock_code)
    end_year = max(years)
    rows = store.get_account_series(company.stock_code, ["operating_income", "total_assets", "total_liabilities"], end_year, end_year)
    rows = _fill_missing_series_with_yfinance(company, ["operating_income", "total_assets", "total_liabilities"], rows, None)
    latest = rows[-1] if rows else {}
    operating_income = _amount(latest, "operating_income")
    assets = _amount(latest, "total_assets")
    liabilities = _amount(latest, "total_liabilities")
    if operating_income is None:
        return {"status": "no_data", "summary": f"{company.company_name}의 기준 영업이익을 확인하지 못했습니다.", "steps": []}
    debt_ratio = min(0.8, max(0.1, liabilities / assets)) if assets and liabilities else 0.45
    exporter = any(token in (company.industry_name or "") for token in ["자동차", "전자", "반도체", "기계", "화학"])
    fx_elasticity = 0.55 if exporter else 0.15
    rate_elasticity = 1.8 * debt_ratio
    fx_effect = fx_shock * fx_elasticity
    rate_effect = -rate_shock * rate_elasticity
    total_effect = fx_effect + rate_effect
    scenario_income = operating_income * (1 + total_effect)
    base_wacc = 0.085
    scenario_wacc = base_wacc + rate_shock * debt_ratio
    value_change = (1 + total_effect) * base_wacc / scenario_wacc - 1
    latest_price = _latest_price(company)
    scenario_price = latest_price * (1 + value_change) if latest_price else None
    steps = [
        f"기준: {end_year}년 영업이익 {_money(operating_income)}, 부채 민감도 {debt_ratio:.2f}",
        f"환율 {fx_shock*100:.1f}% 상승 효과: 영업이익 {fx_effect*100:+.2f}% (수출 업종 탄력도 {fx_elasticity:.2f})",
        f"기준금리 {rate_shock*100:.1f}%p 상승 효과: 영업이익 {rate_effect*100:+.2f}% (금리 탄력도 {rate_elasticity:.2f})",
        f"복합 시나리오 영업이익: {_money(scenario_income)} ({total_effect*100:+.2f}%)",
        f"WACC {base_wacc*100:.2f}% → {scenario_wacc*100:.2f}%, 가치 변화 추정 {value_change*100:+.2f}%",
        f"현재가 기준 시나리오 주가: {scenario_price:,.0f}원" if scenario_price else "현재 주가를 확보하지 못해 시나리오 주가는 비율로만 제시했습니다.",
        "환율·금리 탄력도는 업종과 재무구조 기반 민감도 가정이며 인과 예측이 아닙니다.",
    ]
    return {"status": "ok", "mode": "macro_scenario", "summary": f"복합 충격 시 {company.company_name}의 영업이익은 {total_effect*100:+.2f}%, 적정가치 대용치는 {value_change*100:+.2f}% 변하는 것으로 추정됩니다.", "steps": steps, "company": company.__dict__, "base_operating_income": operating_income, "scenario_operating_income": scenario_income, "value_change": value_change, "latest_price": latest_price, "scenario_price": scenario_price, "assumptions": {"rate_shock": rate_shock, "fx_shock": fx_shock, "debt_ratio": debt_ratio, "fx_elasticity": fx_elasticity, "rate_elasticity": rate_elasticity}}


def _resolve_companies(store: FinancialStatementStore, question: str) -> list[Any]:
    companies, seen = [], set()
    for chunk in re.split(r"\s*(?:와|과|랑|하고|및|vs\.?|VS|비교|,)", question):
        company = store.resolve_company(chunk)
        if company and company.stock_code not in seen:
            seen.add(company.stock_code)
            companies.append(company)
    return companies


def _resolve_company(store: FinancialStatementStore, question: str):
    aliases = {"현대차": "현대자동차", "하이닉스": "SK하이닉스"}
    for alias, canonical in aliases.items():
        if alias in question:
            company = store.resolve_company(canonical)
            if company:
                return company
    return store.resolve_company(question)


def _yfinance_latest_fcf(company: Any) -> float | None:
    try:
        import pandas as pd
        import yfinance as yf

        cashflow = yf.Ticker(_to_yahoo_ticker(company.stock_code, company.market)).cashflow
        for label in ["Free Cash Flow", "Operating Cash Flow"]:
            if cashflow is not None and not cashflow.empty and label in cashflow.index:
                values = cashflow.loc[label].dropna()
                if not values.empty and pd.notna(values.iloc[0]):
                    return float(values.iloc[0])
    except Exception:
        pass
    return None


def _price_frame(company: Any, start: date, end: date):
    try:
        frame = _download_naver_price_data(company.stock_code, start, end)
        if frame is not None and not frame.empty:
            return frame
    except Exception:
        pass
    try:
        frame = _download_price_data(_to_yahoo_ticker(company.stock_code, company.market), start, end)
        return frame if frame is not None and not frame.empty else None
    except Exception:
        return None


def _latest_price(company: Any) -> float | None:
    frame = _price_frame(company, date.today() - timedelta(days=30), date.today())
    return float(frame["Close"].iloc[-1]) if frame is not None and not frame.empty else None


def _amount(row: dict[str, Any], key: str) -> float | None:
    item = row.get(key) if row else None
    return float(item["amount"]) if isinstance(item, dict) and item.get("amount") is not None else None


def _cagr(values: list[float]) -> float | None:
    if len(values) < 2 or values[0] <= 0 or values[-1] <= 0:
        return None
    return (values[-1] / values[0]) ** (1 / (len(values) - 1)) - 1


def _extract_percent(question: str, label: str) -> float | None:
    match = re.search(rf"{label}[^0-9]{{0,12}}([0-9]+(?:\.[0-9]+)?)\s*%?p?", question)
    return float(match.group(1)) if match else None


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_0000_0000_0000:
        return f"{sign}{value / 1_0000_0000_0000:.2f}조원"
    if value >= 1_0000_0000:
        return f"{sign}{value / 1_0000_0000:.2f}억원"
    return f"{sign}{value:,.0f}원"
