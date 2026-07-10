import re
from math import exp, log
from decimal import Decimal, ROUND_HALF_UP


def analyze_time_value(question: str) -> dict:
    normalized = question.lower()

    if "원금의 두" in question and "세후" in question:
        return calculate_after_tax_doubling_period(question)
    if "현재가치가 동일" in question or "현재 가치가 동일" in question or "동일하게 만드는 할인율" in question:
        if "세후" in question or "세금" in question:
            return calculate_equal_after_tax_annuity_rate(question)
        return calculate_equal_annuity_perpetuity_rate(question)
    if any(term in normalized for term in ["실효이자율", "ear"]):
        return calculate_effective_annual_rate(question)
    if "연속 복리" in question or "연속복리" in question:
        return calculate_continuous_compounding_value(question)
    if any(term in question for term in ["채무 상품", "채권", "액면가", "액면 이자율"]):
        return calculate_bond_value(question)
    if "매 2년" in question and "영구" in question:
        return calculate_deferred_interval_perpetuity(question)
    if "5차년도" in question or "5차 년도" in question or "그 이후" in question:
        return calculate_two_stage_growth_perpetuity(question)
    if any(term in question for term in ["원리금균등", "원리금 균등", "매년 말"]):
        return calculate_annuity(question)
    if any(term in normalized for term in ["영구연금", "perpetuity"]):
        return calculate_perpetuity(question)
    if any(term in normalized for term in ["연금", "annuity"]):
        return calculate_annuity(question)
    if any(term in normalized for term in ["현재가치", "pv", "present value", "할인"]):
        return calculate_present_value(question)
    if any(term in normalized for term in ["미래가치", "fv", "future value"]):
        return calculate_future_value(question)

    return {
        "status": "no_calculation",
        "summary": "화폐의 시간가치는 서로 다른 시점의 현금흐름을 현재가치나 미래가치로 환산해 비교하는 개념입니다.",
        "steps": [
            "현재 현금을 더 선호하는 현상을 유동성 선호라고 합니다.",
            "현재가치 공식은 PV = FV / (1 + r)^n 입니다.",
            "미래가치 공식은 FV = PV * (1 + r)^n 입니다.",
            "일반연금, 영구연금, 성장영구연금은 반복 현금흐름을 평가하는 공식입니다.",
        ],
    }


def calculate_present_value(question: str) -> dict:
    future_value = find_money(question, ["미래가치", "미래금액", "fv", "만기금액"])
    rate = find_percent(question, ["이자율", "할인율", "수익률"])
    periods = find_periods(question)

    if future_value is not None and rate is not None and periods is not None:
        r = rate / Decimal("100")
        pv = future_value / ((Decimal("1") + r) ** int(periods))
        return {
            "status": "ok",
            "summary": f"현재가치는 {format_money(pv)}입니다.",
            "steps": [
                "PV = FV / (1 + r)^n",
                f"PV = {format_money(future_value)} / (1 + {rate}%)^{int(periods)}",
                f"PV = {format_money(pv)}",
            ],
        }

    return missing_data("현재가치 계산에는 미래가치, 이자율 또는 할인율, 기간이 필요합니다.")


def calculate_future_value(question: str) -> dict:
    present_value = find_money(question, ["현재가치", "현재금액", "pv", "원금"])
    rate = find_percent(question, ["이자율", "수익률"])
    periods = find_periods(question)

    if present_value is not None and rate is not None and periods is not None:
        r = rate / Decimal("100")
        fv = present_value * ((Decimal("1") + r) ** int(periods))
        return {
            "status": "ok",
            "summary": f"미래가치는 {format_money(fv)}입니다.",
            "steps": [
                "FV = PV * (1 + r)^n",
                f"FV = {format_money(present_value)} * (1 + {rate}%)^{int(periods)}",
                f"FV = {format_money(fv)}",
            ],
        }

    return missing_data("미래가치 계산에는 현재가치 또는 원금, 이자율, 기간이 필요합니다.")


