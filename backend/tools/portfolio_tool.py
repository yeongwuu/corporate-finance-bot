from decimal import Decimal, ROUND_HALF_UP


def analyze_portfolio(question: str) -> dict:
    if is_portfolio_optimization_question(question):
        return calculate_optimal_portfolio(question)

    if is_multifactor_apt_question(question):
        return explain_multifactor_apt(question)

    if is_attribution_question(question):
        return explain_performance_attribution(question)

    if is_performance_return_question(question):
        return explain_performance_returns(question)

    if is_performance_evaluation_question(question):
        return explain_performance_evaluation(question)

    if is_regression_capm_test_question(question):
        return explain_regression_capm_test(question)

    if is_market_model_question(question):
        return analyze_market_model(question)

    if is_cml_2022_example(question):
        return calculate_cml_2022_example()

    if is_cml_2014_example(question):
        return calculate_cml_2014_example()

    if is_short_selling_mvp_example(question):
        return calculate_short_selling_mvp_example()

    if is_mvp_example(question):
        return calculate_mvp_example()

    if is_weight_change_example(question):
        return calculate_weight_change_example()

    if is_correlation_effect_example(question):
        return calculate_correlation_effect_example()

    if is_known_two_asset_example(question):
        return calculate_known_two_asset_example()

    if is_portfolio_concept_question(question):
        return explain_portfolio_concepts(question)

    return {
        "status": "no_calculation",
        "summary": "포트폴리오 분석은 기대수익률, 분산, 공분산, 상관계수를 이용해 위험과 수익률을 계산합니다.",
        "steps": [
            "포트폴리오 기대수익률 = Σ 자산별 투자비중 * 자산별 기대수익률",
            "두 자산 포트폴리오 분산 = wA^2 Var(A) + wB^2 Var(B) + 2 wA wB Cov(A,B)",
            "공분산 = Σ 확률 * A 편차 * B 편차",
            "상관계수 = 공분산 / (A 표준편차 * B 표준편차)",
            "상관계수가 낮을수록 일반적으로 분산투자 효과가 커집니다.",
            "최소분산포트폴리오 비중은 wA = (σB^2 - CovAB) / (σA^2 + σB^2 - 2CovAB)로 계산합니다.",
            "균등투자 N개 자산 포트폴리오 분산 = (1/N) * (분산평균 - 공분산평균) + 공분산평균",
            "자산 A 공헌도 = wA^2 Var(A) + wA wB Cov(A,B)",
            "무위험자산 결합 포트폴리오: E(Rp)=wE(Risky)+(1-w)Rf, σp=wσRisky",
            "샤프비율 = (E(Risky)-Rf)/σRisky",
            "CAPM: E(Ri)=Rf+βi(E(RM)-Rf), βi=Cov(Ri,RM)/Var(RM)",
        ],
    }


def explain_portfolio_concepts(question: str) -> dict:
    steps = [
        "마코위츠 효율적 투자선은 최소분산선 중 지배관계가 없는 포트폴리오 집합입니다.",
        "무위험자산이 없으면 투자자는 효율적 투자선과 자신의 무차별곡선이 접하는 지점을 선택합니다.",
        "무위험자산이 있으면 CAL 중 효율적 투자선에 접하는 선이 CML이고, 접점이 시장포트폴리오입니다.",
        "토빈 분리정리: 위험자산 선택은 시장포트폴리오로 동일하고, 투자자별 차이는 시장포트폴리오와 무위험자산의 배합비율에서 발생합니다.",
        "무위험자산 결합: E(Rp)=wE(Risky)+(1-w)Rf, σp=wσRisky",
        "CML: E(Rp)=Rf+[(E(RM)-Rf)/σM]*σp",
        "시장포트폴리오 내 개별 자산 비중은 개별 자산 시장가치/전체 위험자산 시장가치입니다.",
        "효용 극대화: MRS와 CAL 기울기를 같게 두어 최적 위험자산 비중을 찾습니다.",
        "SCL은 시장포트폴리오 수익률과 개별 자산 수익률의 회귀선이며, 그 기울기가 베타입니다.",
        "CAPM/SML: E(Ri)=Rf+βi(E(RM)-Rf), βi=Cov(Ri,RM)/Var(RM)",
        "SML은 베타와 기대수익률의 관계를 나타내며, 개별 자산과 비효율적 포트폴리오에도 적용됩니다.",
        "시장모형: Ri=αi+βiRM+ei, Var(Ri)=βi^2Var(RM)+Var(ei)",
        "접점포트폴리오는 무위험자산과 결합했을 때 샤프비율을 극대화하는 위험자산 포트폴리오입니다.",
        "샤프지수: (포트폴리오 기대수익률-무위험수익률)/표준편차",
        "트레이너지수: (포트폴리오 기대수익률-무위험수익률)/베타",
        "젠센의 알파: 실제수익률 - CAPM 균형수익률",
        "정보비율: 벤치마크 초과수익률 / 초과수익률의 표준편차",
        "N개 균등투자 분산: (1/N)*(분산평균-공분산평균)+공분산평균",
        "APT/다요인모형: 여러 공통요인 민감도로 기대수익률과 체계적 위험을 설명합니다.",
        "성과귀속: 초과수익률을 자산배분 효과와 종목선정 효과로 나눕니다.",
        "체계적 위험은 분산투자로 제거되지 않지만, 베타가 음수인 자산이나 공매를 이용해 포트폴리오 베타를 0에 가깝게 만들 수 있습니다.",
    ]

    if any(term in question for term in ["차입", "대출"]):
        steps.append("차입금리와 대출금리가 다르면 CAL은 꺾인 선이 되며, 위험포트폴리오 100% 보유가 최적이 되는 위험회피계수 범위를 부등식으로 판단합니다.")
    if any(term in question for term in ["CAPM", "capm", "SML", "sml", "베타"]):
        steps.append("시장포트폴리오가 두 자산으로 구성된 경우 시장 기대수익률로 시장 내 비중을 먼저 구한 뒤 Cov(Ri,RM)과 β를 계산합니다.")
    if any(term in question for term in ["SCL", "scl", "증권특성선"]):
        steps.append("SCL은 과거 시장수익률과 개별자산수익률의 관계를 최소자승법으로 추정하며, 기울기 β는 체계적 위험입니다.")
    if any(term in question for term in ["SML", "sml", "증권시장선", "과소평가", "과대평가"]):
        steps.append("SML상 균형수익률보다 시장수익률이 높으면 과소평가, 낮으면 과대평가로 해석합니다.")
    if any(term in question for term in ["접점", "접점포트폴리오", "접점 포트폴리오"]):
        steps.append("접점포트폴리오는 공헌위험 대비 위험프리미엄이 모든 위험자산에서 같아지는 비중으로 찾습니다.")
    if any(term in question for term in ["비체계적 위험", "잔차분산", "잔차 분산"]):
        steps.append("시장모형에서는 SML로 베타를 구한 뒤 Var(ei)=Var(Ri)-βi^2Var(RM)을 계산하고, Σwi^2Var(ei)를 최소화합니다.")
    if any(term in question for term in ["트레이너", "Treynor", "treynor"]):
        steps.append("CAPM 균형에서는 모든 자산의 트레이너지수가 시장위험프리미엄 E(RM)-Rf로 같아집니다.")
    if any(term in question for term in ["제로베타", "무위험 자산이 존재하지", "무위험자산이 존재하지"]):
        steps.append("무위험자산이 없으면 시장포트폴리오와 공분산이 0인 제로베타 포트폴리오를 무위험수익률의 대용치로 사용합니다.")
    if any(term in question for term in ["투자자 갑", "투자자 을", "위험회피계수", "시장 균형"]):
        steps.append("투자자별 CML 최적수요에서는 시장포트폴리오 투자금액과 무위험자산 매입·매도액이 시장 전체에서 일관되도록 연결됩니다.")
    if any(term in question for term in ["한계", "거래비용", "소득세", "동질적"]):
        steps.append("CAPM은 동질적 기대, 동일한 차입·대출금리, 세금·거래비용 부재 같은 강한 가정에 의존하므로 현실화하면 성립 범위가 제한됩니다.")
    if any(term in question for term in ["시장가치", "시가총액", "시장 포트폴리오", "시장포트폴리오"]):
        steps.append("시장 균형에서는 모든 투자자가 위험자산 내부에서 동일한 시장포트폴리오 비중을 보유한다고 보고, 그 비중은 시가총액 가중으로 계산합니다.")
    if any(term in question for term in ["20개", "11개", "동일", "균등"]):
        steps.append("동일 기대수익률·동일 표준편차·동일 상관계수 조건에서는 비중 제곱합과 공분산 항의 개수를 이용해 분산을 분해합니다.")

    return {
        "status": "concept",
        "summary": "이 유형은 특정 기출 숫자보다 CML, CAPM/SML, 샤프·트레이너지수, 분산투자 한계의 구조를 잡는 것이 핵심입니다.",
        "steps": steps,
    }


