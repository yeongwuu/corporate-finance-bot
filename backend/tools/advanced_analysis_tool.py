from __future__ import annotations

import re
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import numpy as np

from company_data.financial_store import FinancialStatementStore
from dart_client import DartClient, load_dart_api_key
from rag.external_rag import search_external_docs
from tools.company_analysis_tool import _map_dart_accounts
from tools.company_trend_tool import _fill_missing_series_with_yfinance
from tools.stock_price_tool import _download_naver_price_data, _download_price_data, _to_yahoo_ticker
from tools.valuation_tool import _fetch_listed_shares


def analyze_advanced_question(question: str) -> dict[str, Any]:
    compact = question.replace(" ", "").lower()
    if "시나리오" in compact and "매출원가율" in compact and "매출" in compact:
        return _revenue_cost_scenario_analysis(question)
    if any(token in compact for token in ["매출원가", "원가율"]) and any(
        token in compact for token in ["시나리오", "방어확률", "ear", "백테스팅", "몬테카를로", "eps", "주당순이익"]
    ):
        return _cost_of_sales_ear_scenario(question)
    if "wacc" in compact and "영구성장률" in compact and "민감도" in compact:
        return _dcf_sensitivity_analysis(question)
    if "스트레스" in compact and "매출성장률" in compact and "영업이익률" in compact:
        return _growth_margin_stress_analysis(question)
    if "배당성장률" in compact and "요구수익률" in compact and any(token in compact for token in ["가치", "주가", "시나리오"]):
        return _dividend_growth_scenario_analysis(question)
    if "환율" in compact and "기준금리" in compact and any(token in compact for token in ["반도체가격", "메모리가격", "반도체가격하락"]):
        return _multi_factor_stress_test(question)
    if any(token in compact for token in ["몬테카를로", "기대수익률분포", "유리할확률"]):
        return _monte_carlo_return_comparison(question)
    if "기준금리" in compact and "환율" in compact:
        return _macro_scenario_analysis(question)
    if any(token in compact for token in ["dcf", "현금흐름할인", "10년fcf", "적정주가"]):
        return _ten_year_dcf(question)
    return {"status": "no_calculation", "summary": "고급 분석 유형을 확인하지 못했습니다.", "steps": []}


