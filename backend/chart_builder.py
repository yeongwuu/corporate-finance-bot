from __future__ import annotations

from typing import Any


CHART_ACCOUNT_ORDER = [
    "revenue",
    "cost_of_sales",
    "gross_profit",
    "selling_admin_expenses",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "total_assets",
    "total_liabilities",
    "total_equity",
]


def build_chart_spec(tool_name: str, calculation: dict[str, Any]) -> dict[str, Any] | None:
    if calculation.get("status") != "ok":
        return None
    if calculation.get("mode") in {"advanced_dcf", "dcf_sensitivity", "monte_carlo_comparison", "macro_scenario", "multi_factor_stress", "cost_of_sales_ear"}:
        return _build_advanced_analysis_chart(calculation)
    if calculation.get("mode") == "stock_price_comparison":
        return _build_stock_price_comparison_chart(calculation)
    if calculation.get("mode") == "portfolio_optimization":
        return _build_portfolio_optimization_chart(calculation)
    if calculation.get("mode") == "rf_stock_forecast":
        return _build_rf_stock_forecast_chart(calculation)
    if tool_name == "company_trend_tool":
        comparison_chart = _build_company_financial_comparison_chart(calculation)
        if comparison_chart:
            return comparison_chart
        industry_growth_chart = _build_industry_growth_comparison_chart(calculation)
        if industry_growth_chart:
            return industry_growth_chart
        return _build_trend_chart(calculation)
    if tool_name == "company_analysis_tool":
        return _build_account_bar_chart(calculation)
    if tool_name == "forecast_tool":
        return _build_forecast_chart(calculation)
    if tool_name == "stock_price_tool":
        return _build_stock_price_chart(calculation)
    if tool_name == "valuation_tool":
        return _build_market_ratio_chart(calculation)
    return None


def _build_company_financial_comparison_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    comparison = calculation.get("comparison") or []
    if len(comparison) < 2 or calculation.get("mode") in {"industry_growth_comparison", "representative_sector_comparison"}:
        return None

    account_order = ["revenue", "operating_income", "net_income"]
    metrics = []
    for account_key in account_order:
        values = []
        for item in comparison:
            company_name = (item.get("company") or {}).get("company_name", "기업")
            for row in item.get("series") or []:
                account = row.get(account_key)
                if not isinstance(account, dict) or account.get("amount") is None:
                    continue
                year = int(row["year"])
                values.append(
                    {
                        "year": year,
                        "label": f"{str(year)[-2:]}년\n{company_name}",
                        "value": float(account["amount"]),
                        "display": _format_amount(float(account["amount"])),
                        "company": company_name,
                    }
                )
        if values:
            labels = {"revenue": "매출액", "operating_income": "영업이익", "net_income": "당기순이익"}
            metrics.append({"key": account_key, "label": labels.get(account_key, account_key), "values": values})

    if not metrics:
        return None
    company_names = [(item.get("company") or {}).get("company_name", "기업") for item in comparison]
    periods = [item.get("period") or {} for item in comparison]
    start_years = [int(period["start_year"]) for period in periods if period.get("start_year")]
    end_years = [int(period["end_year"]) for period in periods if period.get("end_year")]
    period_label = f"{min(start_years)}~{max(end_years)}년" if start_years and end_years else "최근 실적"
    return {
        "type": "compact_metric_bar",
        "title": " · ".join(company_names) + " 재무지표 비교",
        "subtitle": period_label,
        "unit": "KRW",
        "metrics": metrics,
    }


