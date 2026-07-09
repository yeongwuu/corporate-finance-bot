from llm_client import build_final_answer
from rag.simple_rag import search_knowledge
from tools.capital_budgeting_tool import analyze_capital_budgeting
from tools.cost_of_capital_tool import calculate_cost_of_capital
from tools.finance_concept_tool import explain_finance_concept
from tools.financial_ratio_tool import analyze_financial_ratios
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

    if any(word in normalized for word in ["운전자본", "현금전환주기", "ccc", "매출채권", "재고", "매입채무"]):
        return "working_capital_tool"
    if any(word in normalized for word in ["배당할인", "항상성장", "주식가치", "주가", "npvgo", "per", "pbr", "주가수익비율", "주가순자산비율"]):
        return "valuation_tool"
    if (
        any(word in normalized for word in ["현재가치", "미래가치", "연금", "영구연금", "실효이자율", "표시이자율", "할인율", "복리", "유동성 선호"])
        or any(word in normalized for word in ["pv", "fv", "ear", "apr", "annuity", "perpetuity"])
    ):
        return "time_value_tool"
    if any(word in normalized for word in ["npv", "순현재가치", "irr", "투자안", "회수기간"]):
        return "capital_budgeting_tool"
    if (
        any(word in normalized for word in ["잉여현금흐름", "free cash flow", "fcf", "기업가치", "주주가치", "이해관계자", "esg", "조달", "운용", "요구수익률"])
        or any(word in compact for word in ["재무관리목표", "재무관리의목표", "타인자본비용", "자기자본비용"])
    ):
        return "finance_concept_tool"
    if any(word in normalized for word in ["wacc", "자본비용", "타인자본", "자기자본", "capm"]):
        return "cost_of_capital_tool"
    if any(word in normalized for word in ["유동비율", "부채비율", "roe", "roa", "회전율", "재무비율"]):
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
