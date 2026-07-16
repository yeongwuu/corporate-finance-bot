from rag.internal_rag import search_knowledge


def test_answer_policy_is_available_from_finance_basics():
    references = search_knowledge("재무 답변에서 계산 결과와 판단 기준을 어떻게 제시해?")

    assert references
    assert "finance_basics" in {reference["title"] for reference in references}


def test_working_capital_is_available_from_financial_ratios():
    references = search_knowledge("운전자본과 현금전환주기 CCC의 관계를 설명해줘")

    assert references
    assert references[0]["title"] == "financial_ratios"
