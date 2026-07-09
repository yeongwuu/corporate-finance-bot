import re
from decimal import Decimal, ROUND_HALF_UP


def analyze_financial_ratios(question: str) -> dict:
    current_assets = find_money(question, ["유동자산"])
    current_liabilities = find_money(question, ["유동부채"])
    debt = find_money(question, ["부채"])
    equity = find_money(question, ["자본", "자기자본"])
    net_income = find_money(question, ["당기순이익", "순이익"])

    steps = []
    ratios = []

    if current_assets is not None and current_liabilities:
        current_ratio = current_assets / current_liabilities * Decimal("100")
        ratios.append(f"유동비율 {format_percent(current_ratio)}")
        steps.append(f"유동비율 = 유동자산 / 유동부채 * 100 = {format_percent(current_ratio)}")

    if debt is not None and equity:
        debt_ratio = debt / equity * Decimal("100")
        ratios.append(f"부채비율 {format_percent(debt_ratio)}")
        steps.append(f"부채비율 = 부채 / 자본 * 100 = {format_percent(debt_ratio)}")

    if net_income is not None and equity:
        roe = net_income / equity * Decimal("100")
        ratios.append(f"ROE {format_percent(roe)}")
        steps.append(f"ROE = 당기순이익 / 자기자본 * 100 = {format_percent(roe)}")

    if ratios:
        return {"status": "ok", "summary": ", ".join(ratios) + "입니다.", "steps": steps}

    return {
        "status": "need_more_data",
        "summary": "재무비율 계산에는 유동자산, 유동부채, 부채, 자본, 순이익 등 필요한 항목이 필요합니다.",
        "steps": [],
    }


def find_money(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        match = re.search(rf"{label}[^0-9￦₩]*[￦₩]?\s*([0-9,]+)", text)
        if match:
            return Decimal(match.group(1).replace(",", ""))
    return None


def format_percent(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"