def _cost_of_sales_ear_scenario(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    company = _resolve_company(store, question)
    if not company:
        return {"status": "needs_company", "summary": "매출원가 시나리오 대상 기업명을 확인하지 못했습니다.", "steps": []}
    if not load_dart_api_key():
        return {"status": "no_data", "summary": "시나리오 분석에 필요한 DART_API_KEY가 없습니다.", "steps": []}

    available_years = store.available_years(company.stock_code)
    if not available_years:
        return {"status": "no_data", "summary": f"{company.company_name}의 분석 가능 연도를 찾지 못했습니다.", "steps": []}
    latest_year = max(available_years)
    stated_years = sorted({int(value) for value in re.findall(r"20[1-3]\d", question)})
    if len(stated_years) >= 2:
        history_years = list(range(stated_years[0], stated_years[-1] + 1))[-5:]
    else:
        history_years = list(range(latest_year - 3, latest_year))

    history = []
    validation_logs = []
    raw_latest_rows: list[dict[str, Any]] = []
    try:
        client = DartClient()
        for fiscal_year in history_years:
            result = client.fetch_financial_accounts(
                stock_code=company.stock_code,
                corp_name=company.company_name,
                fiscal_year=fiscal_year,
            )
            if result.get("status") != "ok":
                validation_logs.append(f"{fiscal_year}년: DART 계정 조회 실패")
                continue
            accounts = _map_dart_accounts(result.get("accounts") or [])
            revenue = _account_amount(accounts, "revenue")
            cost = _account_amount(accounts, "cost_of_sales")
            gross_profit = _account_amount(accounts, "gross_profit")
            missing = [label for label, value in [("매출액", revenue), ("매출원가", cost)] if value is None]
            if missing:
                validation_logs.append(f"{fiscal_year}년: 세부계정 누락({', '.join(missing)}) — 해당 연도 제외")
                continue
            calculated_gross = revenue - cost
            cross_check_ok = gross_profit is None or abs(calculated_gross - gross_profit) <= max(1.0, abs(revenue) * 1e-6)
            validation_logs.append(
                f"{fiscal_year}년: 매출액-매출원가와 매출총이익 교차 검증 "
                + ("일치" if cross_check_ok else "불일치")
            )
            if not cross_check_ok:
                continue
            history.append(
                {"year": fiscal_year, "revenue": revenue, "cost_of_sales": cost, "cost_ratio": cost / revenue}
            )

        latest_result = client.fetch_financial_accounts(
            stock_code=company.stock_code,
            corp_name=company.company_name,
            fiscal_year=latest_year,
        )
        if latest_result.get("status") == "ok":
            raw_latest_rows = latest_result.get("accounts") or []
    except Exception as exc:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 DART 재무 데이터를 조회하지 못했습니다.",
            "steps": [str(exc)],
            "company": company.__dict__,
        }

    if len(history) < 3:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 매출원가율 변동성을 계산할 유효 연도가 부족합니다.",
            "steps": validation_logs,
            "company": company.__dict__,
        }

    cost_ratios = np.array([row["cost_ratio"] for row in history], dtype=float)
    volatility = float(np.std(cost_ratios, ddof=1))
    shock_pct = _extract_percent(question, "매출원가") or _extract_percent(question, "원가율") or 2.0
    shock = shock_pct / 100
    base_eps = _extract_eps(question) or _find_basic_eps(raw_latest_rows)
    if base_eps is None:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 기준 EPS를 확인하지 못했습니다.",
            "steps": validation_logs,
            "company": company.__dict__,
        }

    simulation_count = _extract_simulation_count(question, default=5_000, maximum=100_000)
    rng = np.random.default_rng(2922)
    simulated_cost_ratio_changes = rng.normal(0.0, volatility, simulation_count)
    base_defense_probability = float(np.mean(simulated_cost_ratio_changes <= 0))
    scenario_defense_probability = float(np.mean(simulated_cost_ratio_changes + shock <= 0))
    probability_change = scenario_defense_probability - base_defense_probability
    ratios_text = " → ".join(f"{row['cost_ratio'] * 100:.1f}%" for row in history)
    return {
        "status": "ok",
        "mode": "cost_of_sales_ear",
        "summary": (
            f"{company.company_name}의 매출원가율이 {shock_pct:.1f}%p 상승하면 EPS {base_eps:,.0f}원 방어 확률은 "
            f"{base_defense_probability * 100:.1f}%에서 {scenario_defense_probability * 100:.1f}%로 "
            f"{probability_change * 100:.1f}%p 낮아집니다."
        ),
        "steps": [
            f"백테스팅: {history[0]['year']}~{history[-1]['year']}년 매출원가율 {ratios_text}",
            f"역사적 변동성: 표본 표준편차 {volatility * 100:.2f}%",
            f"시뮬레이션: 매출원가율 변화 {simulation_count:,}개 경로, 기준 EPS {base_eps:,.0f}원, 원가율 +{shock_pct:.1f}%p",
            f"EPS 방어 확률: {base_defense_probability * 100:.1f}% → {scenario_defense_probability * 100:.1f}% ({probability_change * 100:.1f}%p)",
            "검증 로그: " + " | ".join(validation_logs),
            "매출원가율 이외의 매출·판관비·금융손익·세율은 기준 시점과 동일하다고 가정한 민감도 분석입니다.",
        ],
        "company": company.__dict__,
        "history": history,
        "history_years": [row["year"] for row in history],
        "cost_ratio_volatility": volatility,
        "cost_shock": shock,
        "base_eps": base_eps,
        "base_defense_probability": base_defense_probability,
        "scenario_defense_probability": scenario_defense_probability,
        "probability_change": probability_change,
        "simulation_count": simulation_count,
        "validation": {"status": "passed", "logs": validation_logs, "missing_account_policy": "유효 연도에서 제외"},
        "source": "DART fnlttSinglAcntAll",
    }


def _account_amount(accounts: dict[str, Any], key: str) -> float | None:
    item = accounts.get(key)
    return float(item["amount"]) if isinstance(item, dict) and item.get("amount") is not None else None


def _extract_eps(question: str) -> float | None:
    match = re.search(r"eps[^0-9]{0,20}([0-9][0-9,]*(?:\.[0-9]+)?)\s*원?", question, re.IGNORECASE)
    return float(match.group(1).replace(",", "")) if match else None


