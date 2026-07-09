import re
from decimal import Decimal, ROUND_HALF_UP


def analyze_capital_budgeting(question: str) -> dict:
    cash_flows = find_cash_flows(question)
    discount_rate = find_percent(question, ["할인율", "자본비용", "요구수익률"])

    if cash_flows and discount_rate is not None:
        rate = discount_rate / Decimal("100")
        npv = sum(cf / ((Decimal("1") + rate) ** i) for i, cf in enumerate(cash_flows))
        return {
            "status": "ok",
            "summary": f"투자안의 NPV는 {format_money(npv)}입니다.",
            "steps": [
                f"할인율 = {discount_rate}%",
                f"현금흐름 = {', '.join(format_money(cf) for cf in cash_flows)}",
                f"NPV = 각 기간 현금흐름의 현재가치 합계 = {format_money(npv)}",
            ],
        }

    return {
        "status": "need_more_data",
        "summary": "NPV 계산에는 기간별 현금흐름과 할인율이 필요합니다.",
        "steps": [],
    }


def find_cash_flows(text: str) -> list[Decimal]:
    match = re.search(r"현금흐름[^0-9\-￦₩]*([0-9,\-￦₩\s]+)", text)
    if not match:
        return []
    values = re.findall(r"-?[￦₩]?\s*([0-9,]+)", match.group(1))
    return [Decimal(value.replace(",", "")) for value in values]


def find_percent(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        match = re.search(rf"{label}[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*%", text)
        if match:
            return Decimal(match.group(1))
    return None


def format_money(value: Decimal) -> str:
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"￦{rounded:,.0f}"
