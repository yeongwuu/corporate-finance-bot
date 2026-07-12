import re
import urllib.request
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from company_data.financial_store import FinancialStatementStore
from tools.stock_price_tool import _download_naver_price_data, _download_price_data, _to_yahoo_ticker


def analyze_valuation(question: str) -> dict:
    market_trend = calculate_market_ratio_trend(question)
    if market_trend["status"] in {"ok", "missing_shares", "price_fetch_error"}:
        return market_trend

    if "유보율" in question and "per" in question.lower() and "pbr" in question.lower() and "roe" in question.lower():
        return calculate_growth_from_per_pbr(question)

    market_ratios = calculate_market_value_ratios(question)
    if market_ratios["status"] == "ok":
        return market_ratios

    if is_constant_growth_question(question):
        return calculate_constant_growth_stock_value(question)

    return {
        "status": "no_calculation",
        "summary": "주식가치는 배당할인모형에 따라 미래 배당금을 주주의 요구수익률로 할인해 계산합니다.",
        "steps": [
            "배당할인모형: P0 = Σ Dt / (1 + k)^t",
            "항상성장모형: P0 = EPS1 * (1 - b) / (k - g)",
            "성장률: g = 유보율 * ROE",
            "NPVGO = 성장모형 주가 - 무성장모형 주가",
        ],
    }


def calculate_market_ratio_trend(question: str) -> dict[str, Any]:
    ratio_keys = _extract_market_ratio_keys(question)
    if not ratio_keys or not _asks_ratio_trend(question):
        return {"status": "no_calculation", "summary": "", "steps": []}

    store = FinancialStatementStore()
    try:
        company = store.resolve_company(question)
    except FileNotFoundError as exc:
        return {
            "status": "missing_data",
            "summary": "재무제표 데이터에서 회사를 확인하지 못했습니다.",
            "steps": [str(exc)],
        }
    if not company:
        return {
            "status": "needs_company",
            "summary": "PER/PBR/PSR 추이를 계산할 회사명을 찾지 못했습니다.",
            "steps": ["예: 삼성전자 최근 7개년 PER 변동, SK하이닉스 2021~2025년 PBR 추이"],
        }

    available_years = store.available_years(company.stock_code)
    if not available_years:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 재무제표 연도 데이터를 찾지 못했습니다.",
            "steps": [],
            "company": company.__dict__,
        }

    start_year, end_year, period_label = _extract_year_period(question, available_years)
    account_keys = _required_accounts_for_market_ratios(ratio_keys)
    financial_rows = store.get_account_series(company.stock_code, account_keys, start_year, end_year)
    shares = _fetch_listed_shares(company.stock_code)
    if not shares:
        return {
            "status": "missing_shares",
            "summary": f"{company.company_name}의 PER/PBR/PSR 추이를 계산하려면 상장주식수 데이터가 필요합니다.",
            "steps": [
                "PER/PBR/PSR은 연도별 시가총액과 재무제표 계정을 결합해 계산합니다.",
                "시가총액 = 연도말 종가 * 상장주식수",
                "네이버 금융에서 상장주식수를 확인하지 못했습니다.",
            ],
            "company": company.__dict__,
            "ratio_keys": ratio_keys,
        }

    rows = []
    price_errors = []
    for row in financial_rows:
        fiscal_year = int(row["year"])
        close = _fetch_year_end_close(company.stock_code, company.market, fiscal_year)
        if close is None:
            price_errors.append(str(fiscal_year))
            continue
        market_cap = close * shares
        ratio_row = {
            "year": fiscal_year,
            "close": close,
            "shares": shares,
            "market_cap": market_cap,
            "ratios": {},
        }
        for ratio_key in ratio_keys:
            value = _calculate_market_ratio_value(ratio_key, market_cap, row)
            if value is None:
                continue
            ratio_row["ratios"][ratio_key] = {
                "label": _market_ratio_label(ratio_key),
                "value": value,
                "display": format_number_float(value),
            }
        if ratio_row["ratios"]:
            rows.append(ratio_row)

    if not rows:
        return {
            "status": "price_fetch_error" if price_errors else "no_data",
            "summary": f"{company.company_name}의 {period_label} PER/PBR/PSR 계산에 필요한 결합 데이터를 만들지 못했습니다.",
            "steps": [
                "필요 데이터: 연도별 종가, 상장주식수, 순이익/자본총계/매출액",
                f"주가 조회 실패 연도: {', '.join(price_errors)}" if price_errors else "계산 가능한 재무제표 계정이 부족합니다.",
            ],
            "company": company.__dict__,
            "ratio_keys": ratio_keys,
        }

    labels = ", ".join(_market_ratio_label(key) for key in ratio_keys)
    steps = [
        f"조회 대상: {company.company_name}({company.stock_code}), {period_label}",
        f"상장주식수: {shares:,.0f}주",
        "시가총액은 연도말 종가와 상장주식수를 곱해 추정했습니다.",
        "계산식: PER = 시가총액 / 당기순이익, PBR = 시가총액 / 자본총계, PSR = 시가총액 / 매출액",
    ]
    for row in rows:
        ratio_text = ", ".join(f"{item['label']} {item['display']}" for item in row["ratios"].values())
        steps.append(f"{row['year']}년: 연도말 종가 {_format_krw(row['close'])}, 시가총액 {_format_amount_float(row['market_cap'])}, {ratio_text}")
    if price_errors:
        steps.append(f"주가를 가져오지 못해 제외한 연도: {', '.join(price_errors)}")

    return {
        "status": "ok",
        "mode": "market_ratio_trend",
        "summary": f"{company.company_name}의 {period_label} {labels} 추이를 계산했습니다.",
        "steps": steps,
        "company": company.__dict__,
        "period": {"start_year": rows[0]["year"], "end_year": rows[-1]["year"], "source": period_label},
        "ratio_keys": ratio_keys,
        "market_ratio_series": rows,
    }


