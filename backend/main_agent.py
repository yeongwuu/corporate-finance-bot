import time

from chart_builder import build_chart_spec
from llm_client import build_attachment_answer, build_final_answer
from rag.simple_rag import search_knowledge
from tools.capital_budgeting_tool import analyze_capital_budgeting
from tools.company_analysis_tool import analyze_company_financials
from tools.company_trend_tool import analyze_company_trend
from tools.cost_of_capital_tool import calculate_cost_of_capital
from tools.finance_concept_tool import explain_finance_concept
from tools.financial_ratio_tool import analyze_financial_ratios
from tools.forecast_tool import forecast_company_metric
from tools.industry_rank_tool import rank_industry_companies
from tools.mergers_acquisitions_tool import analyze_mergers_acquisitions
from tools.portfolio_tool import analyze_portfolio
from tools.risk_utility_tool import analyze_risk_utility
from tools.stock_price_tool import analyze_stock_price
from tools.time_value_tool import analyze_time_value
from tools.valuation_tool import analyze_valuation
from tools.working_capital_tool import analyze_working_capital


def answer_finance_question(question: str, history: list[dict] | None = None, attachment: dict | None = None) -> dict:
    started_at = time.perf_counter()
    trace = []
    if attachment:
        return answer_attachment_question(question, attachment, started_at)

    context_text = _build_context_text(history or []) if _should_use_context(question) else ""
    if context_text:
        trace.append(_trace_item("이전 질문 맥락 확인", "후속 질문 해석에 사용할 최근 사용자 질문을 반영했습니다.", started_at))
    effective_question = _with_context(question, context_text)

    step_started = time.perf_counter()
    tool_name = select_tool(effective_question)
    trace.append(_trace_item("분석 도구 선택", _tool_description(tool_name), step_started))

    step_started = time.perf_counter()
    knowledge_references = search_knowledge(effective_question)
    trace.append(_trace_item("재무 지식 검색", f"관련 기준 문서 {len(knowledge_references)}건을 확인했습니다.", step_started))

    step_started = time.perf_counter()
    calculation = run_tool(tool_name, effective_question)
    trace.append(_trace_item("데이터 분석 실행", _calculation_description(calculation), step_started))
    if context_text and isinstance(calculation, dict):
        calculation["conversation_context"] = context_text

    step_started = time.perf_counter()
    references = _combined_references(calculation, knowledge_references)
    trace.append(_trace_item("근거 병합", f"뉴스/공시/지식 근거 {len(references)}건을 답변 후보로 정리했습니다.", step_started))

    step_started = time.perf_counter()
    answer = build_final_answer(
        question=question,
        tool_name=tool_name,
        calculation=calculation,
        references=references,
    )
    trace.append(_trace_item("답변 생성", "계산 결과와 근거를 사용자 답변 문장으로 정리했습니다.", step_started))

    step_started = time.perf_counter()
    chart = build_chart_spec(tool_name, calculation)
    trace.append(_trace_item("그래프 구성", "표시할 그래프를 생성했습니다." if chart else "표시할 그래프가 필요한 질문은 아니었습니다.", step_started))
    trace.append(_trace_item("전체 처리 완료", f"총 {((time.perf_counter() - started_at) * 1000):.0f}ms가 걸렸습니다.", started_at))

    return {
        "question": question,
        "tool": tool_name,
        "answer": answer,
        "calculation": calculation,
        "references": references,
        "chart": chart,
        "trace": trace,
    }


def answer_attachment_question(question: str, attachment: dict, started_at: float | None = None) -> dict:
    started_at = started_at or time.perf_counter()
    trace = [_trace_item("파일 확인", f"{attachment.get('name', '첨부파일')}을 문제 풀이 입력으로 사용했습니다.", started_at)]
    calculation = {
        "status": "ok",
        "summary": "업로드한 파일을 바탕으로 문제 풀이를 시도했습니다.",
        "attachment": {
            "name": attachment.get("name"),
            "type": attachment.get("type"),
            "size": attachment.get("size"),
            "has_text": bool(attachment.get("text")),
            "has_binary": bool(attachment.get("data")),
        },
    }
    try:
        step_started = time.perf_counter()
        answer = build_attachment_answer(question, attachment)
        trace.append(_trace_item("파일 문제 풀이", "첨부파일과 질문을 함께 해석해 답변했습니다.", step_started))
    except Exception as exc:
        calculation["status"] = "missing_config"
        calculation["message"] = str(exc)
        answer = (
            "업로드한 파일을 분석하려면 LLM_PROVIDER, LLM_MODEL, LLM_API_KEY 설정이 필요합니다. "
            "이미지 문제는 비전 입력을 지원하는 모델을 사용해야 합니다."
        )
        trace.append(_trace_item("파일 문제 풀이 실패", str(exc), started_at))

    trace.append(_trace_item("전체 처리 완료", f"총 {((time.perf_counter() - started_at) * 1000):.0f}ms가 걸렸습니다.", started_at))
    return {
        "question": question,
        "tool": "attachment_solver",
        "answer": answer,
        "calculation": calculation,
        "references": [],
        "chart": None,
        "trace": trace,
    }


