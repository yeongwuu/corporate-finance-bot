from __future__ import annotations

from typing import Any


CHART_ACCOUNT_ORDER = [
    "revenue",
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
    if tool_name == "company_trend_tool":
        return _build_trend_chart(calculation)
    if tool_name == "company_analysis_tool":
        return _build_account_bar_chart(calculation)
    if tool_name == "forecast_tool":
        return _build_forecast_chart(calculation)
    return None


def _build_trend_chart(calculation: dict[str, Any]) -> dict[str, Any] | None:
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