def calculate_constant_growth_stock_value(question: str) -> dict:
    eps1 = find_money(question, ["eps", "주당 이익", "주당순이익", "주당 순이익"])
    retention = find_percent(question, ["유보율", "재투자"])
    roe = find_percent(question, ["roe", "자기자본에 대한 투자수익률", "투자수익률", "재투자수익률"])
    required_return = find_percent(question, ["적정 할인율", "할인율", "주주의 요구수익률", "요구수익률"])

    if None in [eps1, retention, roe, required_return]:
        return {
            "status": "need_more_data",
            "summary": "항상성장모형 계산에는 EPS1, 유보율, ROE, 주주의 요구수익률이 필요합니다.",
            "steps": [],
        }

    b = retention / Decimal("100")
    r = roe / Decimal("100")
    k = required_return / Decimal("100")
    growth = b * r

    if k <= growth:
        return {
            "status": "need_more_data",
            "summary": "항상성장모형은 주주의 요구수익률이 성장률보다 커야 계산할 수 있습니다.",
            "steps": [f"k = {format_percent(k * Decimal('100'))}", f"g = {format_percent(growth * Decimal('100'))}"],
        }

    dividend1 = eps1 * (Decimal("1") - b)
    growth_value = dividend1 / (k - growth)
    no_growth_value = eps1 / k
    npvgo = growth_value - no_growth_value
    per = growth_value / eps1
    pbr = per * r

    return {
        "status": "ok",
        "summary": (
            f"주식가치는 {format_money(growth_value)}, NPVGO는 {format_money(npvgo)}, "
            f"PER은 {format_number(per)}, PBR은 {format_number(pbr)}입니다."
        ),
        "steps": [
            f"성장률 g = 유보율 {retention}% * ROE {roe}% = {format_percent(growth * Decimal('100'))}",
            f"1년 말 배당금 D1 = EPS1 * (1 - b) = {format_money(eps1)} * (1 - {retention}%) = {format_money(dividend1)}",
            f"성장모형 주가 P0 = D1 / (k - g) = {format_money(dividend1)} / ({required_return}% - {format_percent(growth * Decimal('100'))}) = {format_money(growth_value)}",
            f"무성장 주가 = EPS1 / k = {format_money(eps1)} / {required_return}% = {format_money(no_growth_value)}",
            f"NPVGO = 성장모형 주가 - 무성장 주가 = {format_money(growth_value)} - {format_money(no_growth_value)} = {format_money(npvgo)}",
            f"PER = P0 / EPS1 = {format_number(per)}",
            f"PBR = PER * ROE = {format_number(per)} * {roe}% = {format_number(pbr)}",
        ],
    }


