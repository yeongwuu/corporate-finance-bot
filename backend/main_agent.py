from llm_client import build_final_answer
from rag.simple_rag import search_knowledge
from tools.capital_budgeting_tool import analyze_capital_budgeting
from tools.cost_of_capital_tool import calculate_cost_of_capital
from tools.finance_concept_tool import explain_finance_concept
from tools.financial_ratio_tool import analyze_financial_ratios
from tools.mergers_acquisitions_tool import analyze_mergers_acquisitions
from tools.portfolio_tool import analyze_portfolio
from tools.risk_utility_tool import analyze_risk_utility
from tools.time_value_tool import analyze_time_value
from tools.valuation_tool import analyze_valuation
from tools.working_capital_tool import analyze_working_capital


def answer_finance_question(question: str) -> dict:
    tool_name = select_tool(question)
    references = search_knowledge(question)
    calculation = run_tool(tool_name, question)
    answer = build_final_answer(
        question=question,
        tool_name=tool_name,
        calculation=calculation,
        references=references,
    )

    return {
        "question": question,
        "tool": tool_name,
        "answer": answer,
        "calculation": calculation,
        "references": references,
    }


def select_tool(question: str) -> str:
    normalized = question.lower()
    compact = normalized.replace(" ", "")

    if any(word in normalized for word in ["비교기업", "대용기업", "투자안 베타", "프로젝트 베타", "조정현가", "apv", "목표 부채", "부채비율 유지", "이자비용 절세효과의 현재가치", "이자비용 절세효과 현재가치"]):
        return "capital_budgeting_tool"
    if any(word in normalized for word in ["m&a", "m＆a", "인수합병", "인수 합병", "합병", "흡수합병", "신설합병", "수직적 합병", "수평적 합병", "다각적 합병", "공개매수", "곰의 포옹", "새벽의 기습", "lbo", "mbo", "차입매수", "경영자매수", "적대적", "독약조항", "독약 풋", "황금낙하산", "백기사", "백지주", "황금주", "차등의결권", "팩맨", "왕관의 보석", "녹색편지", "행동주의 펀드", "토빈의 q", "저평가 가설", "경영자주의"]):
        return "mergers_acquisitions_tool"

    if any(
        word in normalized
        for word in [
            "유동비율",
            "당좌비율",
            "현금비율",
            "순운전자본비율",
            "부채비율",
            "자기자본비율",
            "이자보상비율",
            "비유동비율",
            "비유동장기적합률",
            "회전율",
            "회수기간",
            "지급기간",
            "영업순환주기",
            "현금순환주기",
            "현금전환주기",
            "총자산회전율",
            "매출액총이익률",
            "영업이익률",
            "순이익률",
            "총자본영업이익률",
            "수익성비율",
            "총자산성장률",
            "자기자본성장률",
            "내부자금",
            "안정성비율",
            "활동성비율",
            "유동성비율",
        ]
    ):
        return "financial_ratio_tool"
    if any(word in normalized for word in ["현금전환주기", "현금순환주기", "ccc", "운전자본"]):
        return "working_capital_tool"
    if any(word in normalized for word in ["ceq", "확실성등가", "확실성 등가", "경제적 부가가치", "시장부가가치", "시장 부가가치", "초과이익", "잔여이익", "잔여 이익", "npv 곡선", "피셔", "자본할당", "중복투자", "분할투자", "반복투자", "최소공배수", "무한반복", "연간균등가치", "aev", "투자기회선", "한계자본비용", "명목 현금흐름", "실질 현금흐름", "인플레이션", "비교기업", "대용기업", "투자안 베타", "프로젝트 베타", "조정현가", "apv", "목표 부채", "부채비율 유지", "이자비용 절세효과의 현재가치"]):
        return "capital_budgeting_tool"
    if any(word in normalized for word in ["자본구조", "mm이론", "mm 1958", "mm 1963", "하마다", "hamada", "무부채 베타", "주식베타", "주식 베타", "법인세율 변화", "개인소득세", "이자소득세", "주식투자소득세", "밀러", "miller", "균형부채", "deangelo", "masulis", "디안젤로", "마술리스", "비부채성 감세", "대리비용", "위험선호", "과소투자", "재산도피", "파산비용", "기대 파산", "자본조달순위", "pecking", "신호효과", "signaling", "순이익 접근", "순영업이익 접근", "전통적 접근", "miles", "ezzell", "harris", "pringle", "차익거래", "위험부채", "절세효과"]):
        return "cost_of_capital_tool"
    if any(
        word in normalized
        for word in [
            "포트폴리오",
            "공분산",
            "상관계수",
            "분산투자",
            "표준편차",
            "기대수익률",
            "무차별곡선",
            "지배관계",
            "capm",
            "sml",
            "베타",
            "샤프",
            "트레이너",
            "시장포트폴리오",
            "체계적 위험",
            "비체계적 위험",
            "효율적 투자선",
            "최소분산선",
            "자본배분선",
            "자본시장선",
            "cml",
            "cal",
            "토빈",
            "시장가치",
            "scl",
            "증권특성선",
            "증권시장선",
            "제로베타",
            "과소평가",
            "과대평가",
            "시장모형",
            "시장 모형",
            "잔차",
            "결정계수",
            "접점포트폴리오",
            "접점 포트폴리오",
            "트레이너지수",
            "트레이너 지수",
            "위험회피계수",
            "회귀분석",
            "회귀 분석",
            "t-통계량",
            "p-값",
            "실증검증",
            "실증 검증",
            "성과평가",
            "성과 평가",
            "샤프지수",
            "샤프 비율",
            "젠센",
            "정보비율",
            "시간가중",
            "시간 가중",
            "금액가중",
            "금액 가중",
            "성과수익률",
            "성과 수익률",
            "apt",
            "다요인",
            "다 요인",
            "2요인",
            "2 요인",
            "공통요인",
            "차익거래가격결정",
            "차익 거래 가격 결정",
            "fama",
            "french",
            "파마",
            "프렌치",
            "roll",
            "롤의 비판",
            "smb",
            "hml",
            "소형주",
            "대형주",
            "가치주",
            "성장주",
            "자산배분",
            "자산 배분",
            "종목선정",
            "종목 선정",
            "성과귀속",
            "성과 귀속",
            "벤치마크",
        ]
    ):
        return "portfolio_tool"
    if any(
        word in normalized
        for word in [
            "위험회피",
            "위험중립",
            "위험선호",
            "기대효용",
            "확실성등가",
            "위험프리미엄",
            "겜블",
            "보험료",
            "전망이론",
            "준거점",
            "손실회피",
            "부의 증감",
            "평가 손실",
            "화재",
            "주택",
            "행동재무",
            "행동 재무",
            "편향",
            "인지적 오류",
            "감정적 오류",
            "군중심리",
        ]
    ):
        return "risk_utility_tool"
    if any(
        word in normalized
        for word in [
            "배당할인",
            "항상성장",
            "주식가치",
            "주가",
            "npvgo",
            "per",
            "pbr",
            "psr",
            "pcr",
            "tobin",
            "ev/ebitda",
            "주가수익비율",
            "주가순자산비율",
            "시장가치비율",
            "배당성장률",
        ]
    ):
        return "valuation_tool"
    if any(word in normalized for word in ["증분현금흐름", "증분 현금흐름", "apv", "fte", "wacc법", "wacc 법", "조정현가", "조정 현가", "주주가치평가", "주주 가치 평가", "가중평균자본비용법", "ceq", "확실성등가", "확실성 등가", "eva", "mva", "rim", "경제적 부가가치", "시장부가가치", "시장 부가가치", "초과이익", "잔여이익", "잔여 이익", "npv 곡선", "피셔", "자본할당", "중복투자", "분할투자", "반복투자", "최소공배수", "무한반복", "연간균등가치", "aev", "투자기회선", "한계자본비용", "명목 현금흐름", "실질 현금흐름", "인플레이션", "비교기업", "대용기업", "투자안 베타", "프로젝트 베타", "목표 부채", "부채비율 유지", "이자비용 절세효과의 현재가치"]):
        return "capital_budgeting_tool"
    if (
        any(word in normalized for word in ["현재가치", "미래가치", "연금", "영구연금", "실효이자율", "표시이자율", "할인율", "복리", "유동성 선호", "정기예금", "원금의 두"])
        or any(word in normalized for word in ["pv", "fv", "ear", "apr", "annuity", "perpetuity"])
    ):
        return "time_value_tool"
    if any(word in normalized for word in ["npv", "순현재가치", "irr", "투자안", "회수기간", "증분현금흐름", "증분 현금흐름", "투자시점", "종료시점", "투자 종료", "최저가격", "잉여현금흐름", "free cash flow", "fcf", "fcff", "fcfe", "영업현금흐름", "주주 현금흐름", "주주현금흐름", "채권자 현금흐름", "채권자현금흐름", "apv", "fte", "wacc법", "wacc 법", "조정현가", "조정 현가", "주주가치평가", "주주 가치 평가", "가중평균자본비용법", "ceq", "확실성등가", "확실성 등가", "eva", "mva", "rim", "경제적 부가가치", "시장부가가치", "시장 부가가치", "초과이익", "잔여이익", "잔여 이익", "npv 곡선", "피셔", "자본할당", "중복투자", "분할투자", "반복투자", "최소공배수", "무한반복", "연간균등가치", "aev", "투자기회선", "한계자본비용", "명목 현금흐름", "실질 현금흐름", "인플레이션", "비교기업", "대용기업", "투자안 베타", "프로젝트 베타", "목표 부채", "부채비율 유지", "이자비용 절세효과의 현재가치"]):
        return "capital_budgeting_tool"
    if any(word in normalized for word in ["wacc", "자본비용", "타인자본", "자기자본", "레버리지", "영업위험", "재무위험", "dol", "dfl", "dcl", "ebit-eps", "ebit eps", "자본조달분기점", "재무손익분기점", "자본구조", "최적 자본 구조", "mm이론", "mm 1958", "mm 1963", "무부채기업", "부채기업", "수정 이론", "하마다", "hamada", "주식베타", "주식 베타", "무부채 베타", "법인세율 변화", "개인소득세", "이자소득세", "주식투자소득세", "밀러", "miller", "균형부채", "deangelo", "masulis", "디안젤로", "마술리스", "비부채성 감세", "대리비용", "위험선호", "과소투자", "재산도피", "자본조달순위", "pecking", "신호효과", "signaling", "순이익 접근", "순영업이익 접근", "전통적 접근", "miles", "ezzell", "harris", "pringle", "차익거래", "위험부채", "절세효과", "부채 사용", "이자비용 절세", "파산비용", "기대 파산"]):
        return "cost_of_capital_tool"
    if (
        any(word in normalized for word in ["기업가치", "주주가치", "이해관계자", "esg", "조달", "운용", "요구수익률"])
        or any(word in compact for word in ["재무관리목표", "재무관리의목표", "타인자본비용", "자기자본비용", "이익극대화", "회계적이익극대화"])
    ):
        return "finance_concept_tool"
    if any(word in normalized for word in ["wacc", "자본비용", "타인자본", "자기자본"]):
        return "cost_of_capital_tool"
    if any(word in normalized for word in ["roe", "roa", "재무비율"]):
        return "financial_ratio_tool"
    return "rag_only"


def run_tool(tool_name: str, question: str) -> dict:
    if tool_name == "capital_budgeting_tool":
        return analyze_capital_budgeting(question)
    if tool_name == "cost_of_capital_tool":
        return calculate_cost_of_capital(question)
    if tool_name == "finance_concept_tool":
        return explain_finance_concept(question)
    if tool_name == "financial_ratio_tool":
        return analyze_financial_ratios(question)
    if tool_name == "mergers_acquisitions_tool":
        return analyze_mergers_acquisitions(question)
    if tool_name == "portfolio_tool":
        return analyze_portfolio(question)
    if tool_name == "risk_utility_tool":
        return analyze_risk_utility(question)
    if tool_name == "time_value_tool":
        return analyze_time_value(question)
    if tool_name == "valuation_tool":
        return analyze_valuation(question)
    if tool_name == "working_capital_tool":
        return analyze_working_capital(question)
    return {"status": "no_calculation", "message": "관련 재무관리 기준 문서를 검색해 답변합니다."}


if __name__ == "__main__":
    user_question = input("질문을 입력하세요: ")
    result = answer_finance_question(user_question)
    print(result["answer"])
