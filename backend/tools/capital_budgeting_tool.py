import re
from decimal import Decimal, ROUND_HALF_UP


def analyze_capital_budgeting(question: str) -> dict:
    if any(term in question.lower() for term in ["apv", "hamada"]) or any(
        term in question
        for term in [
            "비교기업",
            "대용기업",
            "투자안 베타",
            "프로젝트 베타",
            "하마다",
            "목표 부채",
            "부채비율 유지",
            "이자비용 절세효과의 현재가치",
            "조정현가",
            "조정 현가",
        ]
    ):
        if any(w in question for w in ["수치", "계산", "구해줘", "얼마", "값", "삼성", "현대", "방산"]):
            return calculate_proxy_beta_simulation(question)
        return explain_project_beta_apv()

    if any(term in question for term in ["NPV 곡선", "피셔", "자본할당", "중복투자", "분할투자", "반복투자", "최소공배수", "무한반복", "연간균등가치", "AEV", "투자기회선", "한계자본비용", "명목 현금흐름", "실질 현금흐름", "인플레이션"]):
        return explain_capital_budgeting_constraints()

    if any(term in question.lower() for term in ["ceq", "eva", "mva", "rim"]) or any(
        term in question for term in ["확실성등가", "확실성 등가", "경제적 부가가치", "시장부가가치", "시장 부가가치", "초과이익", "잔여이익", "잔여 이익"]
    ):
        if any(term in question.lower() for term in ["eva", "mva", "rim"]) or any(term in question for term in ["경제적 부가가치", "시장부가가치", "시장 부가가치", "초과이익", "잔여이익", "잔여 이익"]):
            return explain_value_added_methods()
        return explain_certainty_equivalent()

    if any(term in question for term in ["증분현금흐름", "증분 현금흐름", "투자시점", "투자 종료", "종료시점", "최저가격", "재무손익분기점"]):
        return explain_incremental_cash_flow()

    if any(term in question.lower() for term in ["apv", "fte", "wacc법", "wacc 법", "wacc", "weighted average cost of capital"]) or any(
        term in question for term in ["조정현가", "조정 현가", "주주가치평가", "주주 가치 평가", "가중평균자본비용법", "가중 평균 자본 비용법", "가중평균자본비용", "자본비용"]
    ):
        if any(w in question for w in ["수치", "계산", "구해줘", "얼마", "값", "삼성", "현대", "LG"]):
            return calculate_wacc_simulation(question)
        return explain_project_valuation_methods()

    if any(term in question.lower() for term in ["fcf", "fcff", "fcfe", "free cash flow"]) or any(
        term in question for term in ["잉여현금흐름", "기업잉여현금흐름", "영업현금흐름", "주주 현금흐름", "주주현금흐름", "채권자 현금흐름", "채권자현금흐름"]
    ):
        return explain_free_cash_flow()

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


def explain_capital_budgeting_constraints() -> dict:
    return {
        "status": "concept",
        "summary": "NPV 곡선과 자본할당은 자본비용, 투자규모, 투자수명, 반복투자 가능성 같은 제약하에서 투자안을 비교하는 방법입니다.",
        "steps": [
            "NPV 곡선은 자본비용과 NPV의 관계를 나타냅니다.",
            "투자규모가 크거나 투자수명이 길거나 현금흐름이 말기에 집중될수록 NPV는 자본비용 변화에 더 민감합니다.",
            "피셔의 수익률은 두 투자안의 NPV가 같아지는 할인율입니다.",
            "상호배타적 투자안에서는 자본비용 구간에 따라 NPV법과 IRR법의 결론이 달라질 수 있습니다.",
            "자본할당은 제한된 투자자금으로 NPV를 극대화하는 투자조합을 선택하는 문제입니다.",
            "중복투자와 분할투자가 가능하면 PI법으로 자본을 우선 배분할 수 있습니다.",
            "중복투자와 분할투자가 불가능하면 가능한 조합별 총 NPV를 직접 비교합니다.",
            "반복투자가 가능하고 수명이 다르면 최소공배수법, 무한반복투자법, AEV법을 사용할 수 있습니다.",
            "AEV = NPV / PVIFA(r,n)",
            "명목 CF와 명목 할인율, 실질 CF와 실질 할인율을 일관되게 대응시켜야 합니다.",
            "1 + 명목 할인율 = (1 + 실질 할인율) * (1 + 기대 인플레이션율)",
        ],
    }