def is_constant_growth_question(question: str) -> bool:
    normalized = question.lower()
    return any(term in normalized for term in ["eps", "주당 이익", "주당순이익", "유보율", "배당성향", "npvgo", "per", "pbr"])


def calculate_market_value_ratios(question: str) -> dict:
    ratios = []
    steps = []

    stock_price = find_money(question, ["현재 주가", "주가"])
    eps = find_money(question, ["기대 주당순이익", "eps", "주당순이익"])
    bps = find_money(question, ["주당 자기자본 장부가치", "bps", "주당순자산"])
    sps = find_money(question, ["기대 주당매출액", "sps", "주당매출액"])
    cps = find_money(question, ["주당현금흐름", "cps"])
    equity_market_value = find_money(question, ["자기자본 시장가치", "시가총액"])
    expected_net_income = find_money(question, ["기대 당기순이익", "당기순이익", "순이익"])
    sales = find_money(question, ["기대 매출액", "매출액"])
    operating_cash_flow = find_money(question, ["영업현금흐름"])
    replacement_cost = find_money(question, ["대체원가", "대체 비용", "총대체비용"])
    debt = find_money(question, ["차입금"])
    cash = find_money(question, ["현금및현금성자산", "현금"])
    pretax_income = find_money(question, ["세전순이익"])
    interest_expense = find_money(question, ["이자비용"])
    depreciation = find_money(question, ["감가상각비와 무형자산상각비", "감가상각비", "상각비"])

    if stock_price is not None and eps:
        per = stock_price / eps
        ratios.append(f"PER {format_number(per)}")
        steps.append(f"PER = 현재 주가 / 기대 EPS = {format_number(per)}")
    elif equity_market_value is not None and expected_net_income:
        per = equity_market_value / expected_net_income
        ratios.append(f"PER {format_number(per)}")
        steps.append(f"PER = 자기자본 시장가치 / 기대 당기순이익 = {format_number(per)}")

    if stock_price is not None and bps:
        pbr = stock_price / bps
        ratios.append(f"PBR {format_number(pbr)}")
        steps.append(f"PBR = 현재 주가 / BPS = {format_number(pbr)}")

    if stock_price is not None and sps:
        psr = stock_price / sps
        ratios.append(f"PSR {format_number(psr)}")
        steps.append(f"PSR = 현재 주가 / 기대 주당매출액 = {format_number(psr)}")
    elif equity_market_value is not None and sales:
        psr = equity_market_value / sales
        ratios.append(f"PSR {format_number(psr)}")
        steps.append(f"PSR = 자기자본 시장가치 / 기대 매출액 = {format_number(psr)}")

    if stock_price is not None and cps:
        pcr = stock_price / cps
        ratios.append(f"PCR {format_number(pcr)}")
        steps.append(f"PCR = 현재 주가 / 주당현금흐름 = {format_number(pcr)}")
    elif equity_market_value is not None and operating_cash_flow:
        pcr = equity_market_value / operating_cash_flow
        ratios.append(f"PCR {format_number(pcr)}")
        steps.append(f"PCR = 자기자본 시장가치 / 영업현금흐름 = {format_number(pcr)}")

    if equity_market_value is not None and replacement_cost:
        tobins_q = equity_market_value / replacement_cost
        ratios.append(f"Tobin's q {format_number(tobins_q)}")
        steps.append(f"Tobin's q = 시장가치 / 대체원가 = {format_number(tobins_q)}")

    if (
        equity_market_value is not None
        and debt is not None
        and cash is not None
        and pretax_income is not None
        and interest_expense is not None
        and depreciation is not None
    ):
        ev = equity_market_value + debt - cash
        ebitda = pretax_income + interest_expense + depreciation
        ev_to_ebitda = ev / ebitda
        ratios.append(f"EV/EBITDA {format_number(ev_to_ebitda)}")
        steps.append(f"EV = 시가총액 + 차입금 - 현금및현금성자산 = {format_money(ev)}")
        steps.append(f"EBITDA = 세전순이익 + 이자비용 + 감가상각비와 무형자산상각비 = {format_money(ebitda)}")
        steps.append(f"EV/EBITDA = {format_number(ev_to_ebitda)}")

    if ratios:
        return {"status": "ok", "summary": ", ".join(ratios) + "입니다.", "steps": steps}

    return {"status": "no_calculation", "summary": "", "steps": []}