def _build_trend_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    ratio_chart = _build_ratio_trend_chart(calculation)
    if ratio_chart:
        return ratio_chart

    series_rows = calculation.get("series") or []
    account_keys = calculation.get("accounts") or []
    if len(series_rows) < 2 or not account_keys:
        return None

    datasets = []
    for account_key in account_keys[:4]:
        points = []
        label = None
        for row in series_rows:
            account = row.get(account_key)
            if not account:
                continue
            label = account.get("label") or _label_from_metrics(calculation, account_key) or account_key
            points.append(
                {
                    "x": int(row["year"]),
                    "y": float(account["amount"]),
                    "label": f"{row['year']}년",
                    "display": _format_amount(float(account["amount"])),
                }
            )
        if len(points) >= 2:
            datasets.append({"key": account_key, "label": label, "points": points})

    if not datasets:
        return None

    company = calculation.get("company") or {}
    period = calculation.get("period") or {}
    if _should_use_compact_bar(datasets):
        return {
            "type": "compact_metric_bar",
            "title": f"{company.get('company_name', '기업')} 재무지표 비교",
            "subtitle": f"{period.get('start_year', '')}~{period.get('end_year', '')}년",
            "unit": "KRW",
            "metrics": _datasets_to_bar_metrics(datasets),
        }
    return {
        "type": "line",
        "title": f"{company.get('company_name', '기업')} 재무 추이",
        "subtitle": f"{period.get('start_year', '')}~{period.get('end_year', '')}년",
        "unit": "KRW",
        "datasets": datasets,
    }


def _build_ratio_trend_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    ratio_rows = calculation.get("ratio_series") or []
    if len(ratio_rows) < 2:
        return None

    datasets = []
    ratio_keys = []
    for row in ratio_rows:
        for key, value in row.items():
            if key != "year" and isinstance(value, dict) and key not in ratio_keys:
                ratio_keys.append(key)
    for ratio_key in ratio_keys:
        points = []
        label = None
        for row in ratio_rows:
            item = row.get(ratio_key)
            if not item:
                continue
            label = item.get("label") or ratio_key
            value = float(item["value"]) * 100
            points.append(
                {
                    "x": int(row["year"]),
                    "y": value,
                    "label": f"{row['year']}년",
                    "display": f"{value:.2f}%",
                }
            )
        if len(points) >= 2:
            datasets.append({"key": ratio_key, "label": label, "points": points})

    if not datasets:
        return None

    company = calculation.get("company") or {}
    period = calculation.get("period") or {}
    if _should_use_compact_bar(datasets):
        return {
            "type": "compact_metric_bar",
            "title": f"{company.get('company_name', '기업')} 수익성 비율 비교",
            "subtitle": f"{period.get('start_year', '')}~{period.get('end_year', '')}년",
            "unit": "PERCENT",
            "metrics": _datasets_to_bar_metrics(datasets),
        }
    return {
        "type": "line",
        "title": f"{company.get('company_name', '기업')} 수익성 비율 추이",
        "subtitle": f"{period.get('start_year', '')}~{period.get('end_year', '')}년",
        "unit": "PERCENT",
        "datasets": datasets,
    }


def _should_use_compact_bar(datasets: list[dict[str, Any]]) -> bool:
    if not datasets or len(datasets) > 3:
        return False
    point_counts = [len(dataset.get("points") or []) for dataset in datasets]
    return max(point_counts, default=0) <= 3 and sum(point_counts) <= 6


def _datasets_to_bar_metrics(datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "key": dataset.get("key"),
            "label": dataset.get("label"),
            "values": [
                {
                    "year": int(point["x"]),
                    "value": float(point["y"]),
                    "display": point.get("display"),
                }
                for point in dataset.get("points") or []
            ],
        }
        for dataset in datasets
    ]


def _build_account_bar_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    accounts = calculation.get("accounts") or {}
    bars = []
    for account_key in CHART_ACCOUNT_ORDER:
        account = accounts.get(account_key)
        if not account:
            continue
        bars.append(
            {
                "key": account_key,
                "label": account.get("label") or account_key,
                "value": float(account["amount"]),
                "display": _format_amount(float(account["amount"])),
            }
        )
    if not bars:
        return None

    company = calculation.get("company") or {}
    year = calculation.get("year")
    return {
        "type": "bar",
        "title": f"{company.get('company_name', '기업')} 주요 재무지표",
        "subtitle": f"{year}년 당기 기준" if year else "",
        "unit": "KRW",
        "bars": bars,
    }