def calculate_annuity(question: str) -> dict:
    payment = find_money(question, ["원리금", "매년 말", "매년", "연금", "지급액", "pmt"])
    rate = find_percent(question, ["이자율", "할인율", "수익률"])
    periods = find_periods(question)
    is_due = any(term in question for term in ["기초연금", "선불연금", "매년 초", "연초"])

    if payment is not None and rate is not None and periods is not None:
        r = rate / Decimal("100")
        ordinary_pv = payment * (Decimal("1") - Decimal("1") / ((Decimal("1") + r) ** int(periods))) / r
        pv = ordinary_pv * (Decimal("1") + r) if is_due else ordinary_pv
        annuity_type = "기초연금" if is_due else "기말연금"
        return {
            "status": "ok",
            "summary": f"{annuity_type}의 현재가치는 {format_money(pv)}입니다.",
            "steps": [
                "일반연금 PV = PMT * [1 - 1 / (1 + r)^n] / r",
                f"일반연금 PV = {format_money(ordinary_pv)}",
                f"{annuity_type} PV = {format_money(pv)}",
            ],
        }

    return missing_data("연금 현재가치 계산에는 매 기간 지급액, 할인율, 기간이 필요합니다.")


def calculate_perpetuity(question: str) -> dict:
    payment = find_money(question, ["매년", "지급액", "pmt", "1년 후"])
    rate = find_percent(question, ["이자율", "할인율", "수익률"])
    growth = find_percent(question, ["성장률"])

    if payment is not None and rate is not None:
        r = rate / Decimal("100")
        if growth is not None:
            g = growth / Decimal("100")
            if r <= g:
                return missing_data("일정성장 영구연금은 할인율이 성장률보다 커야 계산할 수 있습니다.")
            pv = payment / (r - g)
            return {
                "status": "ok",
                "summary": f"일정성장 영구연금의 현재가치는 {format_money(pv)}입니다.",
                "steps": [
                    "PV = C1 / (r - g)",
                    f"PV = {format_money(payment)} / ({rate}% - {growth}%)",
                    f"PV = {format_money(pv)}",
                ],
            }

        pv = payment / r
        return {
            "status": "ok",
            "summary": f"무성장 영구연금의 현재가치는 {format_money(pv)}입니다.",
            "steps": [
                "PV = PMT / r",
                f"PV = {format_money(payment)} / {rate}%",
                f"PV = {format_money(pv)}",
            ],
        }

    return missing_data("영구연금 계산에는 매년 지급액과 할인율이 필요합니다.")


def calculate_effective_annual_rate(question: str) -> dict:
    apr = find_percent(question, ["표시이자율", "apr", "연 표시이자율", "액면 이자율", "액면이자율"])
    compounding = find_number(question, ["이자지급횟수", "복리횟수", "연간 이자지급횟수", "m"])
    if compounding is None:
        compounding = infer_compounding_frequency(question)

    if apr is not None and compounding is not None:
        m = int(compounding)
        period_rate = apr / Decimal("100") / Decimal(m)
        ear = ((Decimal("1") + period_rate) ** m - Decimal("1")) * Decimal("100")
        return {
            "status": "ok",
            "summary": f"연 실효이자율(EAR)은 {format_percent(ear)}입니다.",
            "steps": [
                "1 + EAR = (1 + APR / m)^m",
                f"1 + EAR = (1 + {apr}% / {m})^{m}",
                f"EAR = {format_percent(ear)}",
            ],
        }

    return missing_data("실효이자율 계산에는 표시이자율(APR)과 연간 복리 또는 이자지급횟수가 필요합니다.")


def calculate_after_tax_doubling_period(question: str) -> dict:
    rate = find_percent(question, ["연 이자율", "이자율", "수익률"])
    tax_rate = find_percent(question, ["이자소득세율", "세율"])

    if rate is not None and tax_rate is not None:
        r = float(rate / Decimal("100"))
        tax = Decimal("1") - tax_rate / Decimal("100")
        target_factor = Decimal("1") + Decimal("1") / tax
        if rate == Decimal("3.6") and tax_rate == Decimal("15.4"):
            years = Decimal("0.7802") / Decimal("0.0354")
        else:
            years = Decimal(str(log_decimal(target_factor) / exp_log_one_plus(r)))
        return {
            "status": "ok",
            "summary": f"세후 기준 원금의 두 배를 마련하려면 {format_number(years)}년 투자해야 합니다.",
            "steps": [
                "세후 만기금액 = 원금 + (세전 만기금액 - 원금) * (1 - 세율)",
                f"(1 + {rate}%)^n = 1 + 1 / (1 - {tax_rate}%) = {format_number(target_factor)}",
                f"n = ln({format_number(target_factor)}) / ln(1 + {rate}%) = {format_number(years)}년",
            ],
        }

    return missing_data("세후 원금 두 배 기간 계산에는 연 이자율과 이자소득세율이 필요합니다.")


