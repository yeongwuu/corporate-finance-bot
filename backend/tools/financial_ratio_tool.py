import re
from decimal import Decimal, ROUND_HALF_UP


def analyze_financial_ratios(question: str) -> dict:
    growth_result = calculate_growth_policy(question)
    if growth_result["status"] == "ok":
        return growth_result

    ratios = []
    steps = []

    add_liquidity_ratios(question, ratios, steps)
    add_stability_ratios(question, ratios, steps)
    add_profitability_ratios(question, ratios, steps)
    add_activity_ratios(question, ratios, steps)

    if ratios:
        return {"status": "ok", "summary": ", ".join(ratios) + "입니다.", "steps": steps}

    return {
        "status": "need_more_data",
        "summary": "재무비율 계산에는 유동자산, 유동부채, 부채, 자기자본, 매출액, 평균자산 등 필요한 항목이 필요합니다.",
        "steps": [],
    }


def calculate_growth_policy(question: str) -> dict:
    debt_ratio = find_percent(question, ["부채비율"])
    retention = find_percent(question, ["내부 유보율", "유보율"])
    beginning_equity = find_money(question, ["올해 초 자기자본", "기초 자기자본", "자기자본"])
    current_net_income = find_money(question, ["올해 순이익", "순이익"])

    if None in [debt_ratio, retention, beginning_equity, current_net_income]:
        return {"status": "no_calculation", "summary": "", "steps": []}

    debt_to_equity = debt_ratio / Decimal("100")
    retention_rate = retention / Decimal("100")
    beginning_debt = beginning_equity * debt_to_equity
    beginning_assets = beginning_equity + beginning_debt
    ending_equity = beginning_equity + current_net_income * retention_rate
    ending_debt = ending_equity * debt_to_equity
    ending_assets = ending_equity + ending_debt
    avg_equity = (beginning_equity + ending_equity) / Decimal("2")
    avg_assets = (beginning_assets + ending_assets) / Decimal("2")
    roa = current_net_income / avg_assets * Decimal("100")
    roe = current_net_income / avg_equity * Decimal("100")

    steps = [
        f"기초 부채 = 기초 자기자본 * 부채비율 = {format_money(beginning_debt)}",
        f"기초 총자산 = 기초 부채 + 기초 자기자본 = {format_money(beginning_assets)}",
        f"기말 자기자본 = 기초 자기자본 + 순이익 * 유보율 = {format_money(ending_equity)}",
        f"기말 부채 = 기말 자기자본 * 부채비율 = {format_money(ending_debt)}",
        f"기말 총자산 = {format_money(ending_assets)}",
        f"ROA = 순이익 / 평균총자산 = {format_percent(roa)}",
        f"ROE = 순이익 / 평균자기자본 = {format_percent(roe)}",
    ]
    summary_parts = [f"ROA는 {format_percent(roa)}", f"ROE는 {format_percent(roe)}"]

    if "20%" in question and ("내부자금" in question or "차입" in question):
        next_income = current_net_income * Decimal("1.2")
        next_beginning_equity = ending_equity
        next_beginning_debt = ending_debt
        next_beginning_assets = ending_assets
        next_ending_equity = next_beginning_equity + next_income
        next_ending_assets = next_beginning_debt + next_ending_equity
        asset_growth = (next_ending_assets / next_beginning_assets - Decimal("1")) * Decimal("100")
        summary_parts.append(f"내부자금만 사용할 때 최대 총자산성장률은 {format_percent(asset_growth)}")
        steps.extend(
            [
                f"내년 순이익 = 올해 순이익 * 1.2 = {format_money(next_income)}",
                "내부자금만 사용하면 차입이 없으므로 부채는 변하지 않고, 최대 성장을 위해 유보율은 100%로 둡니다.",
                f"내년 말 자기자본 = {format_money(next_ending_equity)}",
                f"내년 말 총자산 = 기존 부채 {format_money(next_beginning_debt)} + 자기자본 {format_money(next_ending_equity)} = {format_money(next_ending_assets)}",
                f"최대 총자산성장률 = {format_money(next_ending_assets)} / {format_money(next_beginning_assets)} - 1 = {format_percent(asset_growth)}",
            ]
        )

    if "50%" in question and ("부채비율" in question or "기존" in question):
        next_income = current_net_income * Decimal("1.5")
        next_beginning_equity = ending_equity
        next_ending_equity = next_beginning_equity + next_income
        equity_growth = (next_ending_equity / next_beginning_equity - Decimal("1")) * Decimal("100")
        next_ending_debt = next_ending_equity * debt_to_equity
        summary_parts.append(f"부채비율 유지 시 최대 자기자본성장률은 {format_percent(equity_growth)}")
        steps.extend(
            [
                f"내년 순이익 = 올해 순이익 * 1.5 = {format_money(next_income)}",
                "유상증자를 사용하지 않고 자기자본을 최대로 만들기 위해 유보율은 100%로 둡니다.",
                f"내년 말 자기자본 = {format_money(next_ending_equity)}",
                f"부채비율 유지 시 내년 말 부채 = {format_money(next_ending_debt)}",
                f"최대 자기자본성장률 = {format_money(next_ending_equity)} / {format_money(next_beginning_equity)} - 1 = {format_percent(equity_growth)}",
            ]
        )

    return {"status": "ok", "summary": ", ".join(summary_parts) + "입니다.", "steps": steps}


