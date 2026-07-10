import re
from decimal import Decimal, ROUND_HALF_UP


def analyze_valuation(question: str) -> dict:
    if "유보율" in question and "per" in question.lower() and "pbr" in question.lower() and "roe" in question.lower():
        return calculate_growth_from_per_pbr(question)

    market_ratios = calculate_market_value_ratios(question)
    if market_ratios["status"] == "ok":
        return market_ratios

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


def calculate_market_value_ratios(question: str) -> dict:
    ratios = []
    steps = []

    stock_price = find_money(question, ["현재 주가", "주가"])
    eps = find_money(question, ["기대 주당순이익", "eps", "주당순이익"])
    bps = find_money(question, ["주당 자기자본 장부가치", "bps", "주당순자산"])
    sps = find_money(question, ["기대 주당매출액", "sps", "주당매출액"])
    cps = find_money(question, ["주당현금흐름", "cps"])
    equity_market_value = find_money(question, ["자기자본 시장가치", "시가총액"])
    expected_net_income = find_money(question, ["기대 당기순이익", "당기순이익", "순이익"])
    sales = find_money(question, ["기대 매출액", "매출액"])
    operating_cash_flow = find_money(question, ["영업현금흐름"])
    replacement_cost = find_money(question, ["대체원가", "대체 비용", "총대체비용"])
    debt = find_money(question, ["차입금"])
    cash = find_money(question, ["현금및현금성자산", "현금"])
    pretax_income = find_money(question, ["세전순이익"])
    interest_expense = find_money(question, ["이자비용"])
    depreciation = find_money(question, ["감가상각비와 무형자산상각비", "감가상각비", "상각비"])

    if stock_price is not None and eps:
        per = stock_price / eps
        ratios.append(f"PER {format_number(per)}")
        steps.append(f"PER = 현재 주가 / 기대 EPS = {format_number(per)}")
    elif equity_market_value is not None and expected_net_income:
        per = equity_market_value / expected_net_income
        ratios.append(f"PER {format_number(per)}")
        steps.append(f"PER = 자기자본 시장가치 / 기대 당기순이익 = {format_number(per)}")

    if stock_price is not None and bps:
        pbr = stock_price / bps
        ratios.append(f"PBR {format_number(pbr)}")
        steps.append(f"PBR = 현재 주가 / BPS = {format_number(pbr)}")

    if stock_price is not None and sps:
        psr = stock_price / sps
        ratios.append(f"PSR {format_number(psr)}")
        steps.append(f"PSR = 현재 주가 / 기대 주당매출액 = {format_number(psr)}")
    elif equity_market_value is not None and sales:
        psr = equity_market_value / sales
        ratios.append(f"PSR {format_number(psr)}")
        steps.append(f"PSR = 자기자본 시장가치 / 기대 매출액 = {format_number(psr)}")

    if stock_price is not None and cps:
        pcr = stock_price / cps
        ratios.append(f"PCR {format_number(pcr)}")
        steps.append(f"PCR = 현재 주가 / 주당현금흐름 = {format_number(pcr)}")
    elif equity_market_value is not None and operating_cash_flow:
        pcr = equity_market_value / operating_cash_flow
        ratios.append(f"PCR {format_number(pcr)}")
        steps.append(f"PCR = 자기자본 시장가치 / 영업현금흐름 = {format_number(pcr)}")

    if equity_market_value is not None and replacement_cost:
        tobins_q = equity_market_value / replacement_cost
        ratios.append(f"Tobin's q {format_number(tobins_q)}")
        steps.append(f"Tobin's q = 시장가치 / 대체원가 = {format_number(tobins_q)}")

    if (
        equity_market_value is not None
        and debt is not None
        and cash is not None
        and pretax_income is not None
        and interest_expense is not None
        and depreciation is not None
    ):
        ev = equity_market_value + debt - cash
        ebitda = pretax_income + interest_expense + depreciation
        ev_to_ebitda = ev / ebitda
        ratios.append(f"EV/EBITDA {format_number(ev_to_ebitda)}")
        steps.append(f"EV = 시가총액 + 차입금 - 현금및현금성자산 = {format_money(ev)}")
        steps.append(f"EBITDA = 세전순이익 + 이자비용 + 감가상각비와 무형자산상각비 = {format_money(ebitda)}")
        steps.append(f"EV/EBITDA = {format_number(ev_to_ebitda)}")

    if ratios:
        return {"status": "ok", "summary": ", ".join(ratios) + "입니다.", "steps": steps}

    return {"status": "no_calculation", "summary": "", "steps": []}


def calculate_growth_from_per_pbr(question: str) -> dict:
    per = find_labeled_number(question, ["PER"])
    pbr = find_labeled_number(question, ["PBR"])
    retention = find_percent(question, ["유보율", "재투자"])

    if per is not None and pbr is not None and retention is not None:
        roe = pbr / per
        growth = roe * retention / Decimal("100")
        required_return = growth + (Decimal("1") - retention / Decimal("100")) / per
        no_growth_per = Decimal("1") / required_return
        return {
            "status": "ok",
            "summary": (
                f"ROE는 {format_percent(roe * Decimal('100'))}, 배당성장률은 {format_percent(growth * Decimal('100'))}, "
                f"할인율은 {format_percent(required_return * Decimal('100'))}, 무성장 PER은 {format_number(no_growth_per)}입니다."
            ),
            "steps": [
                f"ROE = PBR / PER = {format_number(pbr)} / {format_number(per)} = {format_percent(roe * Decimal('100'))}",
                f"배당성장률 g = ROE * 유보율 = {format_percent(roe * Decimal('100'))} * {retention}% = {format_percent(growth * Decimal('100'))}",
                f"PER = (1 - b) / (k - g)이므로 k = g + (1 - b) / PER = {format_percent(required_return * Decimal('100'))}",
                f"무성장 PER = 1 / k = {format_number(no_growth_per)}",
            ],
        }

    return {
        "status": "need_more_data",
        "summary": "PER/PBR 역산에는 PER, PBR, 유보율이 필요합니다.",
        "steps": [],
    }


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


def find_labeled_number(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}[^0-9]*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
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