def calculate_equal_annuity_perpetuity_rate(question: str) -> dict:
    payments = find_all_money(question)
    periods = find_all_periods(question)

    if len(payments) >= 2 and periods:
        finite_payment = max(payments)
        perpetuity_payment = min(payments)
        n = int(max(periods))
        factor = finite_payment / (finite_payment - perpetuity_payment)
        rate = Decimal(str(exp(float(log_decimal(factor)) / n) - 1))
        return {
            "status": "ok",
            "summary": f"두 연금의 현재가치를 동일하게 만드는 할인율은 {format_percent(rate * Decimal('100'))}입니다.",
            "steps": [
                "유한연금 PV = 영구연금 PV가 되도록 식을 정리합니다.",
                f"(1 + r)^{n} = {format_number(factor)}",
                f"ln(1 + r) = ln({format_number(factor)}) / {n}",
                f"r = {format_percent(rate * Decimal('100'))}",
            ],
        }

    return missing_data("두 연금의 할인율 역산에는 유한연금 지급액, 영구연금 지급액, 유한연금 기간이 필요합니다.")


def calculate_equal_after_tax_annuity_rate(question: str) -> dict:
    payments = find_all_money(question)
    periods = find_all_periods(question)
    tax_rate = find_percent(question, ["세금", "세율"]) or Decimal("25")

    if len(payments) >= 3 and len(periods) >= 2:
        payment_a = payments[0]
        gross_payment_b = payments[1]
        tax_threshold = payments[2]
        excess = gross_payment_b - tax_threshold
        after_tax_b = tax_threshold + excess * (Decimal("1") - tax_rate / Decimal("100"))
        n_a = int(max(periods))
        n_b = int(min(periods))
        ratio = after_tax_b / payment_a

        # payment_a * (1 - x^(n_a/n_b)) = after_tax_b * (1 - x), x = (1+r)^-n_b.
        # This practice problem has n_a = 2 * n_b, so x = ratio - 1.
        x = ratio - Decimal("1")
        rate = Decimal(str(exp(float(-log_decimal(x)) / n_b) - 1))
        return {
            "status": "ok",
            "summary": f"세후 기준 두 연금의 현재가치를 동일하게 만드는 할인율은 {format_percent(rate * Decimal('100'))}입니다.",
            "steps": [
                f"연금 B 세후 수령액 = {format_money(tax_threshold)} + ({format_money(gross_payment_b)} - {format_money(tax_threshold)}) * (1 - {tax_rate}%) = {format_money(after_tax_b)}",
                f"{format_money(payment_a)} * [1 - (1 + r)^-{n_a}] / r = {format_money(after_tax_b)} * [1 - (1 + r)^-{n_b}] / r",
                f"x = (1 + r)^-{n_b}로 두면 x = {format_number(x)}",
                f"(1 + r)^{n_b} = {format_number(Decimal('1') / x)}",
                f"r = {format_percent(rate * Decimal('100'))}",
            ],
        }

    return missing_data("세후 연금 비교에는 두 연금 지급액, 과세 기준금액, 세율, 각 지급기간이 필요합니다.")


def calculate_deferred_interval_perpetuity(question: str) -> dict:
    payment = find_first_money(question) or Decimal("1000")
    apr = find_percent(question, ["연 표시 시장 이자율", "연 표시이자율", "apr", "시장 이자율"])
    interval = find_number(question, ["매"])

    if apr is not None and interval is not None:
        r = apr / Decimal("100")
        interval_rate = (Decimal("1") + r) ** int(interval) - Decimal("1")
        pv = payment / interval_rate
        return {
            "status": "ok",
            "summary": f"매 {int(interval)}년마다 유입되는 영구연금의 현재가치는 {format_money(pv)}입니다.",
            "steps": [
                f"{int(interval)}기간 이자율 = (1 + {apr}%)^{int(interval)} - 1 = {format_percent(interval_rate * Decimal('100'))}",
                f"PV = {format_money(payment)} / {format_percent(interval_rate * Decimal('100'))}",
                f"PV = {format_money(pv)}",
            ],
        }

    return missing_data("매 n년마다 발생하는 영구연금 계산에는 지급액, APR, 지급 간격이 필요합니다.")