def _build_industry_growth_comparison_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    if calculation.get("mode") != "industry_growth_comparison":
        return None
    comparison = calculation.get("comparison") or []
    bars = []
    for item in comparison[:10]:
        company = item.get("company") or {}
        metric = (item.get("metrics") or [{}])[0]
        cagr = metric.get("cagr")
        if cagr is None:
            continue
        name = company.get("company_name") or company.get("stock_code") or "-"
        label = f"{name}*" if item.get("is_base") else name
        bars.append(
            {
                "key": company.get("stock_code") or name,
                "label": label,
                "value": float(cagr) * 100,
                "display": f"{float(cagr) * 100:.2f}%",
            }
        )
    if not bars:
        return None

    base = calculation.get("company") or {}
    industry = calculation.get("industry") or "동종 업종"
    subtitle = (
        f"{base.get('company_name')} 포함, CAGR 기준"
        if base.get("company_name")
        else f"대표 기업 {len(bars)}개, CAGR 기준"
    )
    return {
        "type": "bar",
        "title": f"{industry} 매출상승률 비교",
        "subtitle": subtitle,
        "unit": "PERCENT",
        "bars": bars,
    }


def _build_market_ratio_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    if calculation.get("mode") != "market_ratio_trend":
        return None
    rows = calculation.get("market_ratio_series") or []
    ratio_keys = calculation.get("ratio_keys") or []
    if len(rows) < 2 or not ratio_keys:
        return None

    datasets = []
    for ratio_key in ratio_keys:
        points = []
        label = None
        for row in rows:
            ratio = (row.get("ratios") or {}).get(ratio_key)
            if not ratio:
                continue
            label = ratio.get("label") or ratio_key.upper()
            points.append(
                {
                    "x": int(row["year"]),
                    "y": float(ratio["value"]),
                    "label": f"{row['year']}년",
                    "display": f"{ratio['display']}배",
                }
            )
        if len(points) >= 2:
            datasets.append({"key": ratio_key, "label": label, "points": points})

    if not datasets:
        return None

    company = calculation.get("company") or {}
    period = calculation.get("period") or {}
    return {
        "type": "line",
        "title": f"{company.get('company_name', '기업')} 밸류에이션 배수 추이",
        "subtitle": f"{period.get('start_year', '')}~{period.get('end_year', '')}년",
        "unit": "MULTIPLE",
        "datasets": datasets,
    }


def _build_forecast_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    series_rows = calculation.get("series") or []
    forecast = calculation.get("forecast") or {}
    target_year = calculation.get("target_year")
    if len(series_rows) < 2 or not forecast or not target_year:
        return None

    actual_points = [
        {
            "x": int(row["year"]),
            "y": float(row["amount"]),
            "label": f"{row['year']}년",
            "display": _format_amount(float(row["amount"])),
        }
        for row in series_rows
    ]
    last_actual = actual_points[-1]

    def scenario_points(value: float, scenario: str) -> list[dict[str, Any]]:
        return [
            last_actual,
            {
                "x": int(target_year),
                "y": float(value),
                "label": f"{target_year}년",
                "display": _format_amount(float(value)),
                "forecast": True,
                "scenario": scenario,
            },
        ]

    company = calculation.get("company") or {}
    account_label = calculation.get("account_label") or "재무지표"
    return {
        "type": "line",
        "title": f"{company.get('company_name', '기업')} {account_label} 전망",
        "subtitle": f"{actual_points[0]['x']}~{target_year}년 · {actual_points[-1]['x']}년 실적에서 세 가지 연간 전망으로 분기",
        "unit": "KRW",
        "preserve_combined_scale": True,
        "datasets": [
            {"key": "actual", "label": "실적", "points": actual_points, "color": "#FF530A"},
            {
                "key": "low_forecast",
                "label": "보수 전망",
                "points": scenario_points(float(forecast["low"]), "low"),
                "forecast": True,
                "color": "#A63A00",
            },
            {
                "key": "base_forecast",
                "label": "기준 전망",
                "points": scenario_points(float(forecast["base"]), "base"),
                "forecast": True,
                "color": "#E59A2F",
            },
            {
                "key": "high_forecast",
                "label": "낙관 전망",
                "points": scenario_points(float(forecast["high"]), "high"),
                "forecast": True,
                "color": "#D95C2B",
            },
        ],
        "range": {
            "low": _format_amount(float(forecast["low"])),
            "base": _format_amount(float(forecast["base"])),
            "high": _format_amount(float(forecast["high"])),
        },
    }


