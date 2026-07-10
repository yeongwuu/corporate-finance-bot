import re
from decimal import Decimal, ROUND_HALF_UP


def analyze_working_capital(question: str) -> dict:
    dio = find_days(question, ["재고일수", "DIO"])
    dso = find_days(question, ["매출채권회수기간", "DSO"])
    dpo = find_days(question, ["매입채무지급기간", "DPO"])
    inventory_days = find_days(question, ["재고자산회전기간", "재고자산 회전기간"])
    receivable_days = find_days(question, ["매출채권회수기간", "매출채권 회수기간"])

    if inventory_days is not None and receivable_days is not None and "영업순환주기" in question:
        operating_cycle = inventory_days + receivable_days
        return {
            "status": "ok",
            "summary": f"영업순환주기는 {format_days(operating_cycle)}입니다.",
            "steps": [
                "영업순환주기 = 재고자산회전기간 + 매출채권회수기간",
                f"영업순환주기 = {format_days(inventory_days)} + {format_days(receivable_days)} = {format_days(operating_cycle)}",
            ],
        }

    if None not in [dio, dso, dpo]:
        ccc = dio + dso - dpo
        return {
            "status": "ok",
            "summary": f"현금순환주기(CCC)는 {format_days(ccc)}입니다.",
            "steps": [
                "CCC = 재고일수 + 매출채권회수기간 - 매입채무지급기간",
                f"CCC = {format_days(dio)} + {format_days(dso)} - {format_days(dpo)} = {format_days(ccc)}",
            ],
        }

    return {
        "status": "need_more_data",
        "summary": "현금순환주기 계산에는 재고일수, 매출채권회수기간, 매입채무지급기간이 필요합니다.",
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