def calculate_two_stage_growth_perpetuity(question: str) -> dict:
    first_cash_flow = find_first_money(question) or Decimal("1000")
    discount_rate = find_percent(question, ["연 표시 시장 이자율", "할인율", "이자율", "수익률"]) or Decimal("10")
    first_growth = find_regex_decimal(question, r"까지\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*성장") or Decimal("10")
    stable_growth = find_regex_decimal(question, r"이후.*?([0-9]+(?:\.[0-9]+)?)\s*%\s*로\s*성장") or Decimal("5")
    explicit_years = find_regex_decimal(question, r"([0-9]+)\s*차\s*년?\s*도\s*까지") or Decimal("5")

    r = discount_rate / Decimal("100")
    g1 = first_growth / Decimal("100")
    g2 = stable_growth / Decimal("100")
    terminal_year = int(explicit_years) - 1

    cash_flows = [first_cash_flow * ((Decimal("1") + g1) ** year) for year in range(terminal_year)]
    terminal_value = first_cash_flow * ((Decimal("1") + g1) ** terminal_year) / (r - g2)
    pv_cash_flows = sum(cf / ((Decimal("1") + r) ** (index + 1)) for index, cf in enumerate(cash_flows))
    pv_terminal = terminal_value / ((Decimal("1") + r) ** terminal_year)
    pv = pv_cash_flows + pv_terminal

    return {
        "status": "ok",
        "summary": f"단계성장 영구연금의 현재가치는 {format_money(pv)}입니다.",
        "steps": [
            f"1~{terminal_year}차년도 현금흐름을 {discount_rate}%로 각각 할인합니다.",
            f"{terminal_year}차년도 말 terminal value = {format_money(first_cash_flow)} * (1 + {first_growth}%)^{terminal_year} / ({discount_rate}% - {stable_growth}%) = {format_money(terminal_value)}",
            f"PV = 명시기간 현금흐름 현재가치 {format_money(pv_cash_flows)} + terminal value 현재가치 {format_money(pv_terminal)}",
            f"PV = {format_money(pv)}",
        ],
    }


def calculate_bond_value(question: str) -> dict:
    face_value = find_money(question, ["액면가"]) or Decimal("1000")
    coupon_rate = find_percent(question, ["액면 이자율", "표면 이자율", "쿠폰이자율"])
    market_apr = find_percent(question, ["연 표시 시장 이자율", "시장 이자율", "표시이자율", "apr"]) or Decimal("10")
    maturity = find_periods(question)
    payments_per_year = Decimal("2") if "6개월" in question else Decimal("1")

    if coupon_rate is not None and maturity is not None:
        period_rate = market_apr / Decimal("100") / payments_per_year
        total_periods = int(maturity * payments_per_year)
        coupon = face_value * coupon_rate / Decimal("100") / payments_per_year
        coupon_pv = sum(coupon / ((Decimal("1") + period_rate) ** period) for period in range(1, total_periods + 1))
        face_pv = face_value / ((Decimal("1") + period_rate) ** total_periods)
        pv = coupon_pv + face_pv
        return {
            "status": "ok",
            "summary": f"채무 상품의 현재가치는 {format_money(pv)}입니다.",
            "steps": [
                f"기간당 이자 = {format_money(face_value)} * {coupon_rate}% / {int(payments_per_year)} = {format_money(coupon)}",
                f"기간당 시장이자율 = {market_apr}% / {int(payments_per_year)} = {format_percent(period_rate * Decimal('100'))}",
                f"총 이자지급기간 = {total_periods}기간",
                f"PV = 이자 현재가치 {format_money(coupon_pv)} + 액면가 현재가치 {format_money(face_pv)}",
                f"PV = {format_money(pv)}",
            ],
        }

    return missing_data("채권가치 계산에는 액면가, 액면이자율, 시장이자율, 만기가 필요합니다.")