def _build_stock_price_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    prices = calculation.get("prices") or []
    if len(prices) < 2:
        return None

    company = calculation.get("company") or {}
    period = calculation.get("period") or {}
    points = [
        {
            "x": int(index),
            "y": float(point["close"]),
            "label": point["date"],
            "display": point["display"],
        }
        for index, point in enumerate(prices)
    ]
    return {
        "type": "line",
        "title": f"{company.get('company_name', '기업')} 주가 추이",
        "subtitle": f"{period.get('label', '')}, 종가 기준",
        "unit": "KRW_PRICE",
        "datasets": [
            {
                "key": "close",
                "label": "종가",
                "points": points,
            }
        ],
    }
def _label_from_metrics(calculation: dict[str, Any], account_key: str) -> str | None:
    for metric in calculation.get("metrics") or []:
        if metric.get("account") == account_key:
            return metric.get("label")
    return None


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


def _build_rf_stock_forecast_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    prices_list = calculation.get("prices_list") or []
    if not prices_list:
        return None

    points = []
    for idx, item in enumerate(prices_list):
        points.append({
            "x": idx,
            "y": item["close"],
            "label": item["date"],
            "display": f"{item['close']:,.0f}원",
            "forecast": item["forecast"]
        })

    company = calculation.get("company") or {}
    forecast_label = calculation.get("forecast_label") or "다음 영업일"
    return {
        "type": "line",
        "title": f"{company.get('company_name', '기업')} 주가 및 RF·LSTM 예측 전망",
        "subtitle": f"최근 15영업일 + {forecast_label} 예측",
        "unit": "KRW_PRICE",
        "datasets": [
            {
                "key": "close",
                "label": "예상 종가" if points[-1]["forecast"] else "종가",
                "points": points
            }
        ]
    }


def _build_portfolio_optimization_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    weights = calculation.get("weights") or {}
    min_weights = calculation.get("min_variance_weights") or {}
    bars = []
    for name, weight in weights.items():
        bars.append({"key": f"sharpe-{name}", "label": f"최대 샤프 · {name}", "value": float(weight * 100), "display": f"{weight * 100:.2f}%"})
    for name, weight in min_weights.items():
        bars.append({"key": f"minvar-{name}", "label": f"최소분산 · {name}", "value": float(weight * 100), "display": f"{weight * 100:.2f}%"})
    if not bars:
        return None
    return {
        "type": "bar",
        "title": "최적 포트폴리오 자산 배분 비교",
        "subtitle": f"실제 최근 {calculation.get('analysis_years', 5)}년 일별 수익률 기준",
        "unit": "PERCENT",
        "bars": bars,
        "table": {
            "caption": "포트폴리오별 투자 비중",
            "headers": ["기업", "최대 샤프", "최소분산"],
            "rows": [[name, f"{weight*100:.2f}%", f"{min_weights.get(name, 0)*100:.2f}%"] for name, weight in weights.items()],
            "layout": "balanced",
        },
    }


def _build_stock_price_comparison_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    comparison = calculation.get("comparison") or []
    if not comparison:
        return None
        
    datasets = []
    for item in comparison:
        comp_name = item["company"]["company_name"]
        prices = item["prices"] or []
        points = [
            {
                "x": int(index),
                "y": float(point["close"]),
                "label": point["date"],
                "display": point["display"],
            }
            for index, point in enumerate(prices)
        ]
        if points:
            datasets.append({
                "key": item["company"]["stock_code"],
                "label": comp_name,
                "points": points
            })
            
    if not datasets:
        return None
        
    period = calculation.get("period") or {}
    return {
        "type": "line",
        "title": "주가 비교 추이",
        "subtitle": f"{period.get('label', '')}, 종가 기준",
        "unit": "KRW_PRICE",
        "datasets": datasets
    }


