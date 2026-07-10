def explain_finance_concept(question: str) -> dict:
    normalized = question.lower()
    compact = normalized.replace(" ", "")

    if any(term in normalized for term in ["잉여현금흐름", "free cash flow", "fcf"]):
        return {
            "status": "ok",
            "summary": "잉여현금흐름(FCF)은 영업자산에서 발생한 현금흐름 중 자금 조달과 직접 관련이 없는 현금흐름입니다.",
            "steps": [
                "기업은 채권자와 주주 등 자금 공급자로부터 자금을 조달합니다.",
                "조달한 자금으로 영업자산에 투자합니다.",
                "영업자산에서 발생한 현금흐름 중 조달 활동과 직접 관련 없는 부분이 FCF입니다.",
                "FCF는 이자, 배당, 유보 등의 방식으로 채권자와 주주에게 귀속됩니다.",
            ],
        }

    if any(term in compact for term in ["이익극대화", "회계적이익극대화"]):
        return {
            "status": "ok",
            "summary": "회계적 이익 극대화는 재무관리 목표로 한계가 있어 기업가치 극대화가 더 적절합니다.",
            "steps": [
                "경영자의 회계처리 의도에 따라 이익의 크기가 달라질 수 있습니다.",
                "화폐의 시간가치를 반영하지 못합니다.",
                "단기간의 회계성과에 치중할 가능성이 있습니다.",
                "미래 현금흐름의 불확실성을 충분히 고려하지 못합니다.",
            ],
        }

    if any(term in normalized for term in ["재무관리 목표", "기업가치", "주주가치", "이해관계자", "esg"]) or any(
        term in compact for term in ["재무관리목표", "재무관리의목표"]
    ):
        return {
            "status": "ok",
            "summary": "재무관리의 기본 목표는 기업가치 극대화이며, 부채가 일정하면 주주가치 극대화와 연결됩니다.",
            "steps": [
                "NPV가 증가하는 실물자산 투자는 기업가치를 증가시킵니다.",
                "부채가 일정하면 기업가치 증가는 주주가치 증가로 이어집니다.",
                "자본잠식 상태에서는 기업가치 증가분이 먼저 채권자 가치 증가로 귀속될 수 있습니다.",
                "최근에는 ESG를 포함한 이해관계자 가치 극대화 관점도 함께 고려합니다.",
            ],
        }

    if any(term in normalized for term in ["조달", "운용", "자금 공급자", "채권자", "주주"]):
        return {
            "status": "ok",
            "summary": "기업 재무활동은 자금 조달, 자산 운용, 현금흐름 창출, 자금 공급자 배분으로 이어집니다.",
            "steps": [
                "채권자와 주주 등으로부터 자금을 조달합니다.",
                "조달한 자금으로 영업자산을 구입하거나 투자합니다.",
                "영업자산에서 현금흐름을 창출합니다.",
                "창출된 현금흐름은 이자, 배당, 유보 등의 형태로 처리됩니다.",
            ],
        }

    if any(term in normalized for term in ["자본비용", "수익률", "요구수익률", "타인자본", "자기자본"]):
        return {
            "status": "ok",
            "summary": "기업의 자본비용은 투자자 관점에서는 요구수익률입니다.",
            "steps": [
                "타인자본 또는 부채는 투자자 관점에서 채권입니다.",
                "자기자본은 투자자 관점에서 주식 또는 지분입니다.",
                "타인자본비용은 채권자의 요구수익률입니다.",
                "자기자본비용은 주주의 요구수익률입니다.",
            ],
        }

    return {
        "status": "no_calculation",
        "summary": "재무관리 기초 개념 질문입니다. 관련 지식 문서를 참고해 답변합니다.",
        "steps": [],
    }