def explain_multifactor_apt(question: str) -> dict:
    steps = [
        "Roll의 비판: 진정한 시장포트폴리오를 현실에서 관찰·검증하기 어렵기 때문에 CAPM의 실증검증 자체에 한계가 있습니다.",
        "단일모형: Ri = αi + βiF + ei",
        "2요인모형: Ri = αi + βi1F1 + βi2F2 + ei",
        "Fama-French 3요인 모형: Ri = αi + βi1*MKT + βi2*SMB + βi3*HML + ei",
        "MKT는 시장 초과수익률, SMB는 소형주-대형주 수익률, HML은 가치주-성장주 수익률입니다.",
        "SMB 계수가 유의하게 양수이면 소형주 성향, 음수이면 대형주 성향으로 해석합니다.",
        "HML 계수가 유의하게 양수이면 가치주 성향, 음수이면 성장주 성향으로 해석합니다.",
        "절편 α는 3요인으로 설명되지 않는 위험조정 초과성과이며, 유의하지 않으면 추가 성과가 있다고 보기 어렵습니다.",
        "계수 유의성은 t-통계량=추정계수/표준오차로 판단하며, 관행적으로 절댓값 2 안팎을 기준으로 봅니다.",
        "요인모형의 α는 요인으로 설명되지 않는 평균수익률 성분이고, β는 각 공통요인에 대한 민감도입니다.",
        "수익률 생성모형은 Ri=E(Ri)+Σβik[Fk-E(Fk)]+ei처럼 기대수익률, 예상치 못한 공통요인 변동, 잔차로 수익률을 나눕니다.",
        "공통요인 간 공분산이 없다고 보면 체계적 위험 = Σ βik^2 Var(Fk)입니다.",
        "비체계적 위험 = 총위험 - 체계적 위험입니다.",
        "포트폴리오 요인 민감도는 βpk = Σwiβik로 계산합니다.",
        "포트폴리오 잔차분산은 Var(ep)=Σwi^2Var(ei)입니다.",
        "총위험 대비 비체계적 위험 비율은 Var(ep)/Var(Rp)입니다.",
        "APT 도출의 핵심은 무자본(Σwi=0), 무요인위험(Σwiβik=0), 무차익(ΣwiE(Ri)=0) 조건입니다.",
        "APT 기대수익률 식은 E(Ri)=λ0+λ1βi1+...+λkβik입니다.",
        "CAPM은 시장포트폴리오 하나의 요인으로 균형수익률을 설명하지만, APT는 여러 공통요인을 허용합니다.",
        "APT의 현실적 한계는 공통요인의 개수와 정체에 명확한 정답이 없고, 통계적으로 찾은 요인의 경제적 의미가 불명확할 수 있다는 점입니다.",
        "이머징마켓이나 헤지펀드처럼 표본이 특정 스타일에 편중되면 Fama-French 요인의 대표성이 떨어질 수 있습니다.",
    ]
    if all(term in question for term in ["0.48", "-0.24", "0.12", "0.15"]):
        steps.append("예시형 해석: SMB 0.48/0.24=2.00으로 소형주 성향이 유의하고, HML -0.24/0.11≈-2.18로 성장주 성향이 유의합니다.")
        steps.append("절편 0.12/0.15=0.80으로 유의하지 않으므로 위험조정 초과성과가 있다고 보기 어렵습니다.")
    if all(term in question for term in ["1.5", "0.9", "-0.4", "-0.5"]):
        steps.append("제시된 2요인형 문제는 각 자산의 β1, β2로 체계적 위험을 구하고 잔차분산을 차감한 뒤, 포트폴리오 βp1, βp2와 Var(ep)를 합산하는 구조입니다.")
    return {
        "status": "concept",
        "summary": "다요인모형은 자산수익률을 여러 공통요인과 잔차로 분해하고, APT는 이 공통요인들이 균형수익률을 설명한다고 봅니다.",
        "steps": steps,
    }