def _build_advanced_analysis_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
    mode = calculation.get("mode")
    if mode == "cost_of_sales_ear":
        company = calculation.get("company") or {}
        base = float(calculation.get("base_defense_probability") or 0) * 100
        scenario = float(calculation.get("scenario_defense_probability") or 0) * 100
        return {
            "type": "bar",
            "title": f"{company.get('company_name', '기업')} EPS 방어 확률",
            "subtitle": f"매출원가율 +{float(calculation.get('cost_shock') or 0) * 100:.1f}%p 시나리오",
            "unit": "PERCENT",
            "bars": [
                {"key": "base", "label": "기준", "value": base, "display": f"{base:.1f}%", "color": "#FEA278"},
                {"key": "scenario", "label": "원가 상승", "value": scenario, "display": f"{scenario:.1f}%", "color": "#FF530A"},
            ],
        }
    if mode == "advanced_dcf":
        company = calculation.get("company") or {}
        projections = calculation.get("projections") or []
        points = [
            {"x": index, "y": float(row["fcf"]), "label": f"{row['year']}년", "display": _format_amount(float(row["fcf"]))}
            for index, row in enumerate(projections)
        ]
        table = {
            "caption": "연도별 FCF 추정치",
            "headers": ["연도", "영업이익(EBIT)", "FCF", "현재가치(PV)"],
            "rows": [
                [
                    f"{row['year']}년",
                    _format_amount(float(row["ebit"])),
                    _format_amount(float(row["fcf"])),
                    _format_amount(float(row["pv"])),
                ]
                for row in projections
            ],
        }
        return {"type": "line", "title": f"{company.get('company_name', '기업')} 10년 FCF 전망", "subtitle": "가정 기반 기준 시나리오", "unit": "KRW", "datasets": [{"key": "fcf", "label": "FCF", "points": points}], "table": table} if points else None
    if mode == "dcf_sensitivity":
        company = calculation.get("company") or {}
        growth_values = calculation.get("growth_values") or []
        rows = calculation.get("sensitivity") or []
        table_rows = [
            [f"{row['wacc']:.1f}%", *[f"{price:,.0f}원" if price is not None else "-" for price in row["prices"]]]
            for row in rows
        ]
        return {
            "type": "table_only",
            "title": f"{company.get('company_name', '기업')} DCF 민감도",
            "subtitle": "WACC × 영구성장률별 주당 적정가치",
            "table": {"caption": "적정 주가 민감도 표", "headers": ["WACC / 영구성장률", *[f"{value:.1f}%" for value in growth_values]], "rows": table_rows},
        }
    if mode == "monte_carlo_comparison":
        bars = []
        for item in calculation.get("simulations") or []:
            name = (item.get("company") or {}).get("company_name", "기업")
            bars.append({"key": name, "label": f"{name} 중앙값", "value": float(item["median"]) * 100, "display": f"{float(item['median']) * 100:.2f}%"})
        return {"type": "bar", "title": "1년 기대수익률 분포 중앙값", "subtitle": f"{calculation.get('simulation_count', 0):,}회 시뮬레이션", "unit": "PERCENT", "bars": bars} if bars else None
    if mode == "macro_scenario":
        company = calculation.get("company") or {}
        base = float(calculation.get("base_operating_income") or 0)
        scenario = float(calculation.get("scenario_operating_income") or 0)
        return {"type": "bar", "title": f"{company.get('company_name', '기업')} 영업이익 시나리오", "subtitle": "기준 대비 금리·환율 복합 충격", "unit": "KRW", "bars": [{"key": "base", "label": "기준", "value": base, "display": _format_amount(base), "color": "#FEA278"}, {"key": "scenario", "label": "충격 후", "value": scenario, "display": _format_amount(scenario), "color": "#FF530A"}]}
    if mode == "multi_factor_stress":
        company = calculation.get("company") or {}
        base = float(calculation.get("base_operating_income") or 0)
        scenario = float(calculation.get("scenario_operating_income") or 0)
        factors = calculation.get("stress_factors") or []
        return {
            "type": "bar",
            "title": f"{company.get('company_name', '기업')} 복합 스트레스 테스트",
            "subtitle": "환율·금리·반도체 가격 동시 충격",
            "unit": "KRW",
            "bars": [{"key": "base", "label": "기준 영업이익", "value": base, "display": _format_amount(base), "color": "#FEA278"}, {"key": "stress", "label": "스트레스 영업이익", "value": scenario, "display": _format_amount(scenario), "color": "#FF530A"}],
            "table": {"caption": "충격별 영업이익 영향", "headers": ["위험 요인", "충격 가정", "영업이익 영향"], "rows": [[row["factor"], row["shock"], f"{row['income_effect']*100:+.2f}%"] for row in factors]},
        }
    return None
