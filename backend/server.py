import logging
import os
import random
import re
import time
from datetime import datetime
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from korean_particles import normalize_company_pair_particles
from main_agent import answer_finance_question


app = FastAPI(title="Corporate Finance Bot API")

logger = logging.getLogger("corporate_finance_bot")
logging.basicConfig(level=logging.INFO)


def _cors_origins() -> list[str]:
    raw_origins = os.getenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173",
    )
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

    raw_hostnames = os.getenv("BACKEND_CORS_HOSTNAMES", "")
    for hostname in [host.strip() for host in raw_hostnames.split(",") if host.strip()]:
        if hostname.startswith(("http://", "https://")):
            origins.append(hostname)
        else:
            origins.append(f"https://{hostname}")

    return origins


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "Unhandled request error method=%s path=%s elapsed_ms=%.2f",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "요청 처리 중 오류가 발생했습니다.",
            },
            headers={"X-Process-Time-Ms": f"{elapsed_ms:.2f}"},
        )

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
    logger.info(
        "Request completed method=%s path=%s status=%s elapsed_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Request validation failed method=%s path=%s errors=%s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": "입력값을 확인하세요.",
            "details": exc.errors(),
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=os.getenv("BACKEND_CORS_ORIGIN_REGEX") or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str
    history: list[dict[str, str]] = []
    attachment: dict | None = None


class FailedQuestionLogRequest(BaseModel):
    question: str
    answer: str
    tool: str | None = None
    status: str | None = None
    consent: bool


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


RECOMMENDED_QUESTION_TTL_SECONDS = 10 * 60
RECOMMENDED_QUESTION_COUNT = 5
RECOMMENDED_QUESTION_POOL_SIZE = 200
TOP_FIVE_COMPANIES = ["삼성전자", "SK하이닉스", "삼성전기", "현대차", "LG에너지솔루션"]
DEFAULT_SEEDS = [
    "삼성전자의 최근 3개년 매출액과 영업이익 추이를 분석해줘",
    "SK하이닉스의 최근 2개년 유동비율, 당좌비율과 부채비율 추이를 분석해줘",
    "셀트리온의 최근 1년 주가 변동성과 최대낙폭(MDD)을 계산해줘",
    "한화에어로스페이스의 최근 5개년 매출 추이로 2026년 매출을 전망해줘",
    "LIG넥스원의 최근 3개년 주요 재무지표 추이를 분석해줘",
    "에스엠의 최근 1년 주가 수익률과 변동성을 계산해줘",
    "와이지엔터테인먼트의 최근 3개년 매출액과 영업이익을 비교해줘",
    "삼성전자의 최근 5개년 PER 추이를 계산해줘",
    "SK하이닉스의 최근 3년 주가 흐름을 차트로 보여줘",
    "셀트리온의 최근 3개년 매출총이익률, 영업이익률과 당기순이익률 추이를 분석해줘",
    "방산 산업의 최근 주요 동향과 뉴스 흐름을 분석해줘"
]
CURATED_RECOMMENDATION_INDUSTRIES = [
    "반도체", "바이오", "방산", "자동차", "2차전지", "엔터테인먼트",
    "증권", "은행", "보험", "소프트웨어", "건설", "화학",
]
ADVANCED_QUESTION_SEEDS = [
    "삼성전자의 최신 사업보고서 주석에서 CapEx와 운전자본 계획을 추출하고, 향후 10년 FCF를 예측해 적정 주가를 계산해줘.",
    "SK하이닉스의 WACC를 7~11%, 영구성장률을 1~4%로 변경하면서 적정 주가 민감도 표를 만들어줘.",
    "삼성전자·SK하이닉스·삼성전기의 최근 5년 주가를 이용해 최대 샤프지수 포트폴리오와 최소분산 포트폴리오를 구성해줘.",
    "원/달러 환율 급락, 기준금리 상승, 반도체 가격 하락이 동시에 발생하면 삼성전자의 영업이익과 적정 주가가 얼마나 하락할지 분석해줘.",
    "삼성전자와 SK하이닉스의 향후 수익률 분포를 몬테카를로 시뮬레이션으로 비교해줘.",
    "현대차의 WACC를 7~11%, 영구성장률을 1~4%로 변경하면서 적정 주가 민감도 표를 만들어줘.",
    "LG에너지솔루션의 매출 성장률과 영업이익률이 동시에 하락하는 스트레스 시나리오를 분석해줘.",
    "삼성전자·SK하이닉스·삼성전기의 최근 3년 주가로 위험 대비 수익률이 가장 높은 포트폴리오를 구성해줘.",
    "삼성전기의 향후 10년 FCF를 예측하고 WACC와 영구성장률에 따른 적정 주가를 계산해줘.",
    "SK하이닉스의 환율과 반도체 가격 변동에 따른 영업이익 시나리오를 분석해줘.",
    "현대차·기아·현대모비스의 최근 5년 주가를 이용해 최대 샤프지수 포트폴리오와 최소분산 포트폴리오를 구성해줘.",
    "삼성전자 DCF 가치평가에서 매출 성장률과 영업이익률 변화가 적정 주가에 미치는 영향을 분석해줘.",
]
VALUATION_STRESS_QUESTION_SEEDS = [
    "삼성전자의 최신 사업보고서 주석에서 CapEx와 운전자본 계획을 추출하고, 향후 10년 FCF를 예측해 적정 주가를 계산해줘.",
    "SK하이닉스의 WACC를 7~11%, 영구성장률을 1~4%로 변경하면서 적정 주가 민감도 표를 만들어줘.",
    "원/달러 환율 급락, 기준금리 상승, 반도체 가격 하락이 동시에 발생하면 삼성전자의 영업이익과 적정 주가가 얼마나 하락할지 분석해줘.",
    "현대차의 WACC를 7~11%, 영구성장률을 1~4%로 변경하면서 적정 주가 민감도 표를 만들어줘.",
    "LG에너지솔루션의 매출 성장률과 영업이익률이 동시에 하락하는 스트레스 시나리오를 분석해줘.",
    "삼성전기의 향후 10년 FCF를 예측하고 WACC와 영구성장률에 따른 적정 주가를 계산해줘.",
    "삼성전자 DCF 가치평가에서 매출 성장률과 영업이익률 변화가 적정 주가에 미치는 영향을 분석해줘.",
    "기준금리가 1%p 상승하고 원/달러 환율이 10% 오르면 현대차의 영업이익과 적정 주가는 어떻게 변할까?",
    "삼성전자의 WACC를 6~10%, 영구성장률을 1~4%로 변경해 적정 주가 민감도를 분석해줘.",
    "LG에너지솔루션의 WACC를 7~11%, 영구성장률을 1~4%로 변경해 적정 주가 민감도 표를 만들어줘.",
    "삼성전기의 WACC를 7~10%, 영구성장률을 1~3%로 변경해 적정 주가 민감도를 분석해줘.",
    "기아의 WACC를 7~11%, 영구성장률을 1~4%로 변경해 적정 주가 민감도 표를 만들어줘.",
    "삼성전자의 향후 10년 FCF를 예측하고 DCF 방식으로 적정 주가를 계산해줘.",
    "SK하이닉스의 향후 10년 FCF를 예측하고 DCF 방식으로 적정 주가를 계산해줘.",
    "현대차의 향후 10년 FCF를 예측하고 WACC와 영구성장률을 반영한 적정 주가를 계산해줘.",
    "LG에너지솔루션의 향후 10년 FCF를 예측하고 DCF 방식으로 적정 주가를 계산해줘.",
    "기아의 향후 10년 FCF를 예측하고 적정 주가를 계산해줘.",
    "기준금리가 1%p 상승하고 원/달러 환율이 10% 오르면 기아의 영업이익과 적정가치는 어떻게 변할까?",
    "기준금리가 1%p 상승하고 원/달러 환율이 10% 하락하면 LG에너지솔루션의 영업이익과 적정가치는 어떻게 변할까?",
    "기준금리가 0.5%p 상승하고 원/달러 환율이 8% 오르면 삼성전기의 영업이익과 적정가치는 어떻게 변할까?",
    "기준금리 상승과 원/달러 환율 하락이 동시에 발생하면 삼성전자의 영업이익과 적정가치 변화를 분석해줘.",
    "원/달러 환율 급락, 기준금리 상승, 반도체 가격 하락이 동시에 발생하면 SK하이닉스의 영업이익과 적정 주가가 얼마나 하락할지 분석해줘.",
    "삼성전자 DCF에서 WACC 상승과 영구성장률 하락이 적정 주가에 미치는 스트레스를 분석해줘.",
    "SK하이닉스 DCF에서 매출 성장률 둔화와 영업이익률 하락이 적정가치에 미치는 영향을 분석해줘.",
    "현대차 DCF에서 매출 성장률과 영업이익률이 동시에 하락하는 스트레스 시나리오를 분석해줘.",
]
OTHER_QUESTION_SEEDS = [
    "NPV와 IRR의 차이와 투자안 선택 기준을 설명해줘.",
    "회수기간법과 할인회수기간법의 차이를 설명해줘.",
    "명목이자율과 실효이자율의 차이를 예시로 설명해줘.",
    "영구연금과 성장영구연금의 현재가치 공식을 비교해줘.",
    "CAPM의 가정과 현실적인 한계를 설명해줘.",
    "체계적 위험과 비체계적 위험의 차이를 설명해줘.",
    "샤프지수와 트레이너지수의 차이를 설명해줘.",
    "젠센의 알파가 의미하는 바를 설명해줘.",
    "효율적 투자선과 무차별곡선의 관계를 설명해줘.",
    "블랙숄즈 모형으로 콜옵션 가격을 계산할 때 필요한 변수를 알려줘.",
    "콜옵션의 델타와 감마가 의미하는 위험을 설명해줘.",
    "풋콜패리티를 이용한 차익거래 원리를 설명해줘.",
    "채권 듀레이션과 볼록성의 차이를 설명해줘.",
    "금리가 상승할 때 채권 가격이 하락하는 이유를 설명해줘.",
    "합병 시너지와 합병 NPV의 관계를 설명해줘.",
    "현금 인수와 주식교환 인수의 장단점을 비교해줘.",
    "대리인 문제와 배당정책의 관계를 설명해줘.",
    "정보비대칭이 기업의 자금조달 순서에 미치는 영향을 설명해줘.",
    "경제적 부가가치와 시장부가가치의 차이를 설명해줘.",
    "민감도 분석과 시뮬레이션 분석의 차이를 설명해줘.",
]

_cached_questions: list[str] = []
_last_refreshed = 0.0
_question_cache_lock = Lock()
_file_write_lock = Lock()
_last_recommended_questions: set[str] = set()
QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "data", "successful_questions.json")
VERIFIED_SUCCESSFUL_QUESTIONS_FILE = os.path.join(
    os.path.dirname(__file__), "data", "verified_successful_questions.json"
)