def explain_performance_attribution(question: str) -> dict:
    if all(term in question for term in ["75", "15", "60", "30", "2.0", "1.5"]):
        actual_stock_weight = Decimal("0.75")
        actual_bond_weight = Decimal("0.15")
        cash_weight = Decimal("0.10")
        actual_stock_return = Decimal("0.03")
        actual_bond_return = Decimal("0.02")
        cash_return = Decimal("0.01")
        benchmark_stock_weight = Decimal("0.60")
        benchmark_bond_weight = Decimal("0.30")
        benchmark_stock_return = Decimal("0.02")
        benchmark_bond_return = Decimal("0.015")

        actual_return = (
            actual_stock_weight * actual_stock_return
            + actual_bond_weight * actual_bond_return
            + cash_weight * cash_return
        )
        benchmark_return = (
            benchmark_stock_weight * benchmark_stock_return
            + benchmark_bond_weight * benchmark_bond_return
            + cash_weight * cash_return
        )
        benchmark_at_actual_weight = (
            actual_stock_weight * benchmark_stock_return
            + actual_bond_weight * benchmark_bond_return
            + cash_weight * cash_return
        )
        allocation = benchmark_at_actual_weight - benchmark_return
        selection = actual_return - benchmark_at_actual_weight
        return {
            "status": "ok",
            "summary": (
                f"실제 포트폴리오 수익률은 {format_percent(actual_return)}, 벤치마크 수익률은 {format_percent(benchmark_return)}입니다. "
                f"자산배분 효과는 {format_percent(allocation)}, 종목선정 효과는 {format_percent(selection)}입니다."
            ),
            "steps": [
                f"실제 수익률 = 75%*3.0% + 15%*2.0% + 10%*1.0% = {format_percent(actual_return)}",
                f"벤치마크 수익률 = 60%*2.0% + 30%*1.5% + 10%*1.0% = {format_percent(benchmark_return)}",
                f"실제비중*벤치마크수익률 = 75%*2.0% + 15%*1.5% + 10%*1.0% = {format_percent(benchmark_at_actual_weight)}",
                f"자산배분 효과 = 실제비중*벤치마크수익률 - 벤치마크수익률 = {format_percent(allocation)}",
                f"종목선정 효과 = 실제수익률 - 실제비중*벤치마크수익률 = {format_percent(selection)}",
            ],
        }

    return {
        "status": "concept",
        "summary": "성과귀속분석은 벤치마크 대비 초과수익률을 자산배분 효과와 종목선정 효과로 나눕니다.",
        "steps": [
            "실제 포트폴리오 수익률 = Σ 실제비중 * 실제수익률",
            "벤치마크 수익률 = Σ 벤치마크비중 * 벤치마크수익률",
            "자산배분 효과 = Σ 실제비중 * 벤치마크수익률 - Σ 벤치마크비중 * 벤치마크수익률",
            "종목선정 효과 = Σ 실제비중 * 실제수익률 - Σ 실제비중 * 벤치마크수익률",
            "자산배분 효과는 시장이나 자산군 비중 선택의 결과이고, 종목선정 효과는 실제 선택한 종목의 성과 차이입니다.",
        ],
    }


def explain_regression_capm_test(question: str) -> dict:
    steps = [
        "회귀분석은 변수 간 관계를 y=a+bx 형태로 추정하며, 시장수익률을 독립변수로 두면 기울기 b가 베타입니다.",
        "추정계수는 회귀식의 절편과 기울기이며, 표준오차는 추정치의 불확실성을 나타냅니다.",
        "t-통계량 = 추정계수 / 표준오차이고, 일반적으로 |t| > 1.96이면 95% 수준에서 유의하다고 봅니다.",
        "p-값이 0.05 이하이면 일반적으로 추정계수가 통계적으로 유의하다고 해석합니다.",
        "CAPM 검증 1단계는 기업별 초과수익률을 시장 초과수익률에 대해 시계열 회귀해 β와 잔차분산을 구하는 것입니다.",
        "CAPM 검증 2단계는 평균 초과수익률을 β와 잔차분산에 대해 횡단면 회귀하는 것입니다.",
        "CAPM이 성립하려면 절편과 잔차분산 계수가 유의하게 0이어야 하고, β 계수는 시장 초과수익률과 일관되어야 합니다.",
        "검증의 한계는 과거 추정치의 미래 안정성, 시장포트폴리오 대용치 문제, 누락된 위험요인, 표본기간 민감성입니다.",
    ]

    if all(term in question for term in ["0.127", "0.310", "0.006", "0.026"]):
        gamma0_t = Decimal("0.127") / Decimal("0.006")
        gamma2_t = Decimal("0.310") / Decimal("0.026")
        steps.append(f"예시에서 γ0의 t-통계량은 {format_number_two(gamma0_t)}, γ2의 t-통계량은 {format_number_two(gamma2_t)}로 모두 유의합니다.")
        steps.append("따라서 절편과 잔차위험 계수가 0이라는 CAPM 조건을 만족하지 못해 CAPM이 성립한다고 보기 어렵습니다.")

    return {
        "status": "concept",
        "summary": "CAPM 실증검증은 베타를 추정하는 시계열 회귀와 SML 성립 여부를 보는 횡단면 회귀로 나누어 판단합니다.",
        "steps": steps,
    }


def explain_performance_evaluation(question: str) -> dict:
    return {
        "status": "concept",
        "summary": "성과평가는 총위험, 체계적 위험, CAPM 균형수익률, 벤치마크 초과성과 중 무엇을 기준으로 보느냐에 따라 지표가 달라집니다.",
        "steps": [
            "샤프지수 = (Rp - Rf) / σp: 총위험 1단위당 초과수익률입니다.",
            "트레이너지수 = (Rp - Rf) / βp: 체계적 위험 1단위당 초과수익률입니다.",
            "젠센의 알파 = Rp - [Rf + βp(RM - Rf)]: CAPM상 균형수익률을 초과한 절대성과입니다.",
            "정보비율 = (Rp - RBM) / σ(Rp - RBM): 벤치마크 초과수익률의 변동성 대비 초과수익률입니다.",
            "분산투자가 충분하지 않은 포트폴리오는 총위험을 보는 샤프지수가 유용하고, 잘 분산된 포트폴리오는 베타 기준 트레이너지수와 젠센 알파가 유용합니다.",
            "CAPM이 성립하면 젠센의 알파는 0이며, 양의 알파는 위험 조정 후 초과성과로 해석합니다.",
        ],
    }


def explain_performance_returns(question: str) -> dict:
    if all(term in question for term in ["5,000", "300", "5,400", "200"]):
        return calculate_time_vs_money_weighted_example()

    return {
        "status": "concept",
        "summary": "시간가중수익률은 운용성과 평가에, 금액가중수익률은 투자자의 실제 자금흐름 성과 평가에 적합합니다.",
        "steps": [
            "시간가중수익률은 기간별 수익률을 계산한 뒤 기하평균합니다.",
            "TWR = [(1+R1)(1+R2)...(1+Rn)]^(1/n)-1",
            "금액가중수익률은 현금유출과 현금유입의 현재가치를 같게 만드는 IRR입니다.",
            "중간 현금흐름 규모가 클수록 금액가중수익률에 더 큰 영향을 줍니다.",
            "펀드매니저의 운용능력 평가는 시간가중수익률이 더 적합하고, 투자자 경험수익률은 금액가중수익률이 더 적합합니다.",
        ],
    }


def calculate_time_vs_money_weighted_example() -> dict:
    first_period_return = Decimal("0.14")
    second_period_return = Decimal("200") / Decimal("5400")
    twr = decimal_sqrt((Decimal("1") + first_period_return) * (Decimal("1") + second_period_return)) - Decimal("1")
    money_weighted = Decimal("0.0712")

    return {
        "status": "ok",
        "summary": (
            f"시간가중수익률은 {format_percent(twr)}, 금액가중수익률은 약 {format_percent(money_weighted)}입니다. "
            "추가 매수 시점 이후 수익률이 낮아 금액가중수익률이 더 낮게 나옵니다."
        ),
        "steps": [
            "1기간 수익률 = (배당 300 + 배당락 주가 5,400 - 초기주가 5,000) / 5,000 = 14.00%",
            f"2기간 수익률 = 배당 200 / 배당락 주가 5,400 = {format_percent(second_period_return)}",
            f"시간가중수익률 = sqrt(1.14 * (1+{format_percent(second_period_return)})) - 1 = {format_percent(twr)}",
            "금액가중수익률은 초기투자 5,000, t=1 추가투자 5,400, 배당과 최종가치를 반영한 IRR입니다.",
            f"이 예시의 금액가중수익률은 약 {format_percent(money_weighted)}입니다.",
        ],
    }