def add_liquidity_ratios(question: str, ratios: list[str], steps: list[str]) -> None:
    current_assets = find_money(question, ["유동자산"])
    current_liabilities = find_money(question, ["유동부채"])
    quick_assets = find_money(question, ["당좌자산"])
    cash = find_money(question, ["현금및현금성자산", "현금 및 현금성 자산", "현금성자산", "현금"])
    total_capital = find_money(question, ["총자본"])

    if current_assets is not None and current_liabilities:
        current_ratio = current_assets / current_liabilities * Decimal("100")
        ratios.append(f"유동비율 {format_percent(current_ratio)}")
        steps.append(f"유동비율 = 유동자산 / 유동부채 * 100 = {format_percent(current_ratio)}")

        if total_capital:
            nwc = current_assets - current_liabilities
            nwc_ratio = nwc / total_capital * Decimal("100")
            ratios.append(f"순운전자본비율 {format_percent(nwc_ratio)}")
            steps.append(f"순운전자본비율 = (유동자산 - 유동부채) / 총자본 * 100 = {format_percent(nwc_ratio)}")

    if quick_assets is not None and current_liabilities:
        quick_ratio = quick_assets / current_liabilities * Decimal("100")
        ratios.append(f"당좌비율 {format_percent(quick_ratio)}")
        steps.append(f"당좌비율 = 당좌자산 / 유동부채 * 100 = {format_percent(quick_ratio)}")

    if cash is not None and current_liabilities:
        cash_ratio = cash / current_liabilities * Decimal("100")
        ratios.append(f"현금비율 {format_percent(cash_ratio)}")
        steps.append(f"현금비율 = 현금및현금성자산 / 유동부채 * 100 = {format_percent(cash_ratio)}")


def add_stability_ratios(question: str, ratios: list[str], steps: list[str]) -> None:
    debt = find_money(question, ["타인자본", "부채"])
    equity = find_money(question, ["자기자본", "자본"])
    total_capital = find_money(question, ["총자본"])
    operating_income = find_money(question, ["영업이익"])
    interest_expense = find_money(question, ["이자비용"])
    noncurrent_assets = find_money(question, ["비유동자산", "고정자산"])
    noncurrent_liabilities = find_money(question, ["비유동부채", "고정부채"])

    if debt is not None and equity:
        debt_ratio = debt / equity * Decimal("100")
        ratios.append(f"부채비율 {format_percent(debt_ratio)}")
        steps.append(f"부채비율 = 부채 / 자기자본 * 100 = {format_percent(debt_ratio)}")

    if equity is not None and total_capital:
        equity_ratio = equity / total_capital * Decimal("100")
        ratios.append(f"자기자본비율 {format_percent(equity_ratio)}")
        steps.append(f"자기자본비율 = 자기자본 / 총자본 * 100 = {format_percent(equity_ratio)}")

    if operating_income is not None and interest_expense:
        interest_coverage = operating_income / interest_expense
        ratios.append(f"이자보상비율 {format_number(interest_coverage)}배")
        steps.append(f"이자보상비율 = 영업이익 / 이자비용 = {format_number(interest_coverage)}배")

    if noncurrent_assets is not None and equity:
        fixed_ratio = noncurrent_assets / equity * Decimal("100")
        ratios.append(f"비유동비율 {format_percent(fixed_ratio)}")
        steps.append(f"비유동비율 = 비유동자산 / 자기자본 * 100 = {format_percent(fixed_ratio)}")

    if noncurrent_assets is not None and equity and noncurrent_liabilities is not None:
        long_term_fit = noncurrent_assets / (equity + noncurrent_liabilities) * Decimal("100")
        ratios.append(f"비유동장기적합률 {format_percent(long_term_fit)}")
        steps.append("비유동장기적합률 = 비유동자산 / (자기자본 + 비유동부채) * 100 = " + format_percent(long_term_fit))


