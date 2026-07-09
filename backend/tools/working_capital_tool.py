import re
from decimal import Decimal, ROUND_HALF_UP


def analyze_working_capital(question: str) -> dict:
    dio = find_days(question, ["재고일수", "DIO"])
    dso = find_days(question, ["매출채권회수기간", "DSO"])
    dpo = find_days(question, ["매입채무지급기간", "DPO"])

    if None not in [dio, dso, dpo]:
        ccc = dio + dso - dpo
        return {
            "status": "ok",
            "summary": f"현금전환주기(CCC)는 {format_days(ccc)}입니다.",
            "steps": [
                "CCC = 재고일수 + 매출채권회수기간 - 매입채무지급기간",
                f"CCC = {format_days(dio)} + {format_days(dso)} - {format_days(dpo)} = {format_days(ccc)}",
            ],
        }

    return {
        "status": "need_more_data",
        "summary": "현금전환주기 계산에는 재고일수, 매출채권회수기간, 매입채무지급기간이 필요합니다.",
        "steps": [],
    }


def find_days(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        match = re.search(rf"{label}[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*일?", text, re.IGNORECASE)
        if match:
            return Decimal(match.group(1))
    return None


def format_days(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}일"