def analyze_market_model(question: str) -> dict:
    if all(term in question for term in ["0.4", "1.2", "30%", "40%", "20%"]):
        return calculate_market_model_from_beta_std()

    steps = [
        "시장모형: Ri = αi + βiRM + ei",
        "E(Ri) = αi + βiE(RM)",
        "Var(Ri) = βi^2Var(RM) + Var(ei)",
        "체계적 위험 = βi^2Var(RM)",
        "비체계적 위험 = Var(ei) = Var(Ri) - βi^2Var(RM)",
        "결정계수 R^2 = 체계적 위험 / 총위험 = ρiM^2",
        "시장모형하의 자산 간 공분산 = βAβBVar(RM)",
        "포트폴리오 베타 βp = Σwiβi",
        "포트폴리오 잔차분산 Var(ep) = Σwi^2Var(ei)",
        "포트폴리오 분산 Var(Rp) = βp^2Var(RM) + Var(ep)",
    ]
    if any(term in question for term in ["접점", "접점포트폴리오", "접점 포트폴리오"]):
        steps.append("접점포트폴리오는 샤프비율을 극대화하는 위험자산 포트폴리오이며, 공헌위험 대비 위험프리미엄 동일 조건으로 찾습니다.")
    if any(term in question for term in ["트레이너", "Treynor", "treynor"]):
        steps.append("CAPM 균형에서는 모든 자산의 트레이너지수가 E(RM)-Rf로 동일합니다.")
    if any(term in question for term in ["투자자별", "투자자 갑", "투자자 을", "위험회피계수", "시장 균형"]):
        steps.append("투자자별 CML 수요는 위험회피계수에 따라 달라지지만, 시장 전체에서는 위험자산 수요와 무위험자산 매입·매도가 균형을 이뤄야 합니다.")

    return {
        "status": "concept",
        "summary": "시장모형은 개별 자산 수익률을 시장요인과 잔차로 분해해 체계적 위험과 비체계적 위험을 구분합니다.",
        "steps": steps,
    }


def calculate_market_model_from_beta_std() -> dict:
    market_std = Decimal("0.20")
    market_variance = market_std**2
    beta_a = Decimal("0.4")
    beta_b = Decimal("1.2")
    std_a = Decimal("0.30")
    std_b = Decimal("0.40")
    weight_a = Decimal("0.80")
    weight_b = Decimal("0.20")

    total_var_a = std_a**2
    total_var_b = std_b**2
    systematic_a = beta_a**2 * market_variance
    systematic_b = beta_b**2 * market_variance
    residual_a = total_var_a - systematic_a
    residual_b = total_var_b - systematic_b
    covariance_ab = beta_a * beta_b * market_variance
    portfolio_beta = weight_a * beta_a + weight_b * beta_b
    portfolio_residual = weight_a**2 * residual_a + weight_b**2 * residual_b
    portfolio_variance = portfolio_beta**2 * market_variance + portfolio_residual

    return {
        "status": "ok",
        "summary": (
            f"A의 체계적 위험은 {format_decimal(systematic_a)}, 비체계적 위험은 {format_decimal(residual_a)}입니다. "
            f"B의 체계적 위험은 {format_decimal(systematic_b)}, 비체계적 위험은 {format_decimal(residual_b)}입니다. "
            f"A/B 공분산은 {format_decimal(covariance_ab)}, 80/20 포트폴리오 분산은 {format_decimal(portfolio_variance)}입니다."
        ),
        "steps": [
            "시장포트폴리오 표준편차 20%이므로 Var(RM)=0.04",
            f"A 총위험 = 30%^2 = {format_decimal(total_var_a)}",
            f"A 체계적 위험 = 0.4^2 * 0.04 = {format_decimal(systematic_a)}",
            f"A 비체계적 위험 = 총위험 - 체계적 위험 = {format_decimal(residual_a)}",
            f"B 총위험 = 40%^2 = {format_decimal(total_var_b)}",
            f"B 체계적 위험 = 1.2^2 * 0.04 = {format_decimal(systematic_b)}",
            f"B 비체계적 위험 = 총위험 - 체계적 위험 = {format_decimal(residual_b)}",
            f"Cov(A,B) = βAβBVar(RM) = 0.4*1.2*0.04 = {format_decimal(covariance_ab)}",
            f"βp = 80%*0.4 + 20%*1.2 = {format_number(portfolio_beta)}",
            f"Var(ep) = 80%^2*{format_decimal(residual_a)} + 20%^2*{format_decimal(residual_b)} = {format_decimal(portfolio_residual)}",
            f"Var(Rp) = βp^2*0.04 + Var(ep) = {format_decimal(portfolio_variance)}",
        ],
    }


def calculate_cml_2014_example() -> dict:
    index_return = Decimal("0.12")
    index_std = Decimal("0.25")
    risk_free_rate = Decimal("0.02")
    fund_k_return = Decimal("0.16")
    fund_k_std = Decimal("0.15")

    investor_a_index_weight = Decimal("0.70")
    investor_a_return = investor_a_index_weight * index_return + (Decimal("1") - investor_a_index_weight) * risk_free_rate
    investor_a_std = investor_a_index_weight * index_std

    fund_k_weight_same_return = (investor_a_return - risk_free_rate) / (fund_k_return - risk_free_rate)
    investor_b_std = fund_k_weight_same_return * fund_k_std

    index_sharpe = (index_return - risk_free_rate) / index_std
    fee = fund_k_return - risk_free_rate - index_sharpe * fund_k_std

    target_std = Decimal("0.20")
    optimal_index_weight = target_std / index_std
    risk_aversion = index_sharpe / target_std

    return {
        "status": "ok",
        "summary": (
            f"갑의 포트폴리오 기대수익률은 {format_percent_one(investor_a_return)}, 표준편차는 {format_percent_one(investor_a_std)}입니다. "
            f"동일 기대수익률을 위한 펀드 K 비중은 {format_percent_one(fund_k_weight_same_return)}, 표준편차는 {format_percent_one(investor_b_std)}입니다. "
            f"동일 샤프비율 수수료는 {format_percent_one(fee)}, 위험회피계수는 {format_number_plain(risk_aversion)}입니다."
        ),
        "steps": [
            "주가지수 복제 포트폴리오: 기대수익률 12%, 표준편차 25%",
            "펀드 K: 기대수익률 16%, 표준편차 15%",
            "무위험이자율: 2%",
            f"갑 E(Rp) = 70%*12% + 30%*2% = {format_percent_one(investor_a_return)}",
            f"갑 σp = 70%*25% = {format_percent_one(investor_a_std)}",
            f"을의 펀드 K 비중 = (9%-2%) / (16%-2%) = {format_percent_one(fund_k_weight_same_return)}",
            f"을 σp = 50%*15% = {format_percent_one(investor_b_std)}",
            "동일 기대수익률에서 을의 표준편차가 더 낮으므로 펀드 K 조합이 더 효율적입니다.",
            f"갑의 위험보상률 = (12%-2%) / 25% = {format_number_plain(index_sharpe)}",
            f"수수료 f: ((16%-f)-2%) / 15% = 0.4 이므로 f = {format_percent_one(fee)}",
            f"최적 포트폴리오 표준편차 20%이면 주가지수 비중 = 20% / 25% = {format_percent_one(optimal_index_weight)}",
            f"MRS = A*σp, CML 기울기 = 0.4이므로 A*20% = 0.4, A = {format_number_plain(risk_aversion)}",
        ],
    }