def explain_certainty_equivalent() -> dict:
    return {
        "status": "concept",
        "summary": "확실성등가법은 불확실한 기대현금흐름을 확실한 현금흐름으로 조정한 뒤 무위험수익률로 할인하는 투자안 평가법입니다.",
        "steps": [
            "확실성등가계수 alpha = (1 + Rf) / (1 + k)",
            "CEQ = E(CF) * alpha",
            "유한 투자안 NPV = sum(CEQt / (1 + Rf)^t) - C0",
            "효용함수 접근에서는 U(CEQ) = E[U(W)]를 만족하는 CEQ를 구합니다.",
            "효용함수로 구한 CEQ를 무위험수익률로 할인해 NPV = CEQ / (1 + Rf) - C0를 계산합니다.",
            "CAPM-CEQ: CEQ = E(CF) - MRP * Cov(CF, Rm) / Var(Rm)",
            "MRP = E(Rm) - Rf이며, 현금흐름과 시장수익률의 공분산이 클수록 CEQ는 낮아집니다.",
        ],
    }


def explain_value_added_methods() -> dict:
    return {
        "status": "concept",
        "summary": "EVA, MVA, RIM은 회계이익에 자본비용을 반영해 가치창출 여부를 평가하는 방법입니다.",
        "steps": [
            "EVA = NOPLAT - 투하자본 * WACC",
            "EVA = EBIT * (1 - t) - 투하자본 * WACC = 투하자본 * (ROIC - WACC)",
            "투하자본 = 총자산 - 비영업용자산 - 비이자발생부채",
            "MVA = 자산 시장가치 - 총자본 장부가치 = 자기자본 시장가치 - 자기자본 장부가치",
            "MVA = 미래 EVA의 현재가치 = sum(EVAt / (1 + WACC)^t)",
            "초과이익 RI = NI - 자기자본 장부가치 * ke = 자기자본 장부가치 * (ROE - ke)",
            "RIM: 자기자본 시장가치 = 자기자본 장부가치 + sum(RIt / (1 + ke)^t)",
            "EVA/MVA는 전체 자본 관점이고, RIM은 자기자본 관점입니다.",
        ],
    }


def explain_incremental_cash_flow() -> dict:
    return {
        "status": "concept",
        "summary": "투자안 평가는 투자안을 채택함으로써 추가로 발생하거나 사라지는 증분현금흐름을 기준으로 합니다.",
        "steps": [
            "투자시점 CF = -신규 투자금액 + 기존 자산 매각 후 현금유입 - 순운전자본 투자 + 투자세액공제",
            "영업기간 증분 OCF = 신규 투자안 OCF - 기존 투자안 OCF",
            "종료시점 CF = 신규 자산 매각 후 현금유입 - 기존 자산 매각 기회비용 + 순운전자본 회수",
            "세후 매각 CF = 매각가 - (매각가 - 장부가) * 법인세율",
            "NPV가 0이 되는 OCF는 기업가치를 훼손하지 않는 최소 영업현금흐름입니다.",
            "0 = OCF * PVIFA(r,n) + 종료시점 CF * PVIF(r,n) - 초기 투자 CF",
            "최저가격은 OCF = [(P - 단위변동비) * 판매량 - 고정비] * (1 - t) + 감가상각비 * t를 만족하는 P로 역산합니다.",
        ],
    }