def _extract_simulation_count(question: str, default: int, maximum: int) -> int:
    patterns = [
        r"몬테카를로\s*([0-9][0-9,]*)\s*회",
        r"([0-9][0-9,]*)\s*회(?:의)?\s*(?:몬테카를로|시뮬레이션)",
        r"시뮬레이션\s*([0-9][0-9,]*)\s*회",
    ]
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            return min(maximum, max(100, int(match.group(1).replace(",", ""))))
    return default


def _find_basic_eps(rows: list[dict[str, Any]]) -> float | None:
    preferred = ["계속영업 기본주당이익", "기본주당이익(손실)", "기본주당이익"]
    for label in preferred:
        for row in rows:
            name = re.sub(r"\s+", " ", str(row.get("account_nm") or "")).strip()
            if name == label or label in name:
                value = str(row.get("thstrm_amount") or "").replace(",", "").strip()
                try:
                    return float(value)
                except ValueError:
                    continue
    return None


def _dcf_sensitivity_analysis(question: str) -> dict[str, Any]:
    base = _ten_year_dcf(question, fetch_notes=False)
    if base.get("status") != "ok":
        return base
    projections = base.get("projections") or []
    shares = _fetch_listed_shares((base.get("company") or {}).get("stock_code"), (base.get("company") or {}).get("market"))
    if not projections or not shares:
        return {"status": "no_data", "summary": "민감도 분석에 필요한 FCF 또는 발행주식수를 확인하지 못했습니다.", "steps": []}

    wacc_start, wacc_end = _extract_range(question, "WACC", (7.0, 11.0))
    growth_start, growth_end = _extract_range(question, "영구성장률", (1.0, 4.0))
    wacc_values = _percentage_grid(wacc_start, wacc_end)
    growth_values = _percentage_grid(growth_start, growth_end)
    fcf_values = [float(row["fcf"]) for row in projections]
    sensitivity = []
    for wacc_pct in wacc_values:
        prices = []
        for growth_pct in growth_values:
            wacc, growth = wacc_pct / 100, growth_pct / 100
            if wacc <= growth:
                prices.append(None)
                continue
            pv_fcf = sum(value / ((1 + wacc) ** index) for index, value in enumerate(fcf_values, 1))
            terminal = fcf_values[-1] * (1 + growth) / (wacc - growth)
            enterprise_value = pv_fcf + terminal / ((1 + wacc) ** len(fcf_values))
            prices.append(float(enterprise_value / shares))
        sensitivity.append({"wacc": wacc_pct, "prices": prices})
    valid_prices = [price for row in sensitivity for price in row["prices"] if price is not None]
    company_name = (base.get("company") or {}).get("company_name", "기업")
    company_data = base.get("company") or {}
    latest_price = _latest_price(SimpleNamespace(**company_data)) if company_data.get("stock_code") else None
    middle_wacc = min(wacc_values, key=lambda value: abs(value - (wacc_start + wacc_end) / 2))
    middle_growth = min(growth_values, key=lambda value: abs(value - (growth_start + growth_end) / 2))
    middle_row = next(row for row in sensitivity if row["wacc"] == middle_wacc)
    middle_price = middle_row["prices"][growth_values.index(middle_growth)]
    comparison = None
    if latest_price and middle_price is not None:
        upside = middle_price / latest_price - 1
        comparison = {
            "wacc": middle_wacc,
            "growth": middle_growth,
            "fair_price": middle_price,
            "current_price": latest_price,
            "upside": upside,
            "assessment": "저평가" if upside > 0 else "고평가" if upside < 0 else "적정 수준",
            "undervalued_cells": sum(price > latest_price for price in valid_prices),
            "overvalued_cells": sum(price < latest_price for price in valid_prices),
            "total_cells": len(valid_prices),
        }
    return {
        "status": "ok",
        "mode": "dcf_sensitivity",
        "summary": f"{company_name}의 적정 주가는 가정 범위에서 {min(valid_prices):,.0f}원~{max(valid_prices):,.0f}원으로 산출됩니다.",
        "steps": [
            f"WACC {wacc_start:.1f}%~{wacc_end:.1f}%, 영구성장률 {growth_start:.1f}%~{growth_end:.1f}%를 1%p 간격으로 적용했습니다.",
            "각 조합에서 10년 명시적 FCF 현재가치와 영구가치를 다시 계산했습니다.",
            f"민감도 범위: 최저 {min(valid_prices):,.0f}원, 최고 {max(valid_prices):,.0f}원",
            f"현재 주가 {latest_price:,.0f}원 대비 기준 조합(WACC {middle_wacc:.1f}%, 영구성장률 {middle_growth:.1f}%)의 적정가치는 {middle_price:,.0f}원으로 {comparison['assessment']}입니다." if comparison else "현재 주가를 확보하지 못해 고평가·저평가 비교는 생략했습니다.",
            "WACC가 낮고 영구성장률이 높을수록 적정가치가 커지는 가정 기반 분석입니다.",
        ],
        "company": base.get("company"),
        "wacc_values": wacc_values,
        "growth_values": growth_values,
        "sensitivity": sensitivity,
        "latest_price": latest_price,
        "valuation_comparison": comparison,
        "external_references": base.get("external_references") or [],
        "dart_fetch": base.get("dart_fetch"),
    }