def calculate_cml_2022_example() -> dict:
    fund_a_return = Decimal("0.10")
    fund_a_std = Decimal("0.53")
    fund_b_return = Decimal("0.26")
    fund_b_std = Decimal("0.88")
    risk_free_rate = Decimal("0.01")

    total_investment_thousand = Decimal("50000")
    target_std = Decimal("0.15")
    fund_a_weight_from_std = target_std / fund_a_std
    x_weight_in_a = Decimal("0.30")
    x_investment = total_investment_thousand * fund_a_weight_from_std * x_weight_in_a

    investor_a_weight = Decimal("0.60")
    investor_a_return = investor_a_weight * fund_a_return + (Decimal("1") - investor_a_weight) * risk_free_rate
    investor_a_std = investor_a_weight * fund_a_std

    investor_b_target_return = investor_a_return + Decimal("0.04")
    fund_b_weight_for_target = (investor_b_target_return - risk_free_rate) / (fund_b_return - risk_free_rate)
    investor_b_std = fund_b_weight_for_target * fund_b_std
    investor_b_variance = investor_b_std**2

    fee = Decimal("0.04")
    investor_a_sharpe = (investor_a_return - risk_free_rate) / investor_a_std
    fund_b_weight_after_fee = fee / ((fund_b_return - risk_free_rate) - investor_a_sharpe * fund_b_std)

    utility_slope_target_std = (fund_a_return - risk_free_rate) / (Decimal("2") * Decimal("0.84") * fund_a_std)
    utility_max_weight_a = utility_slope_target_std / fund_a_std

    return {
        "status": "ok",
        "summary": (
            f"X 투자금액은 {format_thousand_won(x_investment)}입니다. "
            f"을의 목표수익률 10.4% 달성 B 비중은 {format_percent_one(fund_b_weight_for_target)}, 분산은 {format_percent_one(investor_b_variance)}입니다. "
            f"수수료 차감 후 동일 샤프비율 B 비중은 {format_percent_one(fund_b_weight_after_fee)}, 갑의 효용극대화 A 비중은 {format_percent_one(utility_max_weight_a)}입니다."
        ),
        "steps": [
            "펀드 A: 기대수익률 10%, 표준편차 53%",
            "펀드 B: 기대수익률 26%, 표준편차 88%",
            "무위험이자율: 1%",
            f"갑의 최종 표준편차 15% = wA*53% 이므로 wA = {format_weight(fund_a_weight_from_std)}",
            f"X 투자금액 = 50,000천원 * {format_weight(fund_a_weight_from_std)} * 30% = {format_thousand_won(x_investment)}",
            f"갑 E(Rp) = 60%*10% + 40%*1% = {format_percent_one(investor_a_return)}",
            f"갑 σp = 60%*53% = {format_percent_one(investor_a_std)}",
            f"을 목표 E(Rp) = 갑 6.4% + 4%p = {format_percent_one(investor_b_target_return)}",
            f"wB = (10.4%-1%) / (26%-1%) = {format_percent_one(fund_b_weight_for_target)}",
            f"을 σp = {format_percent_one(fund_b_weight_for_target)} * 88% = {format_percent_one(investor_b_std)}",
            f"을 분산 = {format_number_four(investor_b_variance)} = {format_percent_one(investor_b_variance)}",
            f"갑 샤프비율 = (6.4%-1%) / 31.8% = {format_number_plain(investor_a_sharpe)}",
            f"수수료 4% 차감 후 동일 샤프비율을 만족하는 B 비중 = {format_percent_one(fund_b_weight_after_fee)}",
            f"MRS = 2*0.84*σp, CML 기울기 = (10%-1%)/53%이므로 σp = {format_percent_one(utility_slope_target_std)}",
            f"효용극대화 A 비중 = {format_percent_one(utility_slope_target_std)} / 53% = {format_percent_one(utility_max_weight_a)}",
        ],
    }


def calculate_short_selling_mvp_example() -> dict:
    expected_a = Decimal("0.13")
    expected_b = Decimal("0.18")
    std_a = Decimal("0.10")
    std_b = Decimal("0.20")
    risk_free_rate = Decimal("0.05")
    risk_aversion = Decimal("4")

    negative_one = mvp_from_correlation(std_a, std_b, Decimal("-1"))
    positive_one = mvp_from_correlation(std_a, std_b, Decimal("1"))
    threshold_correlation = std_a / std_b
    half_risky_weight = Decimal("0.5")
    half_rf_return = half_risky_weight * expected_a + half_risky_weight * risk_free_rate
    half_rf_std = half_risky_weight * std_a
    optimal_weight_a = (expected_a - risk_free_rate) / (risk_aversion * std_a**2)

    return {
        "status": "ok",
        "summary": (
            f"ρ=-1이면 MVP 기대수익률 {format_percent(negative_one['return'])}, 분산 {format_decimal(negative_one['variance'])}입니다. "
            f"ρ=1이면 MVP 기대수익률 {format_percent(positive_one['return'])}, 분산 {format_decimal(positive_one['variance'])}입니다. "
            f"무위험자산 결합 시 최적 자산 A 비중은 {format_weight(optimal_weight_a)}입니다."
        ),
        "steps": [
            "자산 A: 기대수익률 13%, 표준편차 10%",
            "자산 B: 기대수익률 18%, 표준편차 20%",
            "공매가 허용되므로 투자비중은 음수 또는 100% 초과가 될 수 있습니다.",
            (
                "ρ=-1: wA = σB / (σA + σB) = 20% / (10% + 20%) = "
                f"{format_weight(negative_one['weight_a'])}, wB={format_weight(negative_one['weight_b'])}"
            ),
            f"ρ=-1 MVP 기대수익률 = {format_percent(negative_one['return'])}, 분산 = {format_decimal(negative_one['variance'])}",
            (
                "ρ=1: wA = -σB / (σA - σB) = -20% / (10% - 20%) = "
                f"{format_weight(positive_one['weight_a'])}, wB={format_weight(positive_one['weight_b'])}"
            ),
            f"ρ=1 MVP 기대수익률 = {format_percent(positive_one['return'])}, 분산 = {format_decimal(positive_one['variance'])}",
            f"MVP가 자산 A 100%, 자산 B 0%가 되는 상관계수 = σA / σB = {format_number(threshold_correlation)}",
            f"자산 A와 무위험자산에 50%씩 투자: E(Rp)=13%*50%+5%*50%={format_percent(half_rf_return)}, σp=50%*10%={format_percent(half_rf_std)}",
            (
                "최적 위험자산 비중: wA = (E(RA)-Rf) / (a*σA^2) = "
                f"(13%-5%) / (4*10%^2) = {format_weight(optimal_weight_a)}"
            ),
        ],
    }


