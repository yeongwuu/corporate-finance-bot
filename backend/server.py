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
    "SK하이닉스의 최근 2개년 유동비율과 당좌비율을 알려줘",
    "셀트리온의 최근 1년 주가 변동성과 최대낙폭(MDD)을 계산해줘",
    "한화에어로스페이스의 최근 5개년 매출 추이로 2026년 매출을 전망해줘",
    "LIG넥스원의 최근 3개년 주요 재무계정 추이를 분석해줘",
    "에스엠의 최근 1년 주가 수익률과 변동성을 계산해줘",
    "와이지엔터테인먼트의 최근 3개년 매출액과 영업이익을 비교해줘",
    "삼성전자의 최근 5개년 PER 추이를 계산해줘",
    "SK하이닉스의 최근 3년 주가 흐름을 차트로 보여줘",
    "셀트리온의 최근 3개년 부채비율과 ROE 추이를 분석해줘",
    "방산 산업의 최근 주요 동향과 뉴스 흐름을 분석해줘"
]

_cached_questions: list[str] = []
_last_refreshed = 0.0
_question_cache_lock = Lock()
_file_write_lock = Lock()
_last_recommended_questions: set[str] = set()
QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "data", "successful_questions.json")

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
            q.replace("의 최근 당기순이익을 알려줘", "의 최근 3개년 당기순이익 추이를 분석해줘").strip()
            for q in questions
            if isinstance(q, str) and q.strip()
        ]
        questions = list(dict.fromkeys(questions))
        if len(questions) < RECOMMENDED_QUESTION_POOL_SIZE:
            generated = _generate_question_pool(RECOMMENDED_QUESTION_POOL_SIZE)
            questions = list(dict.fromkeys([*questions, *generated]))[:RECOMMENDED_QUESTION_POOL_SIZE]

        if not os.path.exists(QUESTIONS_FILE) or len(questions) >= RECOMMENDED_QUESTION_POOL_SIZE:
            with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(questions, f, ensure_ascii=False, indent=2)