def calculate_growth_from_per_pbr(question: str) -> dict:
    per = find_labeled_number(question, ["PER"])
    pbr = find_labeled_number(question, ["PBR"])
    retention = find_percent(question, ["유보율", "재투자"])

    if per is not None and pbr is not None and retention is not None:
        roe = pbr / per
        growth = roe * retention / Decimal("100")
        required_return = growth + (Decimal("1") - retention / Decimal("100")) / per
        no_growth_per = Decimal("1") / required_return
        return {
            "status": "ok",
            "summary": (
                f"ROE는 {format_percent(roe * Decimal('100'))}, 배당성장률은 {format_percent(growth * Decimal('100'))}, "
                f"할인율은 {format_percent(required_return * Decimal('100'))}, 무성장 PER은 {format_number(no_growth_per)}입니다."
            ),
            "steps": [
                f"ROE = PBR / PER = {format_number(pbr)} / {format_number(per)} = {format_percent(roe * Decimal('100'))}",
                f"배당성장률 g = ROE * 유보율 = {format_percent(roe * Decimal('100'))} * {retention}% = {format_percent(growth * Decimal('100'))}",
                f"PER = (1 - b) / (k - g)이므로 k = g + (1 - b) / PER = {format_percent(required_return * Decimal('100'))}",
                f"무성장 PER = 1 / k = {format_number(no_growth_per)}",
            ],
        }

    return {
        "status": "need_more_data",
        "summary": "PER/PBR 역산에는 PER, PBR, 유보율이 필요합니다.",
        "steps": [],
    }


def _extract_market_ratio_keys(question: str) -> list[str]:
    normalized = question.lower().replace(" ", "")
    keys = []
    if "per" in normalized or "주가수익비율" in normalized:
        keys.append("per")
    if "pbr" in normalized or "주가순자산" in normalized:
        keys.append("pbr")
    if "psr" in normalized or "주가매출" in normalized:
        keys.append("psr")
    if any(token in normalized for token in ["시장가치비율", "밸류에이션배수", "valuationmultiple", "주요배수"]):
        keys.extend(["per", "pbr", "psr"])
    deduped = []
    for key in keys:
        if key not in deduped:
            deduped.append(key)
    return deduped


def _asks_ratio_trend(question: str) -> bool:
    normalized = question.lower().replace(" ", "")
    return any(token in normalized for token in ["추이", "변동", "변화", "최근", "연도별", "기간별", "그래프", "비교"])