def _trace_item(label: str, detail: str, started_at: float) -> dict:
    return {
        "label": label,
        "detail": detail,
        "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
    }


def _tool_description(tool_name: str) -> str:
    descriptions = {
        "company_trend_tool": "기업 재무 추이와 최신 뉴스 흐름을 함께 보는 경로를 선택했습니다.",
        "company_analysis_tool": "기업 재무제표 주요 계정을 조회하는 경로를 선택했습니다.",
        "forecast_tool": "최근 재무 추이를 바탕으로 단순 전망을 계산하는 경로를 선택했습니다.",
        "financial_ratio_tool": "재무비율 계산 경로를 선택했습니다.",
        "industry_rank_tool": "산업/업종별 기업 순위를 조회하는 경로를 선택했습니다.",
        "valuation_tool": "기업가치평가 관련 경로를 선택했습니다.",
        "capital_budgeting_tool": "투자안 평가 관련 경로를 선택했습니다.",
        "portfolio_tool": "포트폴리오 분석 경로를 선택했습니다.",
        "cost_of_capital_tool": "자본비용 분석 경로를 선택했습니다.",
        "mergers_acquisitions_tool": "M&A 분석 경로를 선택했습니다.",
        "time_value_tool": "화폐의 시간가치 계산 경로를 선택했습니다.",
        "rag_only": "계산 도구 없이 재무 지식 검색 중심 경로를 선택했습니다.",
    }
    return descriptions.get(tool_name, f"{tool_name} 경로를 선택했습니다.")


def _calculation_description(calculation: dict) -> str:
    status = calculation.get("status", "unknown")
    company = calculation.get("company") or {}
    company_name = company.get("company_name")
    news_fetch = calculation.get("news_fetch") or {}
    parts = [f"상태: {status}"]
    if company_name:
        parts.append(f"기업: {company_name}")
    if calculation.get("period"):
        period = calculation["period"]
        parts.append(f"기간: {period.get('start_year')}~{period.get('end_year')}")
    if calculation.get("target_year"):
        parts.append(f"전망연도: {calculation.get('target_year')}")
    if news_fetch.get("status"):
        parts.append(f"뉴스: {news_fetch.get('status')}")
    return ", ".join(parts)


def _build_context_text(history: list[dict]) -> str:
    lines = []
    for item in history[-6:]:
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if role != "user" or not content:
            continue
        compact = " ".join(content.split())
        lines.append(compact[:220])
    return "\n".join(lines)


def _should_use_context(question: str) -> bool:
    normalized = question.lower().replace(" ", "")
    token_count = len(question.split())
    independent_terms = [
        "상위",
        "top",
        "랭킹",
        "순위",
        "목록",
        "리스트",
        "산업",
        "업종",
        "섹터",
        "시장",
        "기업들",
        "회사들",
    ]
    if any(term in normalized for term in independent_terms):
        return False

    period_only_terms = [
        "최근5개년",
        "최근3개년",
        "최근4개년",
        "최근2개년",
        "최근1년",
        "최근5년",
        "최근3년",
        "전년대비",
        "전년보다",
        "지난5년",
        "지난3년",
        "5개년",
        "3개년",
        "2021~2025",
        "2020~2025",
        "2019~2025",
    ]
    if any(term in normalized for term in period_only_terms):
        return True
    if token_count <= 4 and any(term in normalized for term in ["최근", "기간", "개년", "연도별", "추이", "성장률"]):
        return True

    follow_up_terms = [
        "그럼",
        "그러면",
        "그건",
        "그 회사",
        "같은",
        "동일",
        "이어서",
        "아까",
        "방금",
        "그 기간",
        "최근에도",
        "비교해",
        "영업이익은",
        "순이익은",
        "매출은",
        "주가는",
        "이익률은",
    ]
    return any(term.replace(" ", "") in normalized for term in follow_up_terms)