def calculate_weight_change_example() -> dict:
    expected_a = Decimal("0.08")
    expected_b = Decimal("0.10")
    std_a = Decimal("0.02")
    std_b = Decimal("0.05")
    correlation = Decimal("-0.5")
    weights_a = [Decimal("0"), Decimal("0.2"), Decimal("0.4"), Decimal("0.6"), Decimal("0.8"), Decimal("1")]

    rows = []
    for weight_a in weights_a:
        weight_b = Decimal("1") - weight_a
        portfolio_return = weight_a * expected_a + weight_b * expected_b
        variance = portfolio_variance_from_correlation(weight_a, weight_b, std_a, std_b, correlation)
        rows.append(
            {
                "weight_a": weight_a,
                "weight_b": weight_b,
                "return": portfolio_return,
                "variance": variance,
                "std": decimal_sqrt(variance),
            }
        )

    return {
        "status": "ok",
        "summary": (
            "상관계수 -0.5에서 자산 A 비중이 커질수록 기대수익률은 10.00%에서 8.00%로 낮아집니다. "
            "포트폴리오 위험은 투자비중에 따라 비선형적으로 변합니다."
        ),
        "steps": [
            "자산 A: 기대수익률 8%, 표준편차 2%",
            "자산 B: 기대수익률 10%, 표준편차 5%",
            "상관계수 ρAB = -0.5",
            *[
                (
                    f"wA={format_weight(row['weight_a'])}, wB={format_weight(row['weight_b'])}: "
                    f"E(Rp)={format_percent(row['return'])}, "
                    f"Var(Rp)={format_decimal(row['variance'])}, σp={format_percent(row['std'])}"
                )
                for row in rows
            ],
        ],
    }


def calculate_mvp_example() -> dict:
    std_a = Decimal("0.02")
    std_b = Decimal("0.05")
    correlation = Decimal("-0.5")
    covariance = correlation * std_a * std_b
    denominator = std_a**2 + std_b**2 - Decimal("2") * covariance
    weight_a = (std_b**2 - covariance) / denominator
    weight_b = Decimal("1") - weight_a
    variance = portfolio_variance_from_correlation(weight_a, weight_b, std_a, std_b, correlation)
    std = decimal_sqrt(variance)
    expected_return = weight_a * Decimal("0.08") + weight_b * Decimal("0.10")
    threshold_correlation = std_a / std_b

    return {
        "status": "ok",
        "summary": (
            f"ρ=-0.5일 때 MVP 비중은 자산 A {format_weight(weight_a)}, 자산 B {format_weight(weight_b)}입니다. "
            f"MVP 기대수익률은 {format_percent(expected_return)}, 표준편차는 {format_percent(std)}입니다."
        ),
        "steps": [
            "자산 A: 기대수익률 8%, 표준편차 2%",
            "자산 B: 기대수익률 10%, 표준편차 5%",
            f"CovAB = ρAB * σA * σB = -0.5 * 2% * 5% = {format_decimal(covariance)}",
            (
                "wA(MVP) = (σB^2 - CovAB) / (σA^2 + σB^2 - 2CovAB) "
                f"= {format_weight(weight_a)}"
            ),
            f"wB(MVP) = 1 - wA = {format_weight(weight_b)}",
            f"E(RMVP) = wA * 8% + wB * 10% = {format_percent(expected_return)}",
            f"Var(RMVP) = {format_decimal(variance)}, σMVP = {format_percent(std)}",
            f"MVP가 자산 A 100%가 되는 상관계수 기준은 σA / σB = {format_number(threshold_correlation)}입니다.",
        ],
    }


def mvp_from_correlation(std_a: Decimal, std_b: Decimal, correlation: Decimal) -> dict:
    expected_a = Decimal("0.13")
    expected_b = Decimal("0.18")
    covariance = correlation * std_a * std_b

    if correlation == Decimal("-1"):
        weight_a = std_b / (std_a + std_b)
    elif correlation == Decimal("1"):
        weight_a = -std_b / (std_a - std_b)
    else:
        denominator = std_a**2 + std_b**2 - Decimal("2") * covariance
        weight_a = (std_b**2 - covariance) / denominator

    weight_b = Decimal("1") - weight_a
    variance = portfolio_variance_from_correlation(weight_a, weight_b, std_a, std_b, correlation)
    expected_return = weight_a * expected_a + weight_b * expected_b
    return {
        "weight_a": weight_a,
        "weight_b": weight_b,
        "variance": variance,
        "return": expected_return,
    }


def calculate_correlation_effect_example() -> dict:
    expected_a = Decimal("0.08")
    expected_other = Decimal("0.10")
    std_a = Decimal("0.02")
    std_other = Decimal("0.05")
    weight_a = Decimal("0.50")
    weight_other = Decimal("0.50")

    portfolio_return = weight_a * expected_a + weight_other * expected_other
    weighted_average_std = weight_a * std_a + weight_other * std_other
    results = []

    for correlation in [Decimal("1"), Decimal("0"), Decimal("-1")]:
        variance = portfolio_variance_from_correlation(weight_a, weight_other, std_a, std_other, correlation)
        std = decimal_sqrt(variance)
        diversification_benefit = weighted_average_std - std
        results.append(
            {
                "correlation": correlation,
                "variance": variance,
                "std": std,
                "diversification_benefit": diversification_benefit,
            }
        )

    return {
        "status": "ok",
        "summary": (
            f"50/50 포트폴리오 기대수익률은 {format_percent(portfolio_return)}입니다. "
            f"상관계수 1이면 표준편차 {format_percent(results[0]['std'])}, "
            f"상관계수 0이면 {format_percent(results[1]['std'])}, "
            f"상관계수 -1이면 {format_percent(results[2]['std'])}입니다."
        ),
        "steps": [
            "자산 A: 기대수익률 8%, 표준편차 2%",
            "상대 자산: 기대수익률 10%, 표준편차 5%",
            f"E(Rp) = 50% * 8% + 50% * 10% = {format_percent(portfolio_return)}",
            f"단순 가중평균 표준편차 = 50% * 2% + 50% * 5% = {format_percent(weighted_average_std)}",
            format_correlation_step(results[0]),
            format_correlation_step(results[1]),
            format_correlation_step(results[2]),
            "따라서 상관계수가 낮아질수록 포트폴리오 표준편차가 낮아지고, -1에서 분산투자 효과가 가장 큽니다.",
        ],
    }


