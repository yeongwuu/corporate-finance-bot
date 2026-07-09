import re
from decimal import Decimal, ROUND_HALF_UP


def calculate_cost_of_capital(question: str) -> dict:
    debt_weight = find_percent(question, ["부채비중", "타인자본비중"])
    equity_weight = find_percent(question, ["자기자본비중"])
    cost_of_debt = find_percent(question, ["세전타인자본비용", "타인자본비용"])
    cost_of_equity = find_percent(question, ["자기자본비용"])
    tax_rate = find_percent(question, ["법인세율", "세율"])

    if None not in [debt_weight, equity_weight, cost_of_debt, cost_of_equity, tax_rate]:
        wacc = (
            debt_weight / Decimal("100") * cost_of_debt / Decimal("100") * (Decimal("1") - tax_rate / Decimal("100"))
            + equity_weight / Decimal("100") * cost_of_equity / Decimal("100")
        )
        wacc_percent = wacc * Decimal("100")
        return {
            "status": "ok",
            "summary": f"WACC는 {format_percent(wacc_percent)}입니다.",
            "steps": [
                "WACC = 부채비중 * 세전타인자본비용 * (1 - 세율) + 자기자본비중 * 자기자본비용",
                f"WACC = {debt_weight}% * {cost_of_debt}% * (1 - {tax_rate}%) + {equity_weight}% * {cost_of_equity}%",
                f"WACC = {format_percent(wacc_percent)}",
            ],
        }

    return {
        "status": "need_more_data",
        "summary": "WACC 계산에는 부채비중, 자기자본비중, 타인자본비용, 자기자본비용, 법인세율이 필요합니다.",
        "steps": [],
    }


def find_percent(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        match = re.search(rf"{label}[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*%", text)
        if match:
            return Decimal(match.group(1))
    return None


def format_percent(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"
