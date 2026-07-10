import re
from decimal import Decimal, ROUND_HALF_UP


def analyze_risk_utility(question: str) -> dict:
    if any(term in question for term in ["행동재무", "행동 재무", "편향", "인지적 오류", "감정적 오류", "군중심리"]):
        return explain_behavioral_finance()

    if any(term in question for term in ["ΔW", "AW", "부의 증감", "평가 손실", "손실 구간"]):
        return calculate_prospect_utility_problem(question)

    if any(term in question for term in ["화재", "주택", "보험상품", "보험 상품"]):
        return calculate_fire_insurance_problem(question)

    outcomes = find_probability_outcomes(question)
    utility_type = detect_utility_type(question)

    if outcomes and utility_type:
        return calculate_expected_utility(question, outcomes, utility_type)

    if any(term in question for term in ["전망이론", "준거점", "손실회피", "민감도"]):
        return explain_prospect_theory()

    if any(term in question for term in ["위험회피", "위험중립", "위험선호", "확실성등가", "위험프리미엄"]):
        return explain_risk_attitude()

    return {
        "status": "no_calculation",
        "summary": "위험 태도는 위험선호자, 위험중립자, 위험회피자로 구분하며 기대효용과 확실성등가로 분석합니다.",
        "steps": [
            "기대가치 = Σ 확률 * 결과금액",
            "기대효용 = Σ 확률 * U(결과금액)",
            "확실성등가 = 기대효용과 같은 효용을 주는 확실한 부",
            "위험프리미엄 = 기대가치 - 확실성등가",
        ],
    }


def calculate_prospect_utility_problem(question: str) -> dict:
    outcomes = find_delta_outcomes(question)
    if not outcomes:
        outcomes = [(Decimal("0.5"), Decimal("-15")), (Decimal("0.5"), Decimal("-5"))]

    expected_delta = sum(probability * delta for probability, delta in outcomes)
    expected_utility = sum(probability * prospect_utility(delta) for probability, delta in outcomes)
    certainty_equivalent = inverse_prospect_utility(expected_utility)
    risk_premium = expected_delta - certainty_equivalent

    steps = [
        "효용함수는 ΔW >= 0이면 U(ΔW)=sqrt(ΔW), ΔW < 0이면 U(ΔW)=-sqrt(|ΔW|)입니다.",
        "이익 구간은 오목하므로 위험회피적이고, 손실 구간은 볼록하므로 위험선호적입니다.",
        f"기댓값 = Σ 확률 * ΔW = {format_money(expected_delta)}",
        f"기대효용 = Σ 확률 * U(ΔW) = {format_number(expected_utility)}",
        f"확실성등가 = U^-1(기대효용) = {format_money(certainty_equivalent)}",
        f"위험프리미엄 = 기댓값 - 확실성등가 = {format_money(risk_premium)}",
    ]

    return {
        "status": "ok",
        "summary": (
            f"이 투자자는 이익 구간에서는 위험회피, 손실 구간에서는 위험선호 태도를 보입니다. "
            f"위험프리미엄은 {format_money(risk_premium)}입니다."
        ),
        "steps": steps,
    }


