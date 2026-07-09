import os


def build_final_answer(question: str, tool_name: str, calculation: dict, references: list[dict]) -> str:
    if os.getenv("LLM_PROVIDER"):
        return build_llm_prompt(question, tool_name, calculation, references)
    return build_rule_based_answer(tool_name, calculation, references)


def build_rule_based_answer(tool_name: str, calculation: dict, references: list[dict]) -> str:
    lines = [
        f"사용 도구: {tool_name}",
        "",
        calculation.get("summary", calculation.get("message", "계산 결과가 없습니다.")),
    ]

    steps = calculation.get("steps", [])
    if steps:
        lines.append("")
        lines.append("계산 과정")
        lines.extend(f"- {step}" for step in steps)

    if references:
        lines.append("")
        lines.append("참고 기준")
        for reference in references[:3]:
            lines.append(f"- {reference['title']}: {reference['snippet']}")

    return "\n".join(lines)


def build_llm_prompt(question: str, tool_name: str, calculation: dict, references: list[dict]) -> str:
    return (
        "LLM 연결 지점입니다. 실무 배포 시 이 함수에서 사용하는 LLM SDK를 연결하세요.\n\n"
        f"질문: {question}\n"
        f"선택 도구: {tool_name}\n"
        f"계산 결과: {calculation}\n"
        f"검색 문서: {references}\n"
    )