def _init_questions_file():
    os.makedirs(os.path.dirname(QUESTIONS_FILE), exist_ok=True)
    with _file_write_lock:
        try:
            if os.path.exists(QUESTIONS_FILE):
                with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
                    questions = json.load(f)
            else:
                questions = list(DEFAULT_SEEDS)
        except Exception:
            questions = list(DEFAULT_SEEDS)

        questions = [
            normalize_company_pair_particles(
                q.replace("의 최근 당기순이익을 알려줘", "의 최근 3개년 당기순이익 추이를 분석해줘").strip()
            )
            for q in questions
            if isinstance(q, str) and q.strip()
        ]
        questions = [
            q for q in questions
            if _is_recommendation_question_eligible(q)
        ]
        questions = list(dict.fromkeys([*VALUATION_STRESS_QUESTION_SEEDS, *OTHER_QUESTION_SEEDS, *ADVANCED_QUESTION_SEEDS, *questions]))
        questions = _limit_recommendation_families(questions)
        if len(questions) < RECOMMENDED_QUESTION_POOL_SIZE:
            generated = _generate_question_pool(RECOMMENDED_QUESTION_POOL_SIZE)
            questions = list(dict.fromkeys([*questions, *generated]))
            questions = _limit_recommendation_families(questions)
        questions = questions[:RECOMMENDED_QUESTION_POOL_SIZE]

        with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)