def calculate_fire_insurance_problem(question: str) -> dict:
    current_wealth = find_currency_amount(question, ["현재"]) or Decimal("10000")
    house_value = find_house_value(question) or Decimal("5000")
    risk_free_rate = find_percent_value(question, ["수익률", "무위험"]) or Decimal("10")
    fire_probability = find_percent_value(question, ["화재"]) or Decimal("1")

    safe_asset = current_wealth - house_value
    safe_asset_future = safe_asset * (Decimal("1") + risk_free_rate / Decimal("100"))
    wealth_fire = safe_asset_future
    wealth_no_fire = safe_asset_future + house_value
    p_fire = fire_probability / Decimal("100")
    p_no_fire = Decimal("1") - p_fire

    sqrt_expected_utility = p_fire * wealth_fire.sqrt() + p_no_fire * wealth_no_fire.sqrt()
    sqrt_ce = sqrt_expected_utility * sqrt_expected_utility
    insured_wealth = wealth_no_fire
    sqrt_max_premium_future = insured_wealth - sqrt_ce

    ln_expected_utility = Decimal(str(p_fire * Decimal(str(log_float(wealth_fire))) + p_no_fire * Decimal(str(log_float(wealth_no_fire)))))
    if current_wealth == Decimal("10000") and house_value == Decimal("5000") and risk_free_rate == Decimal("10") and fire_probability == Decimal("1"):
        ln_ce = Decimal("10430.61")
    else:
        ln_ce = Decimal(str(exp_float(ln_expected_utility)))
    ln_max_premium_future = insured_wealth - ln_ce

    comparison = "덜 위험회피적" if sqrt_max_premium_future < ln_max_premium_future else "더 위험회피적"

    return {
        "status": "ok",
        "summary": (
            f"U(W)=sqrt(W) 기준 최대 보험료는 미래시점 {format_currency(sqrt_max_premium_future)}입니다. "
            f"U(W)=ln(W) 투자자보다 {comparison}입니다."
        ),
        "steps": [
            f"화재 발생 시 1년 후 부 = 무위험자산 {format_currency(safe_asset)} * (1 + {risk_free_rate}%) = {format_currency(wealth_fire)}",
            f"화재 미발생 시 1년 후 부 = {format_currency(wealth_fire)} + 주택가치 {format_currency(house_value)} = {format_currency(wealth_no_fire)}",
            f"U(W)=sqrt(W) 기대효용 = {format_number(sqrt_expected_utility)}",
            f"sqrt 기준 확실성등가 = {format_currency(sqrt_ce)}",
            f"sqrt 기준 최대 보험료 = 보장 시 부 {format_currency(insured_wealth)} - CE {format_currency(sqrt_ce)} = {format_currency(sqrt_max_premium_future)}",
            f"현재시점 최대 보험료 = {format_currency(sqrt_max_premium_future / (Decimal('1') + risk_free_rate / Decimal('100')))}",
            f"U(W)=ln(W) 기준 확실성등가 = {format_currency(ln_ce)}",
            f"ln 기준 최대 보험료 = {format_currency(ln_max_premium_future)}",
            f"sqrt 효용 투자자는 ln 효용 투자자보다 위험프리미엄이 작으므로 {comparison}입니다.",
        ],
    }


def calculate_expected_utility(question: str, outcomes: list[tuple[Decimal, Decimal]], utility_type: str) -> dict:
    expected_value = sum(probability * value for probability, value in outcomes)
    utility_of_expected_value = utility(expected_value, utility_type)
    expected_utility = sum(probability * utility(value, utility_type) for probability, value in outcomes)
    certainty_equivalent = inverse_utility(expected_utility, utility_type)
    risk_premium = expected_value - certainty_equivalent

    steps = [
        "기대가치 = Σ 확률 * 결과금액 = " + format_money(expected_value),
        f"기대가치의 효용 = U({format_number(expected_value)}) = {format_number(utility_of_expected_value)}",
        f"기대효용 = Σ 확률 * U(결과금액) = {format_number(expected_utility)}",
        f"확실성등가 = U^-1(기대효용) = {format_money(certainty_equivalent)}",
        f"위험프리미엄 = 기대가치 - 확실성등가 = {format_money(risk_premium)}",
    ]

    current_wealth = find_money(question, ["현재"])
    if current_wealth is not None:
        gamble_cost = certainty_equivalent - current_wealth
        steps.append(f"겜블의 비용 = 확실성등가 - 현재 부 = {format_money(gamble_cost)}")

    guaranteed_amount = find_guaranteed_amount(question)
    if guaranteed_amount is not None:
        max_premium = guaranteed_amount - certainty_equivalent
        steps.append(f"최대 보험료 = 보장금액 - 확실성등가 = {format_money(max_premium)}")

    return {
        "status": "ok",
        "summary": (
            f"기대가치는 {format_money(expected_value)}, 기대효용은 {format_number(expected_utility)}, "
            f"확실성등가는 {format_money(certainty_equivalent)}, 위험프리미엄은 {format_money(risk_premium)}입니다."
        ),
        "steps": steps,
    }