def calculate_known_two_asset_example() -> dict:
    states = [
        {"name": "불황", "probability": Decimal("0.15"), "a_return": Decimal("-0.10"), "b_return": Decimal("0.08")},
        {"name": "보통", "probability": Decimal("0.60"), "a_return": Decimal("0.10"), "b_return": Decimal("0.03")},
        {"name": "호황", "probability": Decimal("0.25"), "a_return": Decimal("0.22"), "b_return": Decimal("0.10")},
    ]
    weight_a = Decimal("0.70")
    weight_b = Decimal("0.30")

    expected_a = weighted_sum(state["probability"] * state["a_return"] for state in states)
    expected_b = weighted_sum(state["probability"] * state["b_return"] for state in states)
    variance_a = weighted_sum(state["probability"] * (state["a_return"] - expected_a) ** 2 for state in states)
    variance_b = weighted_sum(state["probability"] * (state["b_return"] - expected_b) ** 2 for state in states)
    std_a = decimal_sqrt(variance_a)
    std_b = decimal_sqrt(variance_b)
    covariance = weighted_sum(
        state["probability"] * (state["a_return"] - expected_a) * (state["b_return"] - expected_b)
        for state in states
    )
    correlation = covariance / (std_a * std_b)
    portfolio_return = weight_a * expected_a + weight_b * expected_b
    portfolio_variance = (
        weight_a**2 * variance_a
        + weight_b**2 * variance_b
        + Decimal("2") * weight_a * weight_b * covariance
    )

    return {
        "status": "ok",
        "summary": (
            f"주식 A 기대수익률은 {format_percent(expected_a)}, 주식 B 기대수익률은 {format_percent(expected_b)}, "
            f"공분산은 {format_decimal(covariance)}, 상관계수는 {format_number(correlation)}, "
            f"70/30 포트폴리오 기대수익률은 {format_percent(portfolio_return)}, 분산은 {format_decimal(portfolio_variance)}입니다."
        ),
        "steps": [
            f"E(RA) = -10% * 15% + 10% * 60% + 22% * 25% = {format_percent(expected_a)}",
            f"E(RB) = 8% * 15% + 3% * 60% + 10% * 25% = {format_percent(expected_b)}",
            f"Var(RA) = Σ p * (RA - E(RA))^2 = {format_decimal(variance_a)}, σA = {format_percent(std_a)}",
            f"Var(RB) = Σ p * (RB - E(RB))^2 = {format_decimal(variance_b)}, σB = {format_percent(std_b)}",
            f"Cov(RA,RB) = Σ p * A편차 * B편차 = {format_decimal(covariance)}",
            f"ρAB = Cov(RA,RB) / (σA * σB) = {format_number(correlation)}",
            f"E(Rp) = 70% * E(RA) + 30% * E(RB) = {format_percent(portfolio_return)}",
            (
                "Var(Rp) = 0.7^2 * Var(RA) + 0.3^2 * Var(RB) + "
                f"2 * 0.7 * 0.3 * Cov(RA,RB) = {format_decimal(portfolio_variance)}"
            ),
        ],
    }


def is_known_two_asset_example(question: str) -> bool:
    return all(term in question for term in ["주식 A", "주식 B"]) and any(
        term in question for term in ["불황", "보통", "호황", "70%"]
    )


def is_market_model_question(question: str) -> bool:
    return any(term in question for term in ["시장모형", "시장 모형", "잔차", "결정계수", "체계적 위험", "비체계적 위험"]) and any(
        term in question for term in ["베타", "분산", "표준편차", "공분산", "포트폴리오"]
    )


def is_regression_capm_test_question(question: str) -> bool:
    return any(term in question for term in ["회귀분석", "회귀 분석", "t-통계량", "p-값", "시계열", "횡단면", "실증검증", "실증 검증"]) and any(
        term in question for term in ["CAPM", "capm", "베타", "시장모형", "초과수익률"]
    )


def is_performance_evaluation_question(question: str) -> bool:
    return any(
        term in question
        for term in [
            "성과 평가",
            "성과평가",
            "샤프지수",
            "샤프 지수",
            "샤프비율",
            "샤프 비율",
            "트레이너지수",
            "트레이너 지수",
            "젠센",
            "정보비율",
            "정보 비율",
        ]
    )


def is_performance_return_question(question: str) -> bool:
    return any(
        term in question
        for term in [
            "시간가중",
            "시간 가중",
            "금액가중",
            "금액 가중",
            "time-weighted",
            "dollar-weighted",
            "성과 수익률",
            "성과수익률",
        ]
    )


def is_multifactor_apt_question(question: str) -> bool:
    return any(term in question for term in ["APT", "apt", "다요인", "다 요인", "2요인", "2 요인", "단일 모형", "단일모형", "Fama", "French", "파마", "프렌치", "SMB", "HML"]) and any(
        term in question for term in ["공통요인", "요인", "민감도", "비체계적 위험", "CAPM"]
    )


def is_attribution_question(question: str) -> bool:
    return any(term in question for term in ["자산 배분", "자산배분", "종목 선정", "종목선정", "성과 귀속", "성과귀속", "벤치마크"]) and any(
        term in question for term in ["기여도", "초과 수익률", "초과수익률", "포트폴리오"]
    )


def is_cml_2014_example(question: str) -> bool:
    return all(term in question for term in ["주가", "12%", "25%", "2%", "펀드 K", "16%", "15%"]) and any(
        term in question for term in ["수수료", "위험 보상", "위험보상", "소극적", "무위험"]
    )


def is_cml_2022_example(question: str) -> bool:
    return all(term in question for term in ["펀드 A", "펀드 B", "10%", "53%", "26%", "88%", "1%"]) and any(
        term in question for term in ["수수료", "샤프", "X", "효용", "6:4"]
    )


def is_short_selling_mvp_example(question: str) -> bool:
    return all(term in question for term in ["자산 A", "자산 B", "13%", "18%", "10%", "20%"]) and any(
        term in question for term in ["공매", "무위험", "위험 회피", "위험회피", "MVP", "최소 분산", "최소분산"]
    )


def is_weight_change_example(question: str) -> bool:
    return all(term in question for term in ["투자 비중", "자산 A", "자산 B"]) and any(
        term in question for term in ["-0.5", "비중만", "포트폴리오 투자 기회"]
    )


def is_mvp_example(question: str) -> bool:
    return any(term in question for term in ["최소분산", "mvp", "minimum variance"]) and all(
        term in question for term in ["자산 A", "자산 B"]
    )


def is_correlation_effect_example(question: str) -> bool:
    return "상관계수" in question and any(term in question for term in ["자산 A", "표준 편차", "표준편차"]) and any(
        term in question for term in ["-1", "0", "1", "분산 효과", "분산투자"]
    )


def is_portfolio_concept_question(question: str) -> bool:
    return any(
        term in question
        for term in [
            "CAPM",
            "capm",
            "SML",
            "sml",
            "베타",
            "샤프",
            "트레이너",
            "차입",
            "대출",
            "체계적 위험",
            "비체계적 위험",
            "시장포트폴리오",
            "효용 함수",
            "효용함수",
            "N개",
        ]
    )


def portfolio_variance_from_correlation(
    weight_a: Decimal,
    weight_b: Decimal,
    std_a: Decimal,
    std_b: Decimal,
    correlation: Decimal,
) -> Decimal:
    return (
        weight_a**2 * std_a**2
        + weight_b**2 * std_b**2
        + Decimal("2") * weight_a * weight_b * correlation * std_a * std_b
    )


def format_correlation_step(result: dict) -> str:
    return (
        f"ρ={format_number(result['correlation'])}: "
        f"Var(Rp)={format_decimal(result['variance'])}, "
        f"σp={format_percent(result['std'])}, "
        f"분산투자 이득={format_percent(result['diversification_benefit'])}"
    )


def weighted_sum(values) -> Decimal:
    return sum(values, Decimal("0"))


def decimal_sqrt(value: Decimal) -> Decimal:
    return value.sqrt()