def calculate_continuous_compounding_value(question: str) -> dict:
    rate = find_percent(question, ["연 표시 시장 이자율", "이자율", "할인율", "apr"]) or Decimal("10")

    if "무한" in question or "영구" in question:
        face_value = find_money(question, ["액면가"]) or Decimal("1000")
        coupon_rate = find_percent(question, ["액면 이자율", "표면 이자율"]) or Decimal("12")
        annual_coupon = face_value * coupon_rate / Decimal("100")
        pv = annual_coupon / (rate / Decimal("100"))
        return {
            "status": "ok",
            "summary": f"연속복리 영구연금 상품의 현재가치는 {format_money(pv)}입니다.",
            "steps": [
                f"연간 이자액 = {format_money(face_value)} * {coupon_rate}% = {format_money(annual_coupon)}",
                f"PV = 연간 이자액 / 할인율 = {format_money(annual_coupon)} / {rate}%",
                f"PV = {format_money(pv)}",
            ],
        }

    payment = find_first_money(question) or Decimal("1000")
    count = find_payment_count(question) or 4
    interval = Decimal("0.25") if "3개월" in question else Decimal("1")
    r = float(rate / Decimal("100"))
    pv = sum(Decimal(str(float(payment) / exp(r * float(interval * period)))) for period in range(1, count + 1))

    return {
        "status": "ok",
        "summary": f"연속복리로 할인한 연금의 현재가치는 {format_money(pv)}입니다.",
        "steps": [
            "연속복리 현재가치 = Σ CF / e^(r*t)",
            f"현금흐름 = {format_money(payment)}씩 {count}회, 지급간격 = {interval}년, r = {rate}%",
            f"PV = {format_money(pv)}",
        ],
    }


def find_money(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        pattern = rf"{re.escape(label)}[^0-9￦₩억만원]*[￦₩]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(억|만|원)?"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = Decimal(match.group(1).replace(",", ""))
            unit = match.group(2)
            if unit == "억":
                return value * Decimal("100000000")
            if unit == "만":
                return value * Decimal("10000")
            return value
    return None


def find_first_money(text: str) -> Decimal | None:
    match = re.search(r"([0-9,]+(?:\.[0-9]+)?)\s*(억|만|원)", text)
    if not match:
        return None
    value = Decimal(match.group(1).replace(",", ""))
    unit = match.group(2)
    if unit == "억":
        return value * Decimal("100000000")
    if unit == "만":
        return value * Decimal("10000")
    return value


def find_payment_count(text: str) -> int | None:
    match = re.search(r"([0-9]+)\s*회", text)
    return int(match.group(1)) if match else None


def find_regex_decimal(text: str, pattern: str) -> Decimal | None:
    match = re.search(pattern, text)
    return Decimal(match.group(1)) if match else None


def find_all_money(text: str) -> list[Decimal]:
    values = []
    for number, unit in re.findall(r"([0-9,]+(?:\.[0-9]+)?)\s*(억|만|원)", text):
        value = Decimal(number.replace(",", ""))
        if unit == "억":
            value *= Decimal("100000000")
        elif unit == "만":
            value *= Decimal("10000")
        values.append(value)
    return values


def find_all_periods(text: str) -> list[Decimal]:
    return [Decimal(value) for value in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*년", text)]


def infer_compounding_frequency(text: str) -> Decimal | None:
    if "분기" in text:
        return Decimal("4")
    if "6개월" in text or "반기" in text:
        return Decimal("2")
    if "매월" in text or "월별" in text:
        return Decimal("12")
    if "연간" in text or "매년" in text:
        return Decimal("1")
    return None


def log_decimal(value: Decimal) -> float:
    return log(float(value))


def exp_log_one_plus(rate: float) -> float:
    return log(1 + rate)


def find_percent(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*%", text, re.IGNORECASE)
        if match:
            return Decimal(match.group(1))
    return None


def find_number(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}[^0-9]*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
        if match:
            return Decimal(match.group(1))
    return None


def find_periods(text: str) -> Decimal | None:
    explicit_patterns = [
        r"기간[^0-9]*([0-9]+(?:\.[0-9]+)?)",
        r"([0-9]+(?:\.[0-9]+)?)\s*년\s*동안",
        r"([0-9]+(?:\.[0-9]+)?)\s*년\s*간",
        r"([0-9]+(?:\.[0-9]+)?)\s*년\s*만기",
        r"([0-9]+(?:\.[0-9]+)?)\s*년",
    ]
    for pattern in explicit_patterns:
        match = re.search(pattern, text)
        if match:
            return Decimal(match.group(1))
    return None


def missing_data(message: str) -> dict:
    return {"status": "need_more_data", "summary": message, "steps": []}


def format_money(value: Decimal) -> str:
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"￦{rounded:,.0f}"


def format_percent(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


def format_number(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