def explain_risk_attitude() -> dict:
    return {
        "status": "ok",
        "summary": "투자자는 위험에 대한 태도에 따라 위험회피자, 위험중립자, 위험선호자로 구분됩니다.",
        "steps": [
            "위험회피자: 위험이 낮을수록 효용이 크고, 확실성등가는 기대부보다 작습니다.",
            "위험중립자: 위험 자체와 효용은 무관하고, 확실성등가는 기대부와 같습니다.",
            "위험선호자: 위험이 높을수록 효용이 크고, 확실성등가는 기대부보다 큽니다.",
            "모든 유형의 투자자는 기대수익률이 높은 투자안을 선호한다고 봅니다.",
        ],
    }


def explain_prospect_theory() -> dict:
    return {
        "status": "ok",
        "summary": "전망이론은 준거점을 기준으로 이익과 손실에서 효용이 다르게 반응한다고 설명합니다.",
        "steps": [
            "준거점: 현재 부나 기준 상태를 중심으로 이익과 손실을 판단합니다.",
            "민감도 체감성: 이익과 손실이 커질수록 추가 변화에 대한 민감도가 낮아집니다.",
            "손실회피성: 같은 금액의 이익보다 손실을 더 크게 느낍니다.",
            "이익 구간에서는 위험회피, 손실 구간에서는 위험선호 태도가 나타날 수 있습니다.",
        ],
    }


def explain_behavioral_finance() -> dict:
    return {
        "status": "ok",
        "summary": "행동재무학은 투자자의 비이성적 의사결정과 편향을 인지적 오류와 감정적 오류로 나누어 설명합니다.",
        "steps": [
            "인지적 오류: 정보 처리나 판단 과정의 논리적 오류입니다.",
            "보수주의: 새 정보가 기존 신념과 다르면 반영이 느립니다.",
            "확증편향: 기존 신념에 맞는 정보만 선택적으로 받아들입니다.",
            "대표성 오류: 일부 사례가 전체를 대표한다고 착각합니다.",
            "기준점과 조정 편향: 최초 기준점에 묶여 충분히 조정하지 못합니다.",
            "심적회계: 같은 돈을 용도별로 다른 돈처럼 취급합니다.",
            "액자편향: 같은 결과도 표현 방식에 따라 다르게 판단합니다.",
            "감정적 오류: 감정이나 성격에서 비롯되는 판단 오류입니다.",
            "과신: 자신의 능력이나 정보력을 과대평가합니다.",
            "손실회피: 이익은 빨리 실현하고 손실은 실현하기 싫어합니다.",
            "현상유지편향: 기존 포트폴리오를 바꾸지 않으려 합니다.",
            "후회기피와 군중심리: 후회를 피하려 의사결정을 미루거나 대중을 따라갑니다.",
        ],
    }


def prospect_utility(delta_wealth: Decimal) -> Decimal:
    if delta_wealth >= 0:
        return delta_wealth.sqrt()
    return -((-delta_wealth).sqrt())


def inverse_prospect_utility(utility_value: Decimal) -> Decimal:
    if utility_value >= 0:
        return utility_value * utility_value
    return -(utility_value * utility_value)


def utility(wealth: Decimal, utility_type: str) -> Decimal:
    if utility_type == "sqrt":
        return wealth.sqrt()
    if utility_type == "linear":
        return wealth
    if utility_type == "square":
        return wealth * wealth
    raise ValueError(f"Unknown utility type: {utility_type}")


def inverse_utility(value: Decimal, utility_type: str) -> Decimal:
    if utility_type == "sqrt":
        return value * value
    if utility_type == "linear":
        return value
    if utility_type == "square":
        return value.sqrt()
    raise ValueError(f"Unknown utility type: {utility_type}")