def _generate_question_pool(limit: int) -> list[str]:
    import sqlite3

    from company_data.financial_store import FinancialStatementStore

    company_templates = [
        "{company}의 최근 3개년 매출액과 영업이익 추이를 분석해줘",
        "{company}의 최근 5개년 주요 재무계정 추이를 분석해줘",
        "{company}의 최근 2개년 유동비율과 당좌비율을 알려줘",
        "{company}의 최근 3개년 부채비율과 ROE 추이를 분석해줘",
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
    curated_industries = [
        "반도체", "바이오", "방산", "자동차", "2차전지", "엔터테인먼트",
        "증권", "은행", "보험", "소프트웨어", "건설", "화학",
    ]

    companies = []
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
            db_industries = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT industry_name
                    FROM financial_items
                    WHERE industry_name != '' AND stock_code != ''
                    GROUP BY industry_name
                    HAVING COUNT(DISTINCT stock_code) >= 5
                    ORDER BY COUNT(DISTINCT stock_code) DESC
                    LIMIT 20
                    """
                ).fetchall()
            ]
            industries = list(dict.fromkeys([*curated_industries, *db_industries]))
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Failed to build recommendations from financial DB: %s", exc)

    companies = companies or fallback_companies
    candidates = [template.format(company=company) for company in companies for template in company_templates]
    candidates.extend(template.format(industry=industry) for industry in industries for template in industry_templates)
    candidates = list(dict.fromkeys([*DEFAULT_SEEDS, *candidates]))
    random.shuffle(candidates)
    return candidates[:limit]

def log_successful_question(question: str):
    _init_questions_file()
    cleaned = question.strip()
    if not cleaned or len(cleaned) < 5 or len(cleaned) > 100:
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
        except Exception as e:
            logger.error(f"Failed to log successful question: {e}")


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


def _question_family(question: str) -> str:
    compact = question.replace(" ", "").lower()
    if any(token in compact for token in [
        "dcf", "wacc", "영구성장률", "몬테카를로", "기대수익률분포",
        "스트레스", "복합충격", "최대샤프", "최소분산", "포트폴리오", "시나리오",
    ]):
        return "advanced"
    if "주가" in compact and any(token in compact for token in ["흐름", "변동성", "수익률", "최대낙폭", "mdd", "차트"]):
        return "stock"
    if any(token in compact for token in ["뉴스", "동향", "업황", "이슈"]):
        return "news"
    if any(token in compact for token in ["전망", "예측"]):
        return "advanced"
    if any(token in compact for token in ["유동비율", "당좌비율", "부채비율", "roe", "roa", "per", "pbr"]):
        return "ratio"
    if any(token in compact for token in ["업종", "산업", "대표기업", "상위"]):
        return "industry"
    return "financial"


def _replacement_question_index(questions: list[str], incoming: str) -> int:
    family_limits = {"stock": 30, "news": 25, "advanced": 35, "ratio": 45, "industry": 40, "financial": 70}
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
    """Return five diverse questions with stock, news, advanced, and top-company guarantees."""
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

        selected: list[str] = []
        required = [
            (_is_news_api_question, DEFAULT_SEEDS[-1]),
            (_is_stock_recommendation_question, "SK하이닉스의 최근 3년 주가 흐름을 차트로 보여줘"),
            (_is_advanced_recommendation_question, "SK하이닉스의 WACC를 7~11%, 영구성장률을 1~4%로 변경하면서 적정 주가 민감도 표를 만들어줘."),
        ]
        for predicate, fallback in required:
            candidates = [q for q in available if q not in selected and predicate(q)]
            if not candidates:
                candidates = [q for q in questions if q not in selected and predicate(q)]
            selected.append(random.choice(candidates) if candidates else fallback)

        if not any(_mentions_top_five_company(question) for question in selected):
            top_candidates = [q for q in available if q not in selected and _mentions_top_five_company(q)]
            if not top_candidates:
                top_candidates = [q for q in questions if q not in selected and _mentions_top_five_company(q)]
            selected.append(random.choice(top_candidates) if top_candidates else DEFAULT_SEEDS[0])

        neutral_candidates = [
            q for q in available
            if q not in selected
            and not _is_news_api_question(q)
            and not _is_stock_recommendation_question(q)
            and not _is_advanced_recommendation_question(q)
        ]
        needed = RECOMMENDED_QUESTION_COUNT - len(selected)
        candidate_pool = list(neutral_candidates)
        if len(candidate_pool) < needed:
            candidate_pool.extend(q for q in questions if q not in selected and q not in candidate_pool)
        selected.extend(random.sample(candidate_pool, min(needed, len(candidate_pool))))
            
        random.shuffle(selected)
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
        "dcf", "wacc", "영구성장률", "몬테카를로", "기대수익률분포",
        "스트레스", "복합충격", "최대샤프", "최소분산", "포트폴리오",
    ])


def _mentions_top_five_company(question: str) -> bool:
    return any(company in question for company in TOP_FIVE_COMPANIES)


def find_similar_successful_questions(user_question: str) -> list[str]:
    """Find the top 3 most semantically similar successful questions from database."""
    _init_questions_file()
    with _file_write_lock:
        try:
            with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
                questions = json.load(f)
        except Exception:
            questions = list(DEFAULT_SEEDS)

    def get_tokens(text: str) -> set[str]:
        tokens = re.findall(r'[가-힣a-zA-Z0-9]{2,}', text.lower())
        stops = {"최근", "가지고", "보여줘", "알려줘", "계산해줘", "분석해줘", "추이를", "어떻게", "얼마야", "알려줘"}
        return {t for t in tokens if t not in stops}

    user_tokens = get_tokens(user_question)
    if not user_tokens:
        return random.sample(questions, 3) if len(questions) >= 3 else list(DEFAULT_SEEDS[:3])

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

    if len(results) < 3:
        fillers = [q for q in DEFAULT_SEEDS if q not in results]
        results.extend(random.sample(fillers, 3 - len(results)))

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
            item = q.get()
            if item is None:
                break
            yield item

    return StreamingResponse(generator(), media_type="text/event-stream")


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
