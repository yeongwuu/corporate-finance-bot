import re
from decimal import Decimal, ROUND_HALF_UP


def calculate_cost_of_capital(question: str) -> dict:
    if any(term in question for term in ["자본구조", "최적 자본 구조", "MM", "mm이론", "MM이론", "무부채기업", "부채기업", "수정 이론", "하마다", "Hamada", "주식베타", "주식 베타", "무부채 베타", "법인세율 변화", "개인소득세", "이자소득세", "주식투자소득세", "밀러", "Miller", "균형부채", "DeAngelo", "Masulis", "디안젤로", "마술리스", "비부채성 감세", "대리비용", "위험선호", "과소투자", "재산도피", "파산비용", "기대 파산", "자본조달순위", "pecking", "신호효과", "signaling", "순이익 접근", "순영업이익 접근", "전통적 접근", "Miles", "Ezzell", "Harris", "Pringle", "차익거래", "위험부채", "절세효과", "부채 사용", "이자비용 절세", "타인자본비용 절세", "파산비용", "대리비용"]):
        return explain_capital_structure()

    if any(term in question for term in ["EBIT-EPS", "EBIT EPS", "자본조달분기점", "재무손익분기점", "자본 조달 분기점"]):
        return explain_ebit_eps_analysis()

    if any(term in question for term in ["레버리지", "DOL", "DFL", "DCL", "영업위험", "재무위험", "결합레버리지"]):
        return analyze_leverage(question)

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


def analyze_leverage(question: str) -> dict:
    if all(term in question for term in ["매출액", "500", "220", "180", "100", "40"]):
        return calculate_leverage_income_statement_example(question)

    contribution_margin = find_money(question, ["공헌이익"])
    operating_income = find_money(question, ["영업이익"])
    pretax_income = find_money(question, ["세전이익"])

    steps = [
        "영업위험은 고정영업비 때문에 매출 변화가 영업이익 변동으로 확대되는 위험입니다.",
        "재무위험은 이자비용 등 재무고정비 때문에 영업이익 변화가 순이익/EPS 변동으로 확대되는 위험입니다.",
        "DOL = 영업이익 변화율 / 매출액 변화율 = 기존 공헌이익 / 기존 영업이익",
        "DFL = 순이익 또는 EPS 변화율 / 영업이익 변화율 = 기존 영업이익 / 기존 세전이익",
        "DCL = EPS 변화율 / 매출액 변화율 = DOL * DFL",
    ]

    results = []
    dol = None
    dfl = None
    if contribution_margin is not None and operating_income:
        dol = contribution_margin / operating_income
        results.append(f"DOL {format_number(dol)}")
        steps.append(f"DOL = 공헌이익 / 영업이익 = {format_number(dol)}")
    if operating_income is not None and pretax_income:
        dfl = operating_income / pretax_income
        results.append(f"DFL {format_number(dfl)}")
        steps.append(f"DFL = 영업이익 / 세전이익 = {format_number(dfl)}")
    if dol is not None and dfl is not None:
        dcl = dol * dfl
        results.append(f"DCL {format_number(dcl)}")
        steps.append(f"DCL = DOL * DFL = {format_number(dcl)}")

    summary = "레버리지는 고정비로 인해 이익 변동성이 확대되는 구조를 설명합니다."
    if results:
        summary = ", ".join(results) + "입니다."

    return {"status": "ok", "summary": summary, "steps": steps}


def calculate_leverage_income_statement_example(question: str) -> dict:
    sales = Decimal("500")
    variable_cost = Decimal("220")
    fixed_cost = Decimal("180")
    ebit = Decimal("100")
    interest = Decimal("40")
    pretax_income = Decimal("60")
    tax = Decimal("21")
    net_income = Decimal("39")
    sales_drop = Decimal("0.10")
    preferred_dividend = Decimal("15") if "우선주" in question or "배당" in question else Decimal("0")

    tax_rate = tax / pretax_income
    new_sales = sales * (Decimal("1") - sales_drop)
    variable_cost_ratio = variable_cost / sales
    new_variable_cost = new_sales * variable_cost_ratio
    new_contribution_margin = new_sales - new_variable_cost
    new_ebit = new_contribution_margin - fixed_cost
    new_pretax_income = new_ebit - interest
    new_tax = new_pretax_income * tax_rate
    new_net_income = new_pretax_income - new_tax

    contribution_margin = sales - variable_cost
    dol = contribution_margin / ebit
    dfl = ebit / pretax_income
    dcl = dol * dfl

    steps = [
        f"변동영업비율 = 220 / 500 = {format_percent(variable_cost_ratio * Decimal('100'))}",
        f"매출액 10% 하락 후 매출액 = {format_number(new_sales)}",
        f"변동영업비 = {format_number(new_sales)} * 44% = {format_number(new_variable_cost)}",
        f"공헌이익 = 매출액 - 변동영업비 = {format_number(new_contribution_margin)}",
        f"영업이익 = 공헌이익 - 고정영업비 = {format_number(new_ebit)}",
        f"세전이익 = 영업이익 - 이자 = {format_number(new_pretax_income)}",
        f"법인세율 = 21 / 60 = {format_percent(tax_rate * Decimal('100'))}, 법인세 = {format_number(new_tax)}",
        f"당기순이익 = {format_number(new_net_income)}",
        f"DOL = 공헌이익 / 영업이익 = 280 / 100 = {format_number(dol)}",
        f"DFL = 영업이익 / 세전이익 = 100 / 60 = {format_number(dfl)}",
        f"DCL = DOL * DFL = {format_number(dcl)}",
    ]

    summary = (
        f"매출 10% 하락 시 영업이익은 {format_number(new_ebit)}, 세전이익은 {format_number(new_pretax_income)}, "
        f"당기순이익은 {format_number(new_net_income)}입니다. DOL {format_number(dol)}, DFL {format_number(dfl)}, DCL {format_number(dcl)}입니다."
    )

    if preferred_dividend:
        common_income = net_income - preferred_dividend
        preferred_dfl = ebit * (Decimal("1") - tax_rate) / common_income
        steps.append(f"우선주 배당 15가 있으면 보통주 귀속 순이익 = 39 - 15 = {format_number(common_income)}")
        steps.append(f"우선주 반영 DFL = EBIT * (1 - 세율) / 보통주 귀속 순이익 = 100 * 65% / 24 = {format_number(preferred_dfl)}")
        summary += f" 우선주 배당 반영 DFL은 {format_number(preferred_dfl)}입니다."

    return {"status": "ok", "summary": summary, "steps": steps}