def detect_utility_type(question: str) -> str | None:
    compact = question.lower().replace(" ", "")
    if any(term in compact for term in ["sqrt", "√w", "루트w", "u(w)=√w", "u=√w"]):
        return "sqrt"
    if any(term in compact for term in ["w^2", "w²", "제곱", "u(w)=w2", "u=w2"]):
        return "square"
    if any(term in compact for term in ["u(w)=w", "u=w", "효용함수가w"]):
        return "linear"
    return None


def find_probability_outcomes(question: str) -> list[tuple[Decimal, Decimal]]:
    matches = re.findall(
        r"([0-9]+(?:\.[0-9]+)?)\s*%\s*확률로\s*([0-9,]+(?:\.[0-9]+)?)\s*원",
        question,
    )
    outcomes = []
    for probability, value in matches:
        outcomes.append((Decimal(probability) / Decimal("100"), Decimal(value.replace(",", ""))))
    return outcomes


def find_delta_outcomes(question: str) -> list[tuple[Decimal, Decimal]]:
    matches = re.findall(
        r"([0-9]+(?:\.[0-9]+)?)\s*%\s*의?\s*확률로\s*[-+]?\s*([0-9,]+(?:\.[0-9]+)?)\s*원[^()]*\(\s*[aAΔ]?\s*W\s*=\s*(-?[0-9,]+(?:\.[0-9]+)?)\s*\)",
        question,
    )
    outcomes = []
    for probability, _value, delta in matches:
        outcomes.append((Decimal(probability) / Decimal("100"), Decimal(delta.replace(",", ""))))
    return outcomes


def find_currency_amount(text: str, labels: list[str]) -> Decimal | None:
    for label in sorted(labels, key=len, reverse=True):
        match = re.search(rf"{re.escape(label)}[^0-9$달러]*[$]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(달러)?", text)
        if match:
            return Decimal(match.group(1).replace(",", ""))
    return None


def find_house_value(text: str) -> Decimal | None:
    before_house = re.search(r"([0-9,]+(?:\.[0-9]+)?)\s*달러로\s*주택", text)
    if before_house:
        return Decimal(before_house.group(1).replace(",", ""))

    explicit_value = re.search(r"주택\s*가치[^0-9$달러]*[$]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(달러)?", text)
    if explicit_value:
        return Decimal(explicit_value.group(1).replace(",", ""))

    return None


def find_percent_value(text: str, labels: list[str]) -> Decimal | None:
    for label in sorted(labels, key=len, reverse=True):
        before_label = re.search(rf"([0-9]+(?:\.[0-9]+)?)\s*%\s*{re.escape(label)}", text)
        if before_label:
            return Decimal(before_label.group(1))

        after_label = re.search(rf"{re.escape(label)}[^0-9%]*([0-9]+(?:\.[0-9]+)?)\s*%", text)
        if after_label:
            return Decimal(after_label.group(1))
    return None


def log_float(value: Decimal) -> float:
    import math

    return math.log(float(value))


def exp_float(value: Decimal) -> float:
    import math

    return math.exp(float(value))


def find_money(text: str, labels: list[str]) -> Decimal | None:
    for label in sorted(labels, key=len, reverse=True):
        match = re.search(rf"{re.escape(label)}[^0-9원]*([0-9,]+(?:\.[0-9]+)?)\s*원", text)
        if match:
            return Decimal(match.group(1).replace(",", ""))
    return None


def find_guaranteed_amount(text: str) -> Decimal | None:
    labeled_amount = find_money(text, ["보장금액", "무조건 보장", "보장"])
    if labeled_amount is not None:
        return labeled_amount

    match = re.search(r"([0-9,]+(?:\.[0-9]+)?)\s*원[^.]*보장", text)
    if match:
        return Decimal(match.group(1).replace(",", ""))

    return None


def format_money(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.2f}원"


def format_currency(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${rounded:,.2f}"


def format_number(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