def _generate_question_pool(limit: int) -> list[str]:
    import sqlite3

    from company_data.financial_store import FinancialStatementStore

    company_templates = [
        "{company}의 최근 3개년 매출액과 영업이익 추이를 분석해줘",
        "{company}의 최근 5개년 주요 재무지표 추이를 분석해줘",
        "{company}의 최근 2개년 유동비율, 당좌비율과 부채비율 추이를 분석해줘",
        "{company}의 최근 3개년 매출총이익률, 영업이익률과 당기순이익률 추이를 분석해줘",
        "{company}의 최근 1년 주가 변동성과 최대낙폭(MDD)을 계산해줘",
        "{company}의 최근 3년 주가 흐름을 차트로 보여줘",
        "{company}의 최근 5개년 매출 추이로 2026년 매출을 전망해줘",
        "{company}의 최근 3개년 당기순이익 추이를 분석해줘",
    ]
    industry_templates = [
        "{industry} 업종 대표 기업의 매출을 비교해줘",
        "{industry} 업종의 최근 동향과 뉴스 흐름을 분석해줘",
        "{industry} 업종의 매출 상위 5개 기업을 알려줘",
    ]
    fallback_companies = ["삼성전자", "SK하이닉스", "셀트리온", "한화시스템", "LIG넥스원"]
    curated_industries = CURATED_RECOMMENDATION_INDUSTRIES

    companies = []
    company_industries: list[tuple[str, str]] = []
    industries = list(curated_industries)
    try:
        store = FinancialStatementStore()
        store.ensure_database()
        conn = sqlite3.connect(store.db_path)
        try:
            companies = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT company_name
                    FROM financial_items
                    WHERE stock_code != ''
                      AND company_name NOT LIKE '%스팩%'
                      AND company_name NOT LIKE '%기업인수목적%'
                    GROUP BY stock_code, company_name
                    HAVING COUNT(DISTINCT fiscal_year) >= 5
                    ORDER BY RANDOM()
                    LIMIT 80
                    """
                ).fetchall()
            ]
            company_industries = [
                (str(row[0]), str(row[1]))
                for row in conn.execute(
                    """
                    SELECT company_name, industry_name
                    FROM financial_items
                    WHERE stock_code != ''
                      AND industry_name != ''
                      AND company_name NOT LIKE '%스팩%'
                      AND company_name NOT LIKE '%기업인수목적%'
                    GROUP BY stock_code, company_name, industry_name
                    HAVING COUNT(DISTINCT fiscal_year) >= 5
                    ORDER BY industry_name, RANDOM()
                    """
                ).fetchall()
            ]
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Failed to build recommendations from financial DB: %s", exc)

    companies = companies or fallback_companies
    candidates = [template.format(company=company) for company in companies for template in company_templates]
    by_industry: dict[str, list[str]] = {}
    for company_name, industry_name in company_industries:
        by_industry.setdefault(industry_name, []).append(company_name)
    for industry_companies in by_industry.values():
        unique_companies = list(dict.fromkeys(industry_companies))
        random.shuffle(unique_companies)
        for index in range(0, len(unique_companies) - 1, 2):
            first, second = unique_companies[index:index + 2]
            candidates.extend([
                f"{first}과 {second}의 최근 3개년 매출액과 영업이익을 비교해줘",
                f"{first}과 {second}의 최근 2년 주가 흐름을 비교해줘",
            ])
    candidates.extend(template.format(industry=industry) for industry in industries for template in industry_templates)
    candidates = list(dict.fromkeys(
        normalize_company_pair_particles(candidate)
        for candidate in [*DEFAULT_SEEDS, *VALUATION_STRESS_QUESTION_SEEDS, *OTHER_QUESTION_SEEDS, *ADVANCED_QUESTION_SEEDS, *candidates]
    ))
    random.shuffle(candidates)
    return candidates[:limit]

def log_successful_question(question: str):
    _init_questions_file()
    cleaned = normalize_company_pair_particles(question.strip())
    if not cleaned or len(cleaned) < 5 or len(cleaned) > 100:
        return
    if not _comparison_pair_is_same_industry(cleaned):
        return
    with _file_write_lock:
        try:
            if os.path.exists(QUESTIONS_FILE):
                with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
                    questions = json.load(f)
            else:
                questions = list(DEFAULT_SEEDS)

            questions = list(dict.fromkeys(q for q in questions if isinstance(q, str) and q.strip()))
            if cleaned not in questions:
                while len(questions) >= RECOMMENDED_QUESTION_POOL_SIZE:
                    questions.pop(_replacement_question_index(questions, cleaned))
                questions.append(cleaned)
            while len(questions) > RECOMMENDED_QUESTION_POOL_SIZE:
                removable = [index for index, item in enumerate(questions) if item != cleaned]
                questions.pop(random.choice(removable) if removable else 0)
            with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(questions, f, ensure_ascii=False, indent=2)
            _append_verified_successful_question(cleaned)
        except Exception as e:
            logger.error(f"Failed to log successful question: {e}")


def _append_verified_successful_question(question: str) -> None:
    try:
        if os.path.exists(VERIFIED_SUCCESSFUL_QUESTIONS_FILE):
            with open(VERIFIED_SUCCESSFUL_QUESTIONS_FILE, "r", encoding="utf-8") as f:
                questions = json.load(f)
        else:
            questions = []
        questions = [q for q in questions if isinstance(q, str) and q.strip()]
        questions = list(dict.fromkeys([*questions, question]))[-300:]
        with open(VERIFIED_SUCCESSFUL_QUESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.error("Failed to log verified successful question: %s", exc)


def _remove_unanswerable_recommendation(question: str) -> None:
    cleaned = normalize_company_pair_particles(question.strip())
    if not cleaned:
        return
    with _file_write_lock:
        for path in (QUESTIONS_FILE, VERIFIED_SUCCESSFUL_QUESTIONS_FILE):
            try:
                if not os.path.exists(path):
                    continue
                with open(path, "r", encoding="utf-8") as file:
                    questions = json.load(file)
                filtered = [item for item in questions if item != cleaned]
                if len(filtered) == len(questions):
                    continue
                with open(path, "w", encoding="utf-8") as file:
                    json.dump(filtered, file, ensure_ascii=False, indent=2)
            except Exception as exc:
                logger.warning("Failed to remove an unanswerable recommendation: %s", exc)


def _is_verified_successful_result(question: str, result: dict) -> bool:
    calculation = result.get("calculation") or {}
    if calculation.get("status") != "ok":
        return False

    answer = str(result.get("answer") or "")
    failure_phrases = [
        "답변 데이터를 수신하지 못했습니다",
        "찾지 못했습니다",
        "데이터가 부족",
        "어떤 기업이 궁금하세요",
        "오류가 발생",
    ]
    if not answer or any(phrase in answer for phrase in failure_phrases):
        return False

    compact = question.replace(" ", "").lower()
    forecast_intent = any(token in compact for token in ["예측", "전망", "추정", "내년", "다음해"])
    financial_metric = any(
        token in compact
        for token in ["매출", "영업이익", "순이익", "현금흐름", "자산", "부채", "자본", "실적"]
    )
    if forecast_intent and financial_metric:
        return (
            result.get("tool") == "forecast_tool"
            and isinstance(calculation.get("forecast"), dict)
            and len(calculation.get("series") or []) >= 3
            and bool(calculation.get("target_year"))
        )

    if forecast_intent and "주가" in compact:
        return result.get("tool") == "stock_price_tool" and bool(calculation.get("forecast_values"))

    return True


def _comparison_pair_is_same_industry(question: str) -> bool:
    """Allow named two-company recommendations only when both share one DB industry."""
    if "비교" not in question:
        return True
    pair_match = re.search(r"^\s*(.+?)(?:과|와)\s+(.+?)(?:의|를|을)\s+", question)
    if not pair_match:
        return True
    try:
        from company_data.financial_store import FinancialStatementStore

        store = FinancialStatementStore()
        first = store.resolve_company(pair_match.group(1).strip())
        second = store.resolve_company(pair_match.group(2).strip())
    except Exception:
        return True
    if not first or not second:
        return True
    return first.industry_name == second.industry_name


RECOMMENDATION_CATEGORIES = (
    "financial_metrics",
    "stock_investment",
    "valuation_stress",
    "news",
    "other",
)


def _question_family(question: str) -> str:
    compact = question.replace(" ", "").lower()
    if any(token in compact for token in [
        "dcf", "fcf", "wacc", "영구성장률", "적정가치", "적정주가",
        "스트레스", "복합충격", "민감도",
    ]):
        return "valuation_stress"
    if any(token in compact for token in ["뉴스", "동향", "업황", "이슈"]):
        return "news"
    if any(token in compact for token in [
        "주가", "종가", "최대낙폭", "mdd", "포트폴리오", "최대샤프", "최소분산",
        "몬테카를로", "기대수익률분포", "유리할확률",
    ]):
        return "stock_investment"
    if any(token in compact for token in [
        "재무지표", "매출", "영업이익", "당기순이익", "순이익", "실적", "현금흐름",
        "자산", "부채", "자본", "성장률", "cagr",
        "유동비율", "당좌비율", "부채비율", "매출총이익률", "영업이익률",
        "당기순이익률", "순이익률", "roe", "roa", "per", "pbr",
    ]):
        return "financial_metrics"
    return "other"


def _is_recommendation_question_eligible(question: str) -> bool:
    """Exclude raw DB industry labels that have not been verified as answerable."""
    is_industry_prompt = "업종" in question or "산업 대표" in question
    if not is_industry_prompt:
        return True
    return any(
        question.startswith(f"{industry} ")
        for industry in CURATED_RECOMMENDATION_INDUSTRIES
    )


def _limit_recommendation_families(questions: list[str]) -> list[str]:
    """Keep the five recommendation categories large enough for varied rotation."""
    limits = {"valuation_stress": 25, "news": 35}
    counts: dict[str, int] = {}
    selected: list[str] = []
    for question in questions:
        family = _question_family(question)
        if counts.get(family, 0) >= limits.get(family, RECOMMENDED_QUESTION_POOL_SIZE):
            continue
        selected.append(question)
        counts[family] = counts.get(family, 0) + 1
    return selected


def _replacement_question_index(questions: list[str], incoming: str) -> int:
    family_limits = {
        "financial_metrics": 65,
        "stock_investment": 45,
        "valuation_stress": 25,
        "news": 35,
        "other": 30,
    }
    grouped: dict[str, list[int]] = {}
    for index, question in enumerate(questions):
        grouped.setdefault(_question_family(question), []).append(index)
    overrepresented = [
        (len(indices) - family_limits.get(family, 40), indices)
        for family, indices in grouped.items()
        if len(indices) > family_limits.get(family, 40)
    ]
    if overrepresented:
        return random.choice(max(overrepresented, key=lambda item: item[0])[1])
    incoming_family = _question_family(incoming)
    same_family = grouped.get(incoming_family) or []
    return random.choice(same_family) if same_family else random.randrange(len(questions))

FAILED_QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "data", "failed_questions.json")

def log_failed_question(question: str, status: str, error_message: str):
    os.makedirs(os.path.dirname(FAILED_QUESTIONS_FILE), exist_ok=True)
    cleaned = question.strip()
    if not cleaned:
        return
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question": cleaned,
        "status": status,
        "error_message": error_message[:300]
    }
    with _file_write_lock:
        try:
            if os.path.exists(FAILED_QUESTIONS_FILE):
                with open(FAILED_QUESTIONS_FILE, "r", encoding="utf-8") as f:
                    failed_list = json.load(f)
            else:
                failed_list = []
            failed_list.append(log_entry)
            if len(failed_list) > 300:
                failed_list = failed_list[-300:]
            with open(FAILED_QUESTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(failed_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to log failed question: {e}")

def _generate_guaranteed_questions() -> list[str]:
    """Return exactly one question from each of the five product categories."""
    global _last_recommended_questions
    _init_questions_file()
    with _file_write_lock:
        try:
            with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
                questions = json.load(f)
        except Exception:
            questions = list(DEFAULT_SEEDS)
    
    questions = list(dict.fromkeys([*questions, *DEFAULT_SEEDS]))
    with _question_cache_lock:
        available = [question for question in questions if question not in _last_recommended_questions]
        if len(available) < RECOMMENDED_QUESTION_COUNT:
            available = questions

        fallbacks = {
            "financial_metrics": DEFAULT_SEEDS[0],
            "stock_investment": "SK하이닉스의 최근 3년 주가 흐름을 차트로 보여줘",
            "valuation_stress": VALUATION_STRESS_QUESTION_SEEDS[1],
            "news": DEFAULT_SEEDS[-1],
            "other": "NPV와 IRR의 차이를 설명해줘",
        }
        selected: list[str] = []
        for category in RECOMMENDATION_CATEGORIES:
            candidates = [q for q in available if q not in selected and _question_family(q) == category]
            if not candidates:
                candidates = [q for q in questions if q not in selected and _question_family(q) == category]
            selected.append(random.choice(candidates) if candidates else fallbacks[category])

        _last_recommended_questions = set(selected)
    return selected


def _is_news_api_question(question: str) -> bool:
    compact = question.replace(" ", "").lower()
    return "뉴스" in compact and any(token in compact for token in ["동향", "이슈", "흐름", "업황"])


def _is_stock_recommendation_question(question: str) -> bool:
    compact = question.replace(" ", "").lower()
    if _is_news_api_question(question) or _is_advanced_recommendation_question(question):
        return False
    return any(token in compact for token in ["주가", "종가", "최대낙폭", "mdd"]) and any(
        token in compact for token in ["추이", "흐름", "변동성", "수익률", "예측", "전망", "차트", "계산"]
    )


def _is_advanced_recommendation_question(question: str) -> bool:
    compact = question.replace(" ", "").lower()
    return any(token in compact for token in [
        "dcf", "fcf", "wacc", "영구성장률", "몬테카를로", "기대수익률분포",
        "스트레스", "복합충격", "최대샤프", "최소분산", "포트폴리오",
    ])


def _mentions_top_five_company(question: str) -> bool:
    return any(company in question for company in TOP_FIVE_COMPANIES)


def find_similar_successful_questions(user_question: str) -> list[str]:
    """Find similar questions that previously completed with a verified successful result."""
    with _file_write_lock:
        try:
            with open(VERIFIED_SUCCESSFUL_QUESTIONS_FILE, "r", encoding="utf-8") as f:
                questions = json.load(f)
        except Exception:
            questions = []

    questions = [q for q in questions if isinstance(q, str) and q.strip()]
    if not questions:
        return []

    def get_tokens(text: str) -> set[str]:
        tokens = re.findall(r'[가-힣a-zA-Z0-9]{2,}', text.lower())
        stops = {"최근", "가지고", "보여줘", "알려줘", "계산해줘", "분석해줘", "추이를", "어떻게", "얼마야", "알려줘"}
        return {t for t in tokens if t not in stops}

    user_tokens = get_tokens(user_question)
    if not user_tokens:
        return random.sample(questions, min(3, len(questions)))

    scored_questions = []
    for q in questions:
        if q.strip() == user_question.strip():
            continue
        q_tokens = get_tokens(q)
        intersection = user_tokens.intersection(q_tokens)
        score = len(intersection)
        union = user_tokens.union(q_tokens)
        jaccard = score / len(union) if union else 0.0
        scored_questions.append((q, score, jaccard))

    scored_questions.sort(key=lambda x: (x[1], x[2]), reverse=True)
    results = [q for q, s, j in scored_questions[:3]]

    return results[:3]


@app.get("/api/recommended-questions")
@app.get("/api/trending-questions", include_in_schema=False)
def get_recommended_questions() -> dict:
    # Generate dynamically shuffled fresh questions on every request
    questions = _generate_guaranteed_questions()
    return {
        "questions": questions,
        "refresh_interval_seconds": 0,
        "pool_size": _recommended_question_pool_size(),
    }


def _recommended_question_pool_size() -> int:
    _init_questions_file()
    try:
        with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
            return len(set(json.load(f)))
    except Exception:
        return len(set(DEFAULT_SEEDS))


import queue
import threading
import json
from fastapi.responses import StreamingResponse


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    q = queue.Queue()

    def run_agent():
        try:
            def on_step(step_index: int, message: str | None = None):
                q.put(f"event: step\ndata: {json.dumps({'step_index': step_index, 'message': message}, ensure_ascii=False)}\n\n")

            res = answer_finance_question(
                question=request.question,
                history=request.history,
                attachment=request.attachment,
                on_step=on_step
            )
            result_status = (res.get("calculation") or {}).get("status") or res.get("status")
            if result_status == "ok" and not request.attachment and _is_verified_successful_result(request.question, res):
                log_successful_question(request.question)
            elif result_status in {"needs_company", "no_data", "missing_data", "missing_shares"}:
                _remove_unanswerable_recommendation(request.question)
            res["suggestions"] = find_similar_successful_questions(request.question)
            q.put(f"event: result\ndata: {json.dumps(res, ensure_ascii=False)}\n\n")
        except Exception as e:
            logger.exception("Agent execution failed")
            suggestions = find_similar_successful_questions(request.question)[:2]
            q.put(
                f"event: error\ndata: "
                f"{json.dumps({'message': str(e), 'suggestions': suggestions}, ensure_ascii=False)}\n\n"
            )
        finally:
            q.put(None)

    threading.Thread(target=run_agent, daemon=True).start()

    def generator():
        while True:
            try:
                item = q.get(timeout=10)
            except queue.Empty:
                # Prevent free-hosting proxies from closing long-running DART/market-data requests.
                yield ": keep-alive\n\n"
                continue
            if item is None:
                break
            yield item

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/failed-question-log")
def save_failed_question_with_consent(request: FailedQuestionLogRequest) -> dict:
    if not request.consent:
        return {"status": "skipped", "message": "동의하지 않아 수집하지 않았습니다."}
    if not request.question.strip() or not request.answer.strip():
        return JSONResponse(status_code=422, content={"status": "error", "message": "질문과 답변이 필요합니다."})

    log_failed_question(
        question=request.question,
        status=request.status or "error",
        error_message=request.answer,
    )
    return {"status": "ok", "message": "동의한 실패 질문을 기록했습니다."}