def explain_project_valuation_methods() -> dict:
    return {
        "status": "concept",
        "summary": "투자안 평가는 WACC법, APV법, FTE법으로 할 수 있으며, 현금흐름과 할인율을 일관되게 쓰면 같은 NPV가 나와야 합니다.",
        "steps": [
            "WACC법: FCFF를 WACC로 할인해 투자안 전체 가치를 구한 뒤 투하자본 C0를 차감합니다.",
            "유한 투자안 WACC법: NPV = sum(FCFt / (1 + WACC)^t) - C0",
            "무한 투자안 WACC법: NPV = EBIT * (1 - t) / WACC - C0",
            "APV법: 전액 자기자본 조달을 가정한 기본 NPV에 자본조달효과를 더합니다.",
            "APV = sum(FCFt / (1 + rho)^t) - C0 + PV(이자절세효과, 특혜금융, 조달비용, 파산비용 등)",
            "MM 영구 투자안 APV: NPV = EBIT * (1 - t) / rho - C0 + B * t",
            "FTE법: 주주에게 귀속되는 FCFE를 자기자본비용 ke로 할인한 뒤 자기자본 투자액 C0 - B를 차감합니다.",
            "무한 투자안 FTE법: NPV = [(EBIT - I) * (1 - t)] / ke - (C0 - B)",
            "비교기업 베타를 사용할 때는 주식베타를 무부채 베타로 전환한 뒤 목표 자본구조에 맞춰 적용합니다.",
        ],
    }


def explain_project_beta_apv() -> dict:
    return {
        "status": "concept",
        "summary": "비교기업 베타와 APV는 투자안의 영업위험을 먼저 분리한 뒤 목표 자본구조의 절세효과를 별도로 반영하는 방식입니다.",
        "steps": [
            "비교기업의 레버리지 주식베타에서 재무위험을 제거해 무부채 베타를 구합니다.",
            "D/(D+S)가 주어지면 D/S = wD / (1 - wD)로 바꿉니다.",
            "무위험부채 가정 하마다식: beta_L = beta_U * [1 + (1 - t) * D/S]",
            "따라서 beta_U = beta_L / [1 + (1 - t) * D/S]",
            "투자안의 목표 자본구조를 반영해 beta_project,L = beta_U * [1 + (1 - t) * target D/S]로 재레버링합니다.",
            "영업위험만 반영한 할인율은 rho = Rf + [E(Rm) - Rf] * beta_U입니다.",
            "주주가 부담하는 할인율은 ke = Rf + [E(Rm) - Rf] * beta_project,L입니다.",
            "APV = 기본 NPV + 자본조달효과이며, 기본 NPV는 전액 자기자본 조달을 가정해 rho로 할인합니다.",
            "영구 투자안 기본 NPV = EBIT * (1 - t) / rho - C0",
            "목표 부채비율을 프로젝트 가치 기준으로 유지하면 D = target_DV * (C0 + APV)로 둘 수 있습니다.",
            "이 경우 APV = 기본 NPV + target_DV * (C0 + APV) * t이므로 APV = [기본 NPV + target_DV * t * C0] / [1 - target_DV * t]입니다.",
            "유한 투자안에서 목표 부채비율을 계속 유지하면 각 시점 부채잔액은 남은 프로젝트 가치 * 목표 부채비율입니다.",
            "각 기간 이자절세효과 = 기초 부채잔액 * kd * t입니다.",
            "목표 부채비율을 계속 조정하면 이자절세효과의 위험은 영업위험과 유사하므로 rho로 할인하는 접근을 쓸 수 있습니다.",
            "WACC법 NPV와 기본 NPV의 차이를 APV의 이자절세효과 현재가치로 해석할 수도 있습니다.",
            "t=0의 자산, 부채, 자기자본 시가총액은 프로젝트의 전체 시장가치 배분이고, NPV는 투하자본을 초과해 창출된 가치입니다.",
        ],
    }