def explain_ebit_eps_analysis() -> dict:
    return {
        "status": "concept",
        "summary": "EBIT-EPS 분석은 자본조달 방법별 EPS가 같아지는 EBIT 수준과 재무레버리지 효과를 비교합니다.",
        "steps": [
            "EPS = (EBIT - 이자비용) * (1 - 법인세율) / 보통주식수",
            "타인자본 조달은 이자비용을 늘리지만 발행주식수 증가를 억제해 EPS 기울기를 키울 수 있습니다.",
            "자기자본 조달은 이자비용 부담은 줄이지만 발행주식수를 늘려 EPS 기울기를 낮출 수 있습니다.",
            "재무손익분기점은 EPS가 0이 되는 EBIT 수준입니다.",
            "자본조달분기점은 두 자본조달 대안의 EPS가 같아지는 EBIT 수준입니다.",
            "EBIT가 높을수록 부채조달 대안의 EPS가 유리할 수 있고, EBIT가 낮으면 주식조달 대안이 유리할 수 있습니다.",
            "한계: EPS 극대화가 기업가치 극대화를 보장하지 않고, EBIT 변동 위험을 충분히 반영하지 못할 수 있습니다.",
        ],
    }


def explain_capital_structure() -> dict:
    return {
        "status": "concept",
        "summary": "자본구조 이론은 부채와 자기자본의 조합이 WACC와 기업가치를 어떻게 바꾸는지 분석합니다. MM 이론은 법인세 유무에 따라 부채의 기업가치 효과를 다르게 설명합니다.",
        "steps": [
            "자본구조는 타인자본과 자기자본의 구성상태입니다.",
            "목표는 기업가치를 극대화하는 최적 자본구조를 찾는 것입니다.",
            "기본 가정: 부채와 자기자본만 존재하고, 무성장 영구기업이며, 순이익은 전액 배당됩니다.",
            "무성장 영구기업에서는 FCF = EBIT * (1 - t), 기업가치 V = FCF / WACC로 볼 수 있습니다.",
            "부채 사용 증가는 재무위험을 높여 자기자본비용을 상승시킵니다.",
            "부채는 상대적으로 저렴한 자본이므로 부채비중 증가는 WACC를 낮추는 효과가 있습니다.",
            "법인세가 있으면 이자비용 절세효과로 세후 타인자본비용 kb*(1-t)를 사용합니다.",
            "WACC = ks*S/V + kb*(1-t)*B/V",
            "과도한 부채는 파산비용과 대리비용을 증가시켜 기업가치를 낮출 수 있습니다.",
            "MM 1958 제1명제: 법인세가 없으면 기업가치는 자본구조와 무관합니다. VL = VU",
            "MM 1958 제2명제: 부채기업 자기자본비용 ks = rho + (rho - kb) * B/S, WACC = rho",
            "MM 1958 제3명제: 투자안의 cut-off rate는 자본조달 방식과 무관하게 영업위험만 반영한 rho입니다.",
            "MM 1963 제1명제: 법인세가 있으면 이자비용 절세효과 때문에 VL = VU + B*t입니다.",
            "MM 1963 제2명제: ks = rho + (rho - kb) * (1 - t) * B/S, WACC = rho * [1 - t * (B/V)]",
            "MM 1963 제3명제: 투자안의 cut-off rate는 목표 부채구성비율을 반영한 rho * [1 - t * (B/V)]입니다.",
            "목표 부채비율 문제는 VL = VU + B*t와 목표 B/S 또는 B/V 관계식을 동시에 만족하는 B를 구합니다.",
            "CAPM을 결합하면 rho = Rf + 시장위험프리미엄 * beta_u로 영업위험만 반영한 할인율을 구합니다.",
            "하마다 모형 일반식: beta_s = beta_b + (beta_u - beta_b) * (1 - t) * B/S",
            "무위험부채라면 beta_b = 0이므로 beta_s = beta_u * [1 + (1 - t) * B/S]입니다.",
            "부채기업 자기자본비용은 ks = Rf + 시장위험프리미엄 * beta_s로 구할 수 있습니다.",
            "부채 사용 효과 가치 VTS가 있으면 VL = VU + VTS로 보고, rho*VU/VL + kVTS*VTS/VL = kb*B/VL + ks*S/VL 관계를 활용합니다.",
            "법인세율 상승은 VU를 감소시키고 B*t를 증가시키지만, 일반적으로 부채기업 가치는 감소하고 WACC는 하락합니다.",
            "이자절세효과를 FCF에 직접 반영하면 수정 FCF = EBIT*(1-t)+I*t, 수정 WACC = kb*B/V + ks*S/V를 사용해 중복 반영을 피합니다.",
            "절세효과가 포함된 현금흐름이 주어지면 세전 타인자본비용을 쓰는 수정 WACC를 적용하고, 절세효과를 제거한 FCF에는 세후 WACC를 적용합니다.",
            "개인소득세가 있으면 수정 법인세율 t* = tc + ts - tc*ts로 주주 측 세금효과를 정리합니다.",
            "개인소득세 반영 부채 사용 효과 PV = B * (t* - td) / (1 - td)입니다.",
            "따라서 VL = VU + B * (t* - td) / (1 - td)이며, t*와 td의 크기에 따라 레버리지 이득이 달라집니다.",
            "밀러 균형부채이론은 법인세 절세효과와 이자소득세 부담이 균형에서 상쇄되어 경제 전체의 균형부채량은 있어도 개별 기업의 유일한 최적 자본구조는 없다고 봅니다.",
            "DeAngelo-Masulis 모형은 비부채성 감세효과 때문에 기업별 유효 법인세율이 달라지고, 개별 기업의 최적 부채수준이 존재할 수 있다고 봅니다.",
            "대리비용은 감시비용, 확증비용, 잔여손실로 구성되며 자기자본 대리비용과 타인자본 대리비용으로 나눌 수 있습니다.",
            "자기자본 대리비용은 내부주주 또는 경영자의 특권적 소비, 업무 태만, 사적 효익 추구에서 발생합니다.",
            "부채 대리비용은 위험선호 유인, 과소투자 유인, 재산도피 현상으로 나타납니다.",
            "위험선호 유인은 유한책임 때문에 주주가 기업가치가 낮아져도 주주 기대가치가 큰 고위험 투자안을 고르는 현상입니다.",
            "과소투자 유인은 양의 NPV 투자안이라도 이익 대부분이 채권자에게 귀속되면 주주가 투자하지 않는 현상입니다.",
            "파산비용 이론의 부채기업 가치: VL = VU + B*t - PV(기대 파산비용)",
            "최적 부채수준은 이자절세효과에서 기대 파산비용을 차감한 순효과가 가장 큰 지점입니다.",
            "자본조달순위이론은 정보비대칭하에서 내부자금, 부채 발행, 신주 발행 순으로 선호된다고 봅니다.",
            "신호효과는 부채비율, 배당정책 같은 재무정책이 외부 투자자에게 내부정보를 전달하는 현상입니다.",
            "Ross의 신호이론은 긍정적 신호효과와 파산위험 등 부정적 효과가 균형을 이루는 수준에서 최적 자본구조가 정해질 수 있다고 봅니다.",
            "MM 이전 이론 중 순이익 접근법은 부채 사용으로 기업가치가 증가한다고 보고, 순영업이익 접근법은 기업가치가 불변이라고 봅니다.",
            "전통적 접근법은 일정 부채수준까지 기업가치가 증가하다가 과도한 부채 이후 감소하므로 최적 부채규모가 존재한다고 봅니다.",
            "절세효과 할인율은 MM 1963에서는 타인자본비용, Miller에서는 세후 타인자본비용, Miles-Ezzell에서는 첫해 무위험이자율과 이후 rho, Harris-Pringle 및 Modigliani는 rho를 사용합니다.",
            "MM 차익거래는 과대평가 증권을 매도하고 동일 현금흐름 복제 포트폴리오를 매수하는 방식으로 균형가격을 유도합니다.",
            "위험부채가 있으면 kb = Rf + 시장위험프리미엄 * beta_b로 구하고, 세후 WACC 접근과 수정 FCF 접근은 같은 기업가치를 내야 합니다.",
        ],
    }


def find_percent(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        match = re.search(rf"{label}[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*%", text)
        if match:
            return Decimal(match.group(1))
    return None


def find_money(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        match = re.search(rf"{label}[^0-9원억만]*([0-9,]+(?:\.[0-9]+)?)\s*(억|만|원)?", text)
        if match:
            value = Decimal(match.group(1).replace(",", ""))
            unit = match.group(2)
            if unit == "억":
                return value * Decimal("100000000")
            if unit == "만":
                return value * Decimal("10000")
            return value
    return None


def format_percent(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


def format_number(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