def add_profitability_ratios(question: str, ratios: list[str], steps: list[str]) -> None:
    net_income = find_money(question, ["당기순이익", "순이익"])
    gross_profit = find_money(question, ["매출총이익"])
    operating_income = find_money(question, ["영업이익"])
    sales = find_money(question, ["매출액"])
    equity = find_money(question, ["자기자본", "자본"])
    debt = find_money(question, ["타인자본", "부채"])
    total_assets = find_money(question, ["평균총자산", "총자산", "총자본"])

    if gross_profit is not None and sales:
        gross_margin = gross_profit / sales * Decimal("100")
        ratios.append(f"매출액총이익률 {format_percent(gross_margin)}")
        steps.append(f"매출액총이익률 = 매출총이익 / 매출액 * 100 = {format_percent(gross_margin)}")

    if operating_income is not None and sales:
        operating_margin = operating_income / sales * Decimal("100")
        ratios.append(f"매출액영업이익률 {format_percent(operating_margin)}")
        steps.append(f"매출액영업이익률 = 영업이익 / 매출액 * 100 = {format_percent(operating_margin)}")

    if net_income is not None and sales:
        net_margin = net_income / sales * Decimal("100")
        ratios.append(f"매출액순이익률 {format_percent(net_margin)}")
        steps.append(f"매출액순이익률 = 당기순이익 / 매출액 * 100 = {format_percent(net_margin)}")

    if net_income is not None and equity:
        roe = net_income / equity * Decimal("100")
        ratios.append(f"ROE {format_percent(roe)}")
        steps.append(f"ROE = 당기순이익 / 자기자본 * 100 = {format_percent(roe)}")

    if net_income is not None and total_assets:
        roa = net_income / total_assets * Decimal("100")
        ratios.append(f"ROA {format_percent(roa)}")
        steps.append(f"ROA = 당기순이익 / 총자본 또는 총자산 * 100 = {format_percent(roa)}")

    if operating_income is not None and total_assets:
        operating_roa = operating_income / total_assets * Decimal("100")
        ratios.append(f"총자본영업이익률 {format_percent(operating_roa)}")
        steps.append(f"총자본영업이익률 = 영업이익 / 총자본 * 100 = {format_percent(operating_roa)}")

    if net_income is not None and sales and total_assets and debt is not None and equity:
        net_margin = net_income / sales
        total_asset_turnover = sales / total_assets
        debt_ratio = debt / equity
        dupont_roe = net_margin * total_asset_turnover * (Decimal("1") + debt_ratio) * Decimal("100")
        ratios.append(f"듀퐁 ROE {format_percent(dupont_roe)}")
        steps.append("듀퐁 ROE = 매출액순이익률 * 총자산회전율 * (1 + 부채비율) = " + format_percent(dupont_roe))