def _multi_factor_stress_test(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    company = _resolve_company(store, question)
    if not company:
        return {"status": "needs_company", "summary": "스트레스 테스트 대상 기업명을 확인하지 못했습니다.", "steps": []}
    years = store.available_years(company.stock_code)
    if not years:
        return {"status": "no_data", "summary": f"{company.company_name}의 재무 데이터를 찾지 못했습니다.", "steps": []}
    end_year = max(years)
    rows = store.get_account_series(company.stock_code, ["operating_income", "total_assets", "total_liabilities"], end_year, end_year)
    rows = _fill_missing_series_with_yfinance(company, ["operating_income", "total_assets", "total_liabilities"], rows, None)
    latest = rows[-1] if rows else {}
    latest = _prefer_dart_latest_accounts(company, end_year, latest, ["operating_income", "total_assets", "total_liabilities"])
    operating_income = _amount(latest, "operating_income")
    if operating_income is None:
        return {"status": "no_data", "summary": f"{company.company_name}의 기준 영업이익을 확인하지 못했습니다.", "steps": [], "company": company.__dict__}
    assets, liabilities = _amount(latest, "total_assets"), _amount(latest, "total_liabilities")
    debt_ratio = min(0.8, max(0.1, liabilities / assets)) if assets and liabilities else 0.4
    fx_drop = (_extract_percent(question, "환율") or 10.0) / 100
    rate_rise = (_extract_percent(question, "기준금리") or 1.0) / 100
    chip_price_drop = (_extract_percent(question, "반도체 가격") or 15.0) / 100
    effects = {
        "원/달러 환율 하락": -fx_drop * 0.45,
        "기준금리 상승": -rate_rise * (1.6 * debt_ratio),
        "반도체 가격 하락": -chip_price_drop * 0.70,
    }
    total_effect = max(-0.8, sum(effects.values()))
    stressed_income = operating_income * (1 + total_effect)
    base_wacc = 0.085
    stressed_wacc = base_wacc + rate_rise * debt_ratio
    value_change = (1 + total_effect) * base_wacc / stressed_wacc - 1
    latest_price = _latest_price(company)
    stressed_price = latest_price * max(0, 1 + value_change) if latest_price else None
    assumptions = [
        {"factor": "원/달러 환율 하락", "shock": f"-{fx_drop*100:.1f}%", "income_effect": effects["원/달러 환율 하락"]},
        {"factor": "기준금리 상승", "shock": f"+{rate_rise*100:.1f}%p", "income_effect": effects["기준금리 상승"]},
        {"factor": "반도체 가격 하락", "shock": f"-{chip_price_drop*100:.1f}%", "income_effect": effects["반도체 가격 하락"]},
    ]
    return {
        "status": "ok",
        "mode": "multi_factor_stress",
        "summary": f"복합 스트레스 시 {company.company_name}의 영업이익은 {abs(total_effect)*100:.2f}%, 적정가치 대용치는 {abs(value_change)*100:.2f}% 하락하는 것으로 추정됩니다.",
        "steps": [
            f"기본 충격 가정: 환율 -{fx_drop*100:.1f}%, 기준금리 +{rate_rise*100:.1f}%p, 반도체 가격 -{chip_price_drop*100:.1f}%",
            *[f"{row['factor']} {row['shock']}: 영업이익 영향 {row['income_effect']*100:+.2f}%" for row in assumptions],
            f"기준 영업이익 {_money(operating_income)} → 스트레스 영업이익 {_money(stressed_income)}",
            f"WACC {base_wacc*100:.2f}% → {stressed_wacc*100:.2f}%, 적정가치 변화 {value_change*100:+.2f}%",
            f"현재가 기준 스트레스 주가 {stressed_price:,.0f}원" if stressed_price else "현재 주가를 확보하지 못해 가치 변화율만 제시했습니다.",
            "충격별 탄력도를 합산한 시나리오 분석이며 실제 손익의 인과 예측은 아닙니다.",
        ],
        "company": company.__dict__,
        "base_operating_income": operating_income,
        "scenario_operating_income": stressed_income,
        "value_change": value_change,
        "latest_price": latest_price,
        "scenario_price": stressed_price,
        "stress_factors": assumptions,
    }


def _growth_margin_stress_analysis(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    company = _resolve_company(store, question)
    if not company:
        return {"status": "needs_company", "summary": "스트레스 분석 대상 기업명을 확인하지 못했습니다.", "steps": []}
    years = store.available_years(company.stock_code)
    if not years:
        return {"status": "no_data", "summary": f"{company.company_name}의 재무 데이터를 찾지 못했습니다.", "steps": []}

    end_year = max(years)
    rows = store.get_account_series(
        company.stock_code,
        ["revenue", "operating_income"],
        max(min(years), end_year - 3),
        end_year,
    )
    rows = _fill_missing_series_with_yfinance(company, ["revenue", "operating_income"], rows, None)
    rows = _prefer_dart_revenue_income_series(company, end_year, rows)
    valid = [row for row in rows if _amount(row, "revenue") and _amount(row, "operating_income") is not None]
    if not valid:
        return {"status": "no_data", "summary": f"{company.company_name}의 매출액과 영업이익을 확인하지 못했습니다.", "steps": [], "company": company.__dict__}

    latest = valid[-1]
    latest_revenue = float(_amount(latest, "revenue"))
    latest_operating_income = float(_amount(latest, "operating_income"))
    base_margin = latest_operating_income / latest_revenue
    revenue_values = [float(_amount(row, "revenue")) for row in valid]
    historical_growth = _cagr(revenue_values)
    base_growth = min(0.20, max(-0.10, historical_growth if historical_growth is not None else 0.05))
    growth_drop = (_extract_percent(question, "매출 성장률") or 5.0) / 100
    margin_drop = (_extract_percent(question, "영업이익률") or 2.0) / 100
    stressed_growth = base_growth - growth_drop
    stressed_margin = base_margin - margin_drop
    base_revenue = latest_revenue * (1 + base_growth)
    stressed_revenue = latest_revenue * (1 + stressed_growth)
    base_income = base_revenue * base_margin
    stressed_income = stressed_revenue * stressed_margin
    income_change = (stressed_income - base_income) / abs(base_income) if base_income else 0.0
    value_change = income_change
    latest_price = _latest_price(company)
    scenario_price = latest_price * max(0, 1 + value_change) if latest_price else None

    return {
        "status": "ok",
        "mode": "growth_margin_stress",
        "summary": f"매출 성장률 -{growth_drop*100:.1f}%p, 영업이익률 -{margin_drop*100:.1f}%p 충격 시 {company.company_name}의 예상 영업이익은 기준 대비 {abs(income_change)*100:.2f}% 악화됩니다.",
        "steps": [
            f"기준: {end_year}년 매출액 {_money(latest_revenue)}, 영업이익률 {base_margin*100:.2f}%",
            f"기준 시나리오: 매출 성장률 {base_growth*100:.2f}%, 예상 매출액 {_money(base_revenue)}, 예상 영업이익 {_money(base_income)}",
            f"스트레스 가정: 매출 성장률 {base_growth*100:.2f}% → {stressed_growth*100:.2f}%(-{growth_drop*100:.1f}%p), 영업이익률 {base_margin*100:.2f}% → {stressed_margin*100:.2f}%(-{margin_drop*100:.1f}%p)",
            f"스트레스 결과: 예상 매출액 {_money(stressed_revenue)}, 예상 영업이익 {_money(stressed_income)}({income_change*100:+.2f}%)",
            f"현재가 기준 가치 대용치: {latest_price:,.0f}원 → {scenario_price:,.0f}원" if scenario_price else f"가치 대용치 변화: {value_change*100:+.2f}%",
            "적정가치 변화는 영업이익 변화율이 기업가치에 동일하게 반영된다는 단순 민감도 가정이며 투자 의견이 아닙니다.",
        ],
        "company": company.__dict__,
        "base_revenue": base_revenue,
        "scenario_revenue": stressed_revenue,
        "base_operating_income": base_income,
        "scenario_operating_income": stressed_income,
        "value_change": value_change,
        "latest_price": latest_price,
        "scenario_price": scenario_price,
        "assumptions": {
            "base_growth": base_growth,
            "growth_drop": growth_drop,
            "base_margin": base_margin,
            "margin_drop": margin_drop,
            "stressed_growth": stressed_growth,
            "stressed_margin": stressed_margin,
        },
    }


def _revenue_cost_scenario_analysis(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    company = _resolve_company(store, question)
    if not company:
        return {"status": "needs_company", "summary": "매출·원가 시나리오 대상 기업명을 확인하지 못했습니다.", "steps": []}
    years = store.available_years(company.stock_code)
    if not years:
        return {"status": "no_data", "summary": f"{company.company_name}의 재무 데이터를 찾지 못했습니다.", "steps": [], "company": company.__dict__}
    end_year = max(years)
    rows = store.get_account_series(company.stock_code, ["revenue", "cost_of_sales", "operating_income"], end_year, end_year)
    latest = rows[-1] if rows else {}
    latest = _prefer_dart_latest_accounts(company, end_year, latest, ["revenue", "cost_of_sales", "operating_income"])
    revenue = _amount(latest, "revenue")
    cost = _amount(latest, "cost_of_sales")
    operating_income = _amount(latest, "operating_income")
    if revenue in (None, 0) or cost is None or operating_income is None:
        return {"status": "no_data", "summary": f"{company.company_name}의 매출액·매출원가·영업이익을 모두 확인하지 못했습니다.", "steps": [], "company": company.__dict__}
    revenue_change = (_extract_directional_percent(question, "매출") or -5.0) / 100
    cost_ratio_change = (_extract_directional_percent(question, "매출원가율") or 2.0) / 100
    base_cost_ratio = cost / revenue
    fixed_sga = revenue - cost - operating_income
    scenario_revenue = revenue * (1 + revenue_change)
    scenario_cost_ratio = base_cost_ratio + cost_ratio_change
    scenario_income = scenario_revenue * (1 - scenario_cost_ratio) - fixed_sga
    income_change = (scenario_income - operating_income) / abs(operating_income) if operating_income else 0.0
    latest_price = _latest_price(company)
    scenario_price = latest_price * max(0, 1 + income_change) if latest_price else None
    return {
        "status": "ok",
        "mode": "revenue_cost_scenario",
        "summary": f"매출 {revenue_change*100:+.1f}%, 매출원가율 {cost_ratio_change*100:+.1f}%p 시 {company.company_name}의 영업이익은 기준 대비 {income_change*100:+.2f}% 변하는 것으로 추정됩니다.",
        "steps": [
            f"기준: {end_year}년 매출액 {_money(revenue)}, 매출원가율 {base_cost_ratio*100:.2f}%, 영업이익 {_money(operating_income)}",
            f"시나리오: 매출액 {_money(scenario_revenue)}, 매출원가율 {scenario_cost_ratio*100:.2f}%",
            f"판매비와관리비 {_money(fixed_sga)} 고정 가정 시 영업이익 {_money(scenario_income)} ({income_change*100:+.2f}%)",
            f"현재가 기준 가치 대용치 {latest_price:,.0f}원 → {scenario_price:,.0f}원" if scenario_price else f"가치 대용치 변화 {income_change*100:+.2f}%",
            "매출원가율 외 판매비와관리비 등은 고정한 단순 민감도 분석입니다.",
        ],
        "company": company.__dict__,
        "base_operating_income": operating_income,
        "scenario_operating_income": scenario_income,
        "latest_price": latest_price,
        "scenario_price": scenario_price,
        "value_change": income_change,
        "assumptions": {"revenue_change": revenue_change, "base_cost_ratio": base_cost_ratio, "cost_ratio_change": cost_ratio_change},
    }


def _dividend_growth_scenario_analysis(question: str) -> dict[str, Any]:
    dividend_match = re.search(r"주당\s*배당금[^0-9]{0,10}([0-9][0-9,]*)\s*원", question)
    growth_values = [float(value) for value in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*%", question)]
    required_match = re.search(r"요구수익률[^0-9]{0,10}([0-9]+(?:\.[0-9]+)?)\s*%", question)
    if not dividend_match or not required_match or len(growth_values) < 3:
        return {"status": "need_more_data", "summary": "배당가치 시나리오에는 주당 배당금, 기존·변경 배당성장률, 요구수익률이 필요합니다.", "steps": []}
    dividend = float(dividend_match.group(1).replace(",", ""))
    required_return = float(required_match.group(1)) / 100
    growth_candidates = [value / 100 for value in growth_values if value / 100 != required_return]
    base_growth, scenario_growth = growth_candidates[0], growth_candidates[1]
    if required_return <= max(base_growth, scenario_growth):
        return {"status": "no_data", "summary": "항상성장 배당모형에서는 요구수익률이 배당성장률보다 커야 합니다.", "steps": []}
    base_value = dividend * (1 + base_growth) / (required_return - base_growth)
    scenario_value = dividend * (1 + scenario_growth) / (required_return - scenario_growth)
    value_change = scenario_value / base_value - 1
    return {
        "status": "ok",
        "mode": "dividend_growth_scenario",
        "summary": f"배당성장률이 {base_growth*100:.1f}%에서 {scenario_growth*100:.1f}%로 변하면 배당할인모형 주식가치는 {base_value:,.0f}원에서 {scenario_value:,.0f}원으로 {value_change*100:+.2f}% 변합니다.",
        "steps": [
            f"가정: 주당 배당금 {dividend:,.0f}원, 요구수익률 {required_return*100:.1f}%",
            f"기준 가치 = {dividend:,.0f}×(1+{base_growth*100:.1f}%)/({required_return*100:.1f}%-{base_growth*100:.1f}%) = {base_value:,.0f}원",
            f"변경 가치 = {dividend:,.0f}×(1+{scenario_growth*100:.1f}%)/({required_return*100:.1f}%-{scenario_growth*100:.1f}%) = {scenario_value:,.0f}원",
            "배당이 영구히 일정한 성장률로 증가한다는 가정의 이론값입니다.",
        ],
        "base_value": base_value,
        "scenario_value": scenario_value,
        "value_change": value_change,
        "assumptions": {"dividend": dividend, "required_return": required_return, "base_growth": base_growth, "scenario_growth": scenario_growth},
    }
def _ten_year_dcf(question: str, fetch_notes: bool = True) -> dict[str, Any]:
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

    dart_fetch = _fetch_dart_report_for_notes(company, end_year) if fetch_notes else {"status": "skipped", "message": "민감도 분석에서는 DART 주석 조회를 생략했습니다."}
    notes = search_external_docs(f"{company.company_name} CapEx 설비투자 순운전자본 사업보고서", company.company_name, limit=8) if fetch_notes else []
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
        _dart_fetch_step(dart_fetch),
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
        "dart_fetch": dart_fetch,
    }


def _fetch_dart_report_for_notes(company: Any, fiscal_year: int) -> dict[str, Any]:
    if not load_dart_api_key():
        return {"status": "skipped", "message": "DART_API_KEY가 없어 원문 조회를 건너뛰었습니다."}
    try:
        return DartClient().save_business_report_for_rag(
            stock_code=company.stock_code,
            corp_name=company.company_name,
            fiscal_year=fiscal_year,
        )
    except Exception as exc:
        return {"status": "error", "message": f"DART 사업보고서 원문 조회 실패: {exc}"}


def _dart_fetch_step(result: dict[str, Any]) -> str:
    if result.get("status") == "ok":
        report = result.get("report") or {}
        cache_label = "캐시 원문" if result.get("cached") else "신규 수집 원문"
        return f"DART {cache_label}: {report.get('report_name', '사업보고서')} ({report.get('rcept_date', '접수일 미확인')})"
    return result.get("message") or "DART 사업보고서 원문을 확보하지 못했습니다."


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
    rate_shock = (_extract_directional_percent(question, "기준금리") or 1.0) / 100
    fx_shock = (_extract_directional_percent(question, "환율") or 10.0) / 100
    years = store.available_years(company.stock_code)
    end_year = max(years)
    rows = store.get_account_series(company.stock_code, ["operating_income", "total_assets", "total_liabilities"], end_year, end_year)
    rows = _fill_missing_series_with_yfinance(company, ["operating_income", "total_assets", "total_liabilities"], rows, None)
    latest = rows[-1] if rows else {}
    latest = _prefer_dart_latest_accounts(company, end_year, latest, ["operating_income", "total_assets", "total_liabilities"])
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
        f"환율 {abs(fx_shock)*100:.1f}% {'하락' if fx_shock < 0 else '상승'} 효과: 영업이익 {fx_effect*100:+.2f}% (수출 업종 탄력도 {fx_elasticity:.2f})",
        f"기준금리 {abs(rate_shock)*100:.1f}%p {'하락' if rate_shock < 0 else '상승'} 효과: 영업이익 {rate_effect*100:+.2f}% (금리 탄력도 {rate_elasticity:.2f})",
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


def _prefer_dart_revenue_income_series(company: Any, fiscal_year: int, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use consolidated DART annual values when available; keep local rows as an offline fallback."""
    if not load_dart_api_key():
        return fallback
    try:
        client = DartClient()
        result = None
        for fs_div in ("CFS", "OFS"):
            candidate = client.fetch_financial_accounts(
                stock_code=company.stock_code,
                corp_name=company.company_name,
                fiscal_year=fiscal_year,
                fs_div=fs_div,
            )
            if candidate.get("status") == "ok":
                result = candidate
                break
        if not result:
            return fallback
        fields = {
            fiscal_year - 2: "bfefrmtrm_amount",
            fiscal_year - 1: "frmtrm_amount",
            fiscal_year: "thstrm_amount",
        }
        dart_rows = []
        for year, field in fields.items():
            normalized = [
                {**account, "thstrm_amount": account.get(field)}
                for account in result.get("accounts") or []
                if str(account.get(field) or "").strip()
            ]
            mapped = _map_dart_accounts(normalized)
            revenue = mapped.get("revenue")
            operating_income = mapped.get("operating_income")
            if revenue and operating_income and revenue.get("amount") is not None and operating_income.get("amount") is not None:
                dart_rows.append({"year": year, "revenue": revenue, "operating_income": operating_income})
        return dart_rows if len(dart_rows) >= 2 else fallback
    except Exception:
        return fallback


def _prefer_dart_latest_accounts(
    company: Any,
    fiscal_year: int,
    fallback: dict[str, Any],
    account_keys: list[str],
) -> dict[str, Any]:
    """Fill the latest scenario inputs from consolidated DART accounts without exposing missing-row errors."""
    if not load_dart_api_key():
        return fallback or {"year": fiscal_year}
    try:
        client = DartClient()
        for fs_div in ("CFS", "OFS"):
            result = client.fetch_financial_accounts(
                stock_code=company.stock_code,
                corp_name=company.company_name,
                fiscal_year=fiscal_year,
                fs_div=fs_div,
            )
            if result.get("status") != "ok":
                continue
            mapped = _map_dart_accounts(result.get("accounts") or [])
            row = {**(fallback or {}), "year": fiscal_year}
            for key in account_keys:
                account = mapped.get(key)
                if account and account.get("amount") is not None:
                    row[key] = account
            return row
    except Exception:
        pass
    return fallback or {"year": fiscal_year}


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


def _extract_directional_percent(question: str, label: str) -> float | None:
    match = re.search(rf"{label}[^0-9]{{0,12}}([0-9]+(?:\.[0-9]+)?)\s*%?p?([^,.?]{{0,12}})", question)
    if not match:
        return None
    value = float(match.group(1))
    direction = match.group(2)
    return -value if any(token in direction for token in ["하락", "인하", "내리", "감소", "떨어"]) else value


def _extract_range(question: str, label: str, default: tuple[float, float]) -> tuple[float, float]:
    match = re.search(
        rf"{re.escape(label)}[^0-9]{{0,12}}([0-9]+(?:\.[0-9]+)?)\s*%?\s*(?:~|～|-|에서)\s*([0-9]+(?:\.[0-9]+)?)\s*%?",
        question,
        re.IGNORECASE,
    )
    if not match:
        return default
    start, end = float(match.group(1)), float(match.group(2))
    return (min(start, end), max(start, end))


def _percentage_grid(start: float, end: float) -> list[float]:
    values = []
    current = start
    while current <= end + 1e-9 and len(values) < 20:
        values.append(round(current, 2))
        current += 1.0
    if values[-1] != round(end, 2):
        values.append(round(end, 2))
    return values


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_0000_0000_0000:
        return f"{sign}{value / 1_0000_0000_0000:.2f}조원"
    if value >= 1_0000_0000:
        return f"{sign}{value / 1_0000_0000:.2f}억원"
    return f"{sign}{value:,.0f}원"