def _extract_year_period(question: str, available_years: list[int]) -> tuple[int, int, str]:
    years = [int(year) for year in re.findall(r"20[0-3]\d", question)]
    min_year, max_year = min(available_years), max(available_years)
    if len(years) >= 2:
        start_year, end_year = min(years[:2]), max(years[:2])
        start_year = max(start_year, min_year)
        end_year = min(end_year, max_year)
        return start_year, end_year, f"{start_year}~{end_year}년"
    if len(years) == 1:
        year = min(max(years[0], min_year), max_year)
        return year, year, f"{year}년"
    match = re.search(r"최근\s*(\d+)\s*(?:개년|년)", question)
    if match:
        count = max(1, int(match.group(1)))
        start_year = max(min_year, max_year - count + 1)
        return start_year, max_year, f"최근 {count}개년"
    start_year = max(min_year, max_year - 4)
    return start_year, max_year, "기본값: 최근 5개년"


def _required_accounts_for_market_ratios(ratio_keys: list[str]) -> list[str]:
    required = []
    mapping = {
        "per": ["net_income"],
        "pbr": ["total_equity"],
        "psr": ["revenue"],
    }
    for ratio_key in ratio_keys:
        for account_key in mapping.get(ratio_key, []):
            if account_key not in required:
                required.append(account_key)
    return required


def _calculate_market_ratio_value(ratio_key: str, market_cap: float, row: dict[str, Any]) -> float | None:
    denominator_key = {
        "per": "net_income",
        "pbr": "total_equity",
        "psr": "revenue",
    }.get(ratio_key)
    if not denominator_key:
        return None
    account = row.get(denominator_key)
    amount = account.get("amount") if isinstance(account, dict) else None
    if amount in (None, 0):
        return None
    return market_cap / float(amount)


def _fetch_year_end_close(stock_code: str, market: str | None, fiscal_year: int) -> float | None:
    start = date(fiscal_year, 12, 1)
    end = date(fiscal_year, 12, 31)
    try:
        frame = _download_naver_price_data(stock_code, start, end)
    except Exception:
        frame = None
    if frame is not None and not frame.empty:
        return float(frame["Close"].iloc[-1])
    try:
        frame = _download_price_data(_to_yahoo_ticker(stock_code, market), start, end)
    except Exception:
        frame = None
    if frame is not None and not frame.empty:
        return float(frame["Close"].iloc[-1])
    return None


def _fetch_listed_shares(stock_code: str) -> float | None:
    url = f"https://finance.naver.com/item/main.naver?code={stock_code.zfill(6)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read().decode(charset, errors="ignore")
    except Exception:
        return None

    patterns = [
        r"상장주식수</th>\s*<td[^>]*>\s*<em[^>]*>([0-9,]+)</em>",
        r"상장주식수[^0-9]{0,80}([0-9,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.S)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def _market_ratio_label(ratio_key: str) -> str:
    return {"per": "PER", "pbr": "PBR", "psr": "PSR"}.get(ratio_key, ratio_key.upper())


def _format_krw(value: float) -> str:
    return f"{round(value):,}원"


def _format_amount_float(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1_0000_0000_0000:
        return f"{sign}{amount / 1_0000_0000_0000:.2f}조원"
    if amount >= 1_0000_0000:
        return f"{sign}{amount / 1_0000_0000:.2f}억원"
    return f"{sign}{amount:,.0f}원"


def format_number_float(value: float) -> str:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize().to_eng_string()


def find_money(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        pattern = rf"{re.escape(label)}[^0-9￦₩만원]*[￦₩]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(만|원)?"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = Decimal(match.group(1).replace(",", ""))
            unit = match.group(2)
            if unit == "만":
                return value * Decimal("10000")
            return value
    return None


def find_percent(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        pattern = rf"{re.escape(label)}[^0-9%]*([0-9]+(?:\.[0-9]+)?)\s*%"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return Decimal(match.group(1))
    return None


def find_labeled_number(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}[^0-9]*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
        if match:
            return Decimal(match.group(1))
    return None


def format_money(value: Decimal) -> str:
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"￦{rounded:,.0f}"


def format_percent(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


def format_number(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