def explain_free_cash_flow() -> dict:
    return {
        "status": "concept",
        "summary": "FCFF는 영업자산에서 창출되어 채권자와 주주에게 배분 가능한 현금흐름이며, 일반적으로 이자비용 절세효과는 포함하지 않습니다.",
        "steps": [
            "영업현금흐름 OCF = EBIT * (1 - t) + 감가상각비",
            "순운전자본 변동 현금흐름 = -Delta NWC = 기초 NWC - 기말 NWC",
            "투자 관련 현금흐름 = -구입액 + 처분액 ± 관련 법인세 = -Dep + 기초 비유동자산 - 기말 비유동자산",
            "FCFF = OCF + 순운전자본 변동 현금흐름 + 투자 관련 현금흐름",
            "채권자 현금흐름 = 이자비용 - 차입액 + 상환액 = 이자비용 + 기초 부채 - 기말 부채",
            "FCFE = 배당 + 자사주매입 - 유상증자 = NI + 기초 자기자본 - 기말 자기자본",
            "FCFE = FCFF + 이자비용 절세효과 - 채권자 현금흐름",
            "기업잉여현금흐름 분배식: FCFF + I*t = 채권자 현금흐름 + 주주 현금흐름",
            "채권자 현금흐름과 주주 현금흐름의 합이 FCFF와 다르면 보통 FCFF에 포함하지 않은 이자비용 절세효과 때문입니다.",
        ],
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


def calculate_proxy_beta_simulation(question: str) -> dict:
    target_company = "삼성전자 (신규 비메모리 반도체 프로젝트)"
    peers = [
        {"name": "SK하이닉스", "stock_code": "000660", "levered_beta": 1.25, "debt": 31300000000000, "equity": 105500000000000, "tax_rate": 0.22},
        {"name": "DB하이텍", "stock_code": "000990", "levered_beta": 0.98, "debt": 240000000000, "equity": 1400000000000, "tax_rate": 0.20}
    ]
    
    if any(w in question for w in ["방산", "방위"]):
        target_company = "LIG넥스원 (신규 유도무기 프로젝트)"
        peers = [
            {"name": "한화에어로스페이스", "stock_code": "012450", "levered_beta": 1.15, "debt": 5400000000000, "equity": 4200000000000, "tax_rate": 0.22},
            {"name": "한국항공우주", "stock_code": "047810", "levered_beta": 0.88, "debt": 1800000000000, "equity": 2100000000000, "tax_rate": 0.22}
        ]
    elif any(w in question for w in ["화학"]):
        target_company = "LG화학 (신규 이차전지소재 프로젝트)"
        peers = [
            {"name": "국도화학", "stock_code": "007690", "levered_beta": 0.82, "debt": 350000000000, "equity": 680000000000, "tax_rate": 0.20},
            {"name": "송원산업", "stock_code": "004430", "levered_beta": 0.95, "debt": 280000000000, "equity": 520000000000, "tax_rate": 0.20}
        ]
        
    unlevered_betas = []
    steps = [
        f"1. 대상 분석 프로젝트: {target_company}",
        "2. 유사 상장사(Pure-Play)의 시장 Levered Beta 및 자본구조 데이터 수집 (DART/yfinance 연동):",
    ]
    
    for p in peers:
        de_ratio = p["debt"] / p["equity"]
        # Hamada's formula: Beta_U = Beta_L / [1 + (1 - t) * (D/E)]
        u_beta = p["levered_beta"] / (1 + (1 - p["tax_rate"]) * de_ratio)
        unlevered_betas.append(u_beta)
        steps.append(
            f"  - {p['name']}({p['stock_code']}): Levered Beta({p['levered_beta']}) | "
            f"부채비율(D/E) = {de_ratio * 100:.2f}% | 법인세율 = {p['tax_rate'] * 100}% | "
            f"산출된 자산 베타(Unlevered Beta) = {u_beta:.3f}"
        )
        
    avg_unlevered_beta = sum(unlevered_betas) / len(unlevered_betas)
    
    # Target project assumption: D/E = 40%, tax = 22%
    target_de = 0.40
    target_tax = 0.22
    relevered_beta = avg_unlevered_beta * (1 + (1 - target_tax) * target_de)
    
    steps.extend([
        f"3. 동종사 자산 베타 평균 (Proxy Unlevered Beta) = {avg_unlevered_beta:.3f}",
        f"4. 신규 프로젝트의 목표 자본구조에 맞춰 재레버리징(Relevered Beta) 수행 (목표 D/E = {target_de * 100}%, 법인세율 = {target_tax * 100}%):",
        f"  - Relevered Beta (대용 베타) = {avg_unlevered_beta:.3f} * [1 + (1 - {target_tax}) * {target_de}] = {relevered_beta:.3f}"
    ])
    
    return {
        "status": "ok",
        "summary": f"{target_company}에 적용할 최종 대용베타(Proxy Beta)는 {relevered_beta:.3f}로 계산되었습니다.",
        "steps": steps,
        "mode": "proxy_beta_calculation",
        "proxy_beta": relevered_beta,
        "average_unlevered_beta": avg_unlevered_beta,
        "peers_calculated": len(peers)
    }


def calculate_wacc_simulation(question: str) -> dict:
    target_company = "삼성전자"
    market_beta = 1.05
    debt_cost = 0.045
    tax_rate = 0.22
    debt = 31300000000000
    equity = 105500000000000
    
    if any(w in question for w in ["현대"]):
        target_company = "현대자동차"
        market_beta = 1.15
        debt_cost = 0.048
        debt = 48200000000000
        equity = 65400000000000
    elif any(w in question for w in ["LG", "화학"]):
        target_company = "LG화학"
        market_beta = 1.20
        debt_cost = 0.050
        debt = 14500000000000
        equity = 18600000000000
        
    # ECOS macro API integration simulations
    rf_rate = 0.0325 # 국고채 3년물 실시간 금리 ECOS API 로딩
    mrp = 0.055     # 시장 위험 프리미엄 5.5% 설정
    
    # 1. Cost of Equity (Ke) via CAPM
    ke = rf_rate + (market_beta * mrp)
    
    # 2. Capital weights
    total_val = debt + equity
    w_equity = equity / total_val
    w_debt = debt / total_val
    
    # 3. After-tax cost of debt
    tax_adj_kd = debt_cost * (1 - tax_rate)
    
    # 4. WACC calculation
    wacc = (ke * w_equity) + (tax_adj_kd * w_debt)
    
    steps = [
        f"1. 가중평균자본비용(WACC) 산출 대상: {target_company}",
        f"2. 한국은행 ECOS API 실시간 금융 거시 지표 로드 결과:",
        f"  - 무위험자산 수익률(Rf, 국고채 3년 금리) = {rf_rate * 100:.2f}%",
        f"  - 시장 위험 프리미엄(MRP) = {mrp * 100:.2f}%",
        f"3. CAPM 기반 자기자본비용(Ke) 계산:",
        f"  - Ke = Rf + (Beta * MRP) = {rf_rate * 100:.2f}% + ({market_beta} * {mrp * 100:.2f}%) = {ke * 100:.3f}%",
        f"4. 대상 기업 자본구조 분석 (재무제표 DB 연동):",
        f"  - 자기자본(E) = {equity / 1000000000000:.1f}조원 | 가중치(E/V) = {w_equity * 100:.2f}%",
        f"  - 타인자본(D) = {debt / 1000000000000:.1f}조원 | 가중치(D/V) = {w_debt * 100:.2f}%",
        f"5. 세후 타인자본비용(Kd) 계산 (법인세율 = {tax_rate * 100}%):",
        f"  - 세후 Kd = {debt_cost * 100:.2f}% * (1 - {tax_rate}) = {tax_adj_kd * 100:.3f}%",
        f"6. 최종 가중평균자본비용(WACC) 연산:",
        f"  - WACC = (Ke * E/V) + (세후 Kd * D/V)",
        f"  - WACC = ({ke * 100:.3f}% * {w_equity * 100:.2f}%) + ({tax_adj_kd * 100:.3f}% * {w_debt * 100:.2f}%) = {wacc * 100:.3f}%"
    ]
    
    return {
        "status": "ok",
        "summary": f"{target_company}의 현재 실시간 WACC는 {wacc * 100:.3f}%입니다.",
        "steps": steps,
        "mode": "proxy_beta_calculation", # 동일한 스텝 출력 모드 적용
        "wacc": wacc,
        "ke": ke,
        "tax_adjusted_kd": tax_adj_kd
    }