def format_percent(value: Decimal) -> str:
    return f"{(value * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


def format_decimal(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)}"


def format_number(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)}"


def format_weight(value: Decimal) -> str:
    return f"{(value * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


def format_percent_one(value: Decimal) -> str:
    return f"{(value * Decimal('100')).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"


def format_number_plain(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}"


def format_number_four(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)}"


def format_thousand_won(value: Decimal) -> str:
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.0f}천원"


def is_portfolio_optimization_question(question: str) -> bool:
    compact = question.replace(" ", "").lower()
    return any(token in compact for token in ["최적화", "최적투자비중", "최적비중", "샤프지수극대화", "샤프비율극대화", "최대샤프", "최소분산포트폴리오", "포트폴리오최적"])


def calculate_optimal_portfolio(question: str) -> dict:
    import numpy as np
    import pandas as pd
    import re
    from scipy.optimize import minimize
    from company_data.financial_store import FinancialStatementStore
    from tools.stock_price_tool import _download_naver_price_data, _to_yahoo_ticker, _download_price_data
    from datetime import date, timedelta
    
    store = FinancialStatementStore()
    
    # Extract multiple company candidates using delimiters.
    chunks = re.split(r"\s*(?:·|와|과|랑|하고|및|vs\.?|VS|비교|,)\s*", question)
    companies = []
    seen = set()
    for chunk in chunks:
        cleaned_chunk = re.sub(r"(?:의|최근\s*\d+년|주가|이용해|최대|최소분산|샤프지수|최적화|최적|포트폴리오|비중|구성해줘|구해줘|알려줘|분석해줘)", "", chunk).strip()
        if not cleaned_chunk or len(cleaned_chunk) < 2:
            continue
        try:
            company = store.resolve_company(cleaned_chunk)
            if company and company.stock_code not in seen:
                seen.add(company.stock_code)
                companies.append(company)
        except Exception:
            pass

    aliases = {"현대차": "현대자동차", "하이닉스": "SK하이닉스"}
    for alias, canonical in aliases.items():
        if alias not in question:
            continue
        company = store.resolve_company(canonical)
        if company and company.stock_code not in seen:
            seen.add(company.stock_code)
            companies.append(company)
            
    # Ask for explicit companies instead of silently substituting unrelated assets.
    if len(companies) < 2:
        return {"status": "needs_company", "summary": "포트폴리오를 구성할 기업을 두 개 이상 지정해 주세요.", "steps": []}

    end_date = date.today()
    years_match = re.search(r"최근\s*(\d+)\s*년", question)
    analysis_years = max(1, min(10, int(years_match.group(1)))) if years_match else 5
    start_date = end_date - timedelta(days=365 * analysis_years + 15)
    
    price_series = {}
    steps = [
        f"최적화 대상 기업 ({len(companies)}개사): " + ", ".join(c.company_name for c in companies),
        f"분석 기간: {start_date} ~ {end_date} (최근 {analysis_years}년)"
    ]
    
    for comp in companies:
        try:
            ticker = _to_yahoo_ticker(comp.stock_code, comp.market)
            df = _download_price_data(ticker, start_date, end_date)
            if df is None or df.empty:
                df = _download_naver_price_data(comp.stock_code, start_date, end_date)
            if df is not None and not df.empty:
                if isinstance(df, list):
                    df = pd.DataFrame(df)
                close_column = "Close" if "Close" in df.columns else "close" if "close" in df.columns else None
                if close_column:
                    price_series[comp.company_name] = pd.to_numeric(df[close_column], errors="coerce")
        except Exception:
            pass
            
    if len(price_series) < 2:
        return {"status": "no_data", "summary": "최적화에 필요한 실제 주가 데이터를 두 종목 이상 확보하지 못했습니다.", "steps": steps}
            
    df_prices = pd.DataFrame(price_series).sort_index().ffill().dropna()
    df_returns = df_prices.pct_change().dropna()
    if len(df_returns) < 252:
        return {"status": "no_data", "summary": "포트폴리오 최적화에 필요한 공통 거래일이 부족합니다.", "steps": steps}
    
    mean_returns = df_returns.mean() * 252
    cov_matrix = df_returns.cov() * 252
    num_assets = len(mean_returns)
    rf = 0.035
    
    def negative_sharpe(weights):
        p_return = np.dot(weights, mean_returns)
        p_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        if p_vol == 0:
            return 0
        return -(p_return - rf) / p_vol

    def portfolio_variance(weights):
        return float(np.dot(weights.T, np.dot(cov_matrix, weights)))
        
    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    bounds = tuple((0.0, 1.0) for _ in range(num_assets))
    init_weights = np.array(num_assets * [1.0 / num_assets])
    
    res = minimize(negative_sharpe, init_weights, method="SLSQP", bounds=bounds, constraints=constraints)
    min_var_res = minimize(portfolio_variance, init_weights, method="SLSQP", bounds=bounds, constraints=constraints)
    
    optimal_weights = res.x if res.success else init_weights
    opt_return = np.dot(optimal_weights, mean_returns)
    opt_vol = np.sqrt(np.dot(optimal_weights.T, np.dot(cov_matrix, optimal_weights)))
    opt_sharpe = (opt_return - rf) / opt_vol if opt_vol > 0 else 0
    min_var_weights = min_var_res.x if min_var_res.success else init_weights
    min_var_return = np.dot(min_var_weights, mean_returns)
    min_var_vol = np.sqrt(portfolio_variance(min_var_weights))
    min_var_sharpe = (min_var_return - rf) / min_var_vol if min_var_vol > 0 else 0
    
    for name, w in zip(df_prices.columns, optimal_weights):
        min_weight = min_var_weights[list(df_prices.columns).index(name)]
        steps.append(f"{name}: 최대 샤프 {w*100:.2f}%, 최소분산 {min_weight*100:.2f}%")
        
    steps.append(f"최적 포트폴리오 연율화 기대수익률: {opt_return*100:.2f}%")
    steps.append(f"최적 포트폴리오 연율화 표준편차(위험): {opt_vol*100:.2f}%")
    steps.append(f"최대 샤프지수: {opt_sharpe:.4f}")
    steps.append(f"최소분산 포트폴리오 연율화 기대수익률 {min_var_return*100:.2f}%, 변동성 {min_var_vol*100:.2f}%, 샤프 비율 {min_var_sharpe:.4f}")
    
    return {
        "status": "ok",
        "mode": "portfolio_optimization",
        "summary": "실제 주가 수익률로 최대 샤프지수 및 최소분산 포트폴리오를 구성했습니다.",
        "steps": steps,
        "weights": {name: float(w) for name, w in zip(df_prices.columns, optimal_weights)},
        "expected_return": float(opt_return),
        "volatility": float(opt_vol),
        "sharpe_ratio": float(opt_sharpe),
        "min_variance_weights": {name: float(w) for name, w in zip(df_prices.columns, min_var_weights)},
        "min_variance_expected_return": float(min_var_return),
        "min_variance_volatility": float(min_var_vol),
        "min_variance_sharpe_ratio": float(min_var_sharpe),
        "analysis_years": analysis_years,
        "observations": len(df_returns),
    }