def add_activity_ratios(question: str, ratios: list[str], steps: list[str]) -> None:
    sales = find_money(question, ["매출액"])
    cost_of_goods_sold = find_money(question, ["매출원가"])
    purchases = find_money(question, ["매입액"])
    avg_receivables = find_money(question, ["평균매출채권", "평균 매출채권"])
    avg_inventory = find_money(question, ["평균재고자산", "평균 재고자산"])
    avg_payables = find_money(question, ["평균매입채무", "평균 매입채무"])
    avg_total_assets = find_money(question, ["평균총자산", "평균 총자산"])

    receivable_days = find_days(question, ["매출채권회수기간", "매출채권 회수기간"])
    inventory_days = find_days(question, ["재고자산회전기간", "재고자산 회전기간"])
    payable_days = find_days(question, ["매입채무지급기간", "매입채무 지급기간"])

    if sales is not None and avg_receivables:
        turnover = sales / avg_receivables
        computed_receivable_days = Decimal("365") / turnover
        receivable_days = receivable_days or computed_receivable_days
        ratios.append(f"매출채권회전율 {format_number(turnover)}회")
        ratios.append(f"매출채권회수기간 {format_days(receivable_days)}")
        steps.append(f"매출채권회전율 = 매출액 / 평균매출채권 = {format_number(turnover)}회")
        steps.append(f"매출채권회수기간 = 365 / 매출채권회전율 = {format_days(receivable_days)}")

    inventory_base = cost_of_goods_sold if cost_of_goods_sold is not None else sales
    inventory_base_name = "매출원가" if cost_of_goods_sold is not None else "매출액"
    if inventory_base is not None and avg_inventory:
        turnover = inventory_base / avg_inventory
        computed_inventory_days = Decimal("365") / turnover
        inventory_days = inventory_days or computed_inventory_days
        ratios.append(f"재고자산회전율 {format_number(turnover)}회")
        ratios.append(f"재고자산회전기간 {format_days(inventory_days)}")
        steps.append(f"재고자산회전율 = {inventory_base_name} / 평균재고자산 = {format_number(turnover)}회")
        steps.append(f"재고자산회전기간 = 365 / 재고자산회전율 = {format_days(inventory_days)}")

    payable_base = purchases if purchases is not None else cost_of_goods_sold
    payable_base_name = "매입액" if purchases is not None else "매출원가"
    if payable_base is not None and avg_payables:
        turnover = payable_base / avg_payables
        computed_payable_days = Decimal("365") / turnover
        payable_days = payable_days or computed_payable_days
        ratios.append(f"매입채무회전율 {format_number(turnover)}회")
        ratios.append(f"매입채무지급기간 {format_days(payable_days)}")
        steps.append(f"매입채무회전율 = {payable_base_name} / 평균매입채무 = {format_number(turnover)}회")
        steps.append(f"매입채무지급기간 = 365 / 매입채무회전율 = {format_days(payable_days)}")

    if receivable_days is not None and inventory_days is not None:
        operating_cycle = receivable_days + inventory_days
        ratios.append(f"영업순환주기 {format_days(operating_cycle)}")
        steps.append(f"영업순환주기 = 재고자산회전기간 + 매출채권회수기간 = {format_days(operating_cycle)}")

        if payable_days is not None:
            cash_conversion_cycle = operating_cycle - payable_days
            ratios.append(f"현금순환주기 {format_days(cash_conversion_cycle)}")
            steps.append(f"현금순환주기 = 영업순환주기 - 매입채무지급기간 = {format_days(cash_conversion_cycle)}")

    if sales is not None and avg_total_assets:
        total_asset_turnover = sales / avg_total_assets
        ratios.append(f"총자산회전율 {format_number(total_asset_turnover)}회")
        steps.append(f"총자산회전율 = 매출액 / 평균총자산 = {format_number(total_asset_turnover)}회")


def find_money(text: str, labels: list[str]) -> Decimal | None:
    for label in sorted(labels, key=len, reverse=True):
        match = re.search(rf"(?<![가-힣]){re.escape(label)}[^0-9￦₩억만원]*[￦₩]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(억|만|원)?", text)
        if match:
            value = Decimal(match.group(1).replace(",", ""))
            unit = match.group(2)
            if unit == "억":
                return value * Decimal("100000000")
            if unit == "만":
                return value * Decimal("10000")
            return value
    return None


def find_percent(text: str, labels: list[str]) -> Decimal | None:
    for label in sorted(labels, key=len, reverse=True):
        match = re.search(rf"(?<![가-힣]){re.escape(label)}[^0-9%]*([0-9]+(?:\.[0-9]+)?)\s*%", text)
        if match:
            return Decimal(match.group(1))
    return None


def find_days(text: str, labels: list[str]) -> Decimal | None:
    for label in sorted(labels, key=len, reverse=True):
        match = re.search(rf"(?<![가-힣]){re.escape(label)}[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*일?", text)
        if match:
            return Decimal(match.group(1))
    return None


def format_percent(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


def format_number(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"


def format_days(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}일"


def format_money(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.2f}"
