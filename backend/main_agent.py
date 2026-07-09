from llm_client import build_final_answer
from rag.simple_rag import search_knowledge
from tools.capital_budgeting_tool import analyze_capital_budgeting
from tools.cost_of_capital_tool import calculate_cost_of_capital
from tools.financial_ratio_tool import analyze_financial_ratios
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

    if any(word in normalized for word in ["운전자본", "현금전환주기", "ccc", "매출채권", "재고", "매입채무"]):
        return "working_capital_tool"
    if any(word in normalized for word in ["npv", "순현재가치", "irr", "투자안", "회수기간"]):
        return "capital_budgeting_tool"
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
    if tool_name == "financial_ratio_tool":
        return analyze_financial_ratios(question)
    if tool_name == "working_capital_tool":
        return analyze_working_capital(question)
    return {"status": "no_calculation", "message": "관련 재무관리 기준 문서를 검색해 답변합니다."}


if __name__ == "__main__":
    user_question = input("질문을 입력하세요: ")
    result = answer_finance_question(user_question)
    print(result["answer"])
