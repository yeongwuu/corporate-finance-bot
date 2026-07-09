import re
from decimal import Decimal, ROUND_HALF_UP


def analyze_valuation(question: str) -> dict:
    if is_constant_growth_question(question):
        return calculate_constant_growth_stock_value(question)

    return {
        "status": "no_calculation",
        "summary": "주식가치는 배당할인모형에 따라 미래 배당금을 주주의 요구수익률로 할인해 계산합니다.",
        "steps": [
            "배당할인모형: P0 = Σ Dt / (1 + k)^t",
            "항상성장모형: P0 = EPS1 * (1 - b) / (k - g)",
            "성장률: g = 유보율 * ROE",
            "NPVGO = 성장모형 주가 - 무성장모형 주가",
        ],
    }


def calculate_constant_growth_stock_value(question: str) -> dict:
    eps1 = find_money(question, ["eps", "주당 이익", "주당순이익", "주당 순이익"])
    retention = find_percent(question, ["유보율", "재투자"])
    roe = find_percent(question, ["roe", "자기자본에 대한 투자수익률", "투자수익률", "재투자수익률"])
    required_return = find_percent(question, ["적정 할인율", "할인율", "주주의 요구수익률", "요구수익률"])

    if None in [eps1, retention, roe, required_return]:
        return {
            "status": "need_more_data",
            "summary": "항상성장모형 계산에는 EPS1, 유보율, ROE, 주주의 요구수익률이 필요합니다.",
            "steps": [],
        }

    b = retention / Decimal("100")
    r = roe / Decimal("100")
    k = required_return / Decimal("100")
    growth = b * r

    if k <= growth:
        return {
            "status": "need_more_data",
            "summary": "항상성장모형은 주주의 요구수익률이 성장률보다 커야 계산할 수 있습니다.",
            "steps": [f"k = {format_percent(k * Decimal('100'))}", f"g = {format_percent(growth * Decimal('100'))}"],
        }

    dividend1 = eps1 * (Decimal("1") - b)
    growth_value = dividend1 / (k - growth)
    no_growth_value = eps1 / k
    npvgo = growth_value - no_growth_value
    per = growth_value / eps1
    pbr = per * r

    return {
        "status": "ok",
        "summary": (
            f"주식가치는 {format_money(growth_value)}, NPVGO는 {format_money(npvgo)}, "
            f"PER은 {format_number(per)}, PBR은 {format_number(pbr)}입니다."
        ),
        "steps": [
            f"성장률 g = 유보율 {retention}% * ROE {roe}% = {format_percent(growth * Decimal('100'))}",
            f"1년 말 배당금 D1 = EPS1 * (1 - b) = {format_money(eps1)} * (1 - {retention}%) = {format_money(dividend1)}",
            f"성장모형 주가 P0 = D1 / (k - g) = {format_money(dividend1)} / ({required_return}% - {format_percent(growth * Decimal('100'))}) = {format_money(growth_value)}",
            f"무성장 주가 = EPS1 / k = {format_money(eps1)} / {required_return}% = {format_money(no_growth_value)}",
            f"NPVGO = 성장모형 주가 - 무성장 주가 = {format_money(growth_value)} - {format_money(no_growth_value)} = {format_money(npvgo)}",
            f"PER = P0 / EPS1 = {format_number(per)}",
            f"PBR = PER * ROE = {format_number(per)} * {roe}% = {format_number(pbr)}",
        ],
    }


def is_constant_growth_question(question: str) -> bool:
    normalized = question.lower()
    return any(term in normalized for term in ["eps", "주당 이익", "주당순이익", "유보율", "배당성향", "npvgo", "per", "pbr"])


def find_money(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        pattern = rf"{re.escape(label)}[^0-9￦₩만원]*[￦₩]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(만|원)?"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = Decimal(match.group(1).replace(",", ""))
            unit = match.group(2)
            if unit == "만":
                return value * Decimal("10000")
            return value
    return None


def find_percent(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        pattern = rf"{re.escape(label)}[^0-9%]*([0-9]+(?:\.[0-9]+)?)\s*%"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return Decimal(match.group(1))
    return None


def format_money(value: Decimal) -> str:
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"￦{rounded:,.0f}"


def format_percent(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


def format_number(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
