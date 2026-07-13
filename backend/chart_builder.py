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
    if calculation.get("mode") == "rf_stock_forecast":
        return _build_rf_stock_forecast_chart(calculation)
    if tool_name == "company_trend_tool":
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
    return {
        "type": "line",
        "title": f"{company.get('company_name', '기업')} 수익성 비율 추이",
        "subtitle": f"{period.get('start_year', '')}~{period.get('end_year', '')}년",
        "unit": "PERCENT",
        "datasets": datasets,
    }


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
        "title": f"{company.get('company_name', '기업')} 주요 재무계정",
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
    last = actual_points[-1]
    forecast_point = {
        "x": int(target_year),
        "y": float(forecast["base"]),
        "label": f"{target_year}년 전망",
        "display": _format_amount(float(forecast["base"])),
        "forecast": True,
    }
    company = calculation.get("company") or {}
    account_label = calculation.get("account_label") or "재무지표"
    return {
        "type": "line",
        "title": f"{company.get('company_name', '기업')} {account_label} 전망",
        "subtitle": f"{actual_points[0]['x']}~{target_year}년, 기준 전망 {_format_amount(float(forecast['base']))}",
        "unit": "KRW",
        "datasets": [
            {"key": "actual", "label": "실적", "points": actual_points},
            {"key": "forecast", "label": "기준 전망", "points": [last, forecast_point], "forecast": True},
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
        "title": f"{company.get('company_name', '기업')} 주가 및 RF 예측 전망",
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