def _with_context(question: str, context_text: str) -> str:
    if not context_text:
        return question
    return (
        f"{question}\n\n"
        "이전 사용자 질문 맥락:\n"
        f"{context_text}\n\n"
        "위 맥락과 현재 질문이 같은 회사, 기간, 지표를 이어받는 후속 질문이면 그 맥락을 반영해 해석한다. "
        "현재 질문에 새 회사명이나 새 기간이 명시되어 있으면 현재 질문을 우선한다."
    )


def _combined_references(calculation: dict, knowledge_references: list[dict]) -> list[dict]:
    external_references = calculation.get("external_references") or []
    seen = set()
    combined = []
    for reference in [*external_references, *knowledge_references]:
        key = (
            reference.get("title"),
            reference.get("source_url"),
            reference.get("snippet"),
        )
        if key in seen:
            continue
        seen.add(key)
        combined.append(reference)
    return combined


def select_tool(question: str) -> str:
    normalized = question.lower()
    compact = normalized.replace(" ", "")

    if _is_forecast_question(normalized):
        return "forecast_tool"

    if _is_stock_price_question(normalized):
        return "stock_price_tool"

    if _is_industry_rank_question(normalized):
        return "industry_rank_tool"

    if _is_market_news_question(normalized):
        return "company_trend_tool"

    if _is_company_financial_comparison_question(normalized):
        return "company_trend_tool"

    if _is_company_profitability_trend_question(normalized):
        return "company_trend_tool"

    if any(word in normalized for word in ["비교기업", "대용기업", "투자안 베타", "프로젝트 베타", "조정현가", "apv", "목표 부채", "부채비율 유지", "이자비용 절세효과의 현재가치", "이자비용 절세효과 현재가치"]):
        return "capital_budgeting_tool"
    if any(word in normalized for word in ["m&a", "m＆a", "인수합병", "인수 합병", "합병", "흡수합병", "신설합병", "수직적 합병", "수평적 합병", "다각적 합병", "공개매수", "공개 매수", "곰의 포옹", "새벽의 기습", "lbo", "mbo", "차입매수", "차입 매수", "경영자매수", "적대적", "독약조항", "독약 풋", "황금낙하산", "백기사", "백지주", "황금주", "차등의결권", "팩맨", "왕관의 보석", "녹색편지", "행동주의 펀드", "토빈의 q", "저평가 가설", "경영자주의", "시너지 효과", "시너지 계산", "피인수기업", "경제성 평가", "인수 대가", "인수프리미엄", "합병 프리미엄", "주식교환", "주식 교환", "교환비율", "교환 비율", "현금지급", "현금 지급", "eps법", "주가법", "합병 후 eps", "합병후 eps", "합병 후 주가", "합병후 주가", "프리미엄률", "배당성장", "포이즌필", "포이즌 필", "신주인수권", "부의 이전", "무임승차", "사업구조 변경", "합병 후 표준편차", "합병 후 베타"]):
        return "mergers_acquisitions_tool"

    if (
        any(word in normalized for word in ["추이", "성장률", "cagr", "연도별", "기간별", "원인", "이유", "왜", "인사이트", "사업보고서", "뉴스", "최근", "최신", "분기", "분기실적"])
        and any(word in normalized for word in ["매출", "영업이익", "순이익", "현금흐름", "자산", "부채", "자본", "재무제표", "기업", "실적"])
        and not any(word in normalized for word in ["문제", "계산하시오", "구하시오", "공식"])
    ):
        return "company_trend_tool"

    if (
        any(
            word in normalized
            for word in [
                "재무제표",
                "주요계정",
                "주요 계정",
                "기업 분석",
                "회사 분석",
                "코스닥",
                "kosdaq",
                "매출액",
                "영업이익",
                "당기순이익",
                "자산총계",
                "부채총계",
                "자본총계",
                "재고자산",
                "매출채권",
                "영업활동현금흐름",
                "투자활동현금흐름",
                "재무활동현금흐름",
                "현금흐름",
            ]
        )
        and not any(word in normalized for word in ["문제", "계산하시오", "구하시오", "공식"])
    ):
        return "company_analysis_tool"

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


def _is_market_news_question(normalized: str) -> bool:
    market_terms = [
        "주가",
        "주식",
        "시가총액",
        "상승",
        "오를",
        "오르",
        "올라",
        "하락",
        "내릴",
        "내리",
        "떨어",
        "급등",
        "급락",
        "강세",
        "약세",
        "랠리",
        "반등",
        "조정",
        "전망",
    ]
    reason_terms = [
        "왜",
        "이유",
        "원인",
        "배경",
        "분석",
        "최근",
        "비교",
        "더",
        "생각",
        "궁금",
        "전망",
        "예상",
        "가능성",
        "뉴스",
        "기사",
        "이슈",
        "호재",
        "악재",
    ]
    return any(term in normalized for term in market_terms) and any(term in normalized for term in reason_terms)


def _is_forecast_question(normalized: str) -> bool:
    forecast_terms = [
        "예측",
        "전망",
        "추정",
        "forecast",
        "estimate",
        "내년",
        "다음해",
        "다음 해",
        "2026",
        "2027",
    ]
    metric_terms = [
        "매출",
        "영업이익",
        "순이익",
        "현금흐름",
        "자산",
        "부채",
        "자본",
        "실적",
    ]
    return any(term in normalized for term in forecast_terms) and any(term in normalized for term in metric_terms)


def _is_stock_price_question(normalized: str) -> bool:
    if not any(term in normalized for term in ["주가", "종가", "가격", "수익률"]):
        return False
    analysis_terms = [
        "그래프",
        "차트",
        "추이",
        "흐름",
        "변동",
        "변동하였",
        "변동했",
        "어떻게",
        "과거",
        "평균",
        "표준편차",
        "변동성",
        "백테스트",
        "백테스팅",
        "수익률",
        "mdd",
        "최대낙폭",
        "최근 1년",
        "최근 6개월",
        "최근 3개월",
        "최근 5년",
    ]
    reason_terms = ["왜", "이유", "원인", "배경", "호재", "악재", "뉴스", "기사"]
    return any(term in normalized for term in analysis_terms) and not any(term in normalized for term in reason_terms)


def _is_industry_rank_question(normalized: str) -> bool:
    compact = normalized.replace(" ", "")
    direct_terms = [
        "업종별",
        "산업군",
        "그룹화",
        "그룹핑",
        "같은업종",
        "속한업종",
        "무슨업종",
        "어떤업종",
        "어느업종",
        "무슨산업",
        "어떤산업",
        "어느산업",
    ]
    if any(term in compact for term in direct_terms):
        return True
    rank_terms = ["상위", "top", "순위", "랭킹", "랭크"]
    group_terms = ["산업", "업종", "섹터", "기업", "회사", "산업군"]
    return any(term in normalized for term in rank_terms) and any(term in normalized for term in group_terms)


def _is_company_financial_comparison_question(normalized: str) -> bool:
    comparison_terms = ["비교", "vs", "대비"]
    financial_terms = [
        "매출",
        "영업이익",
        "순이익",
        "이익률",
        "원가율",
        "판관비율",
        "수익성",
        "roe",
        "roa",
        "자산",
        "부채",
        "재무",
        "실적",
    ]
    return any(term in normalized for term in comparison_terms) and any(term in normalized for term in financial_terms)


def _is_company_profitability_trend_question(normalized: str) -> bool:
    ratio_terms = [
        "수익성",
        "이익률",
        "영업마진",
        "순이익마진",
        "원가율",
        "매출원가율",
        "판관비율",
        "판매비와관리비율",
        "판매관리비율",
        "매출원가",
        "판관비",
        "grossmargin",
        "operatingmargin",
        "netmargin",
        "roe",
        "roa",
        "총자산이익률",
        "자기자본이익률",
    ]
    trend_terms = ["추이", "최근", "연도별", "계산", "분석"]
    return any(term in normalized for term in ratio_terms) and any(term in normalized for term in trend_terms)


def run_tool(tool_name: str, question: str) -> dict:
    if tool_name == "capital_budgeting_tool":
        return analyze_capital_budgeting(question)
    if tool_name == "company_analysis_tool":
        return analyze_company_financials(question)
    if tool_name == "company_trend_tool":
        return analyze_company_trend(question)
    if tool_name == "cost_of_capital_tool":
        return calculate_cost_of_capital(question)
    if tool_name == "finance_concept_tool":
        return explain_finance_concept(question)
    if tool_name == "financial_ratio_tool":
        return analyze_financial_ratios(question)
    if tool_name == "forecast_tool":
        return forecast_company_metric(question)
    if tool_name == "industry_rank_tool":
        return rank_industry_companies(question)
    if tool_name == "mergers_acquisitions_tool":
        return analyze_mergers_acquisitions(question)
    if tool_name == "portfolio_tool":
        return analyze_portfolio(question)
    if tool_name == "risk_utility_tool":
        return analyze_risk_utility(question)
    if tool_name == "stock_price_tool":
        return analyze_stock_price(question)
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
