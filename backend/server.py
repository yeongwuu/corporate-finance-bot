import logging
import os
import smtplib
import time
from email.message import EmailMessage

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


class FeedbackEmailRequest(BaseModel):
    question: str
    answer: str
    tool: str | None = None
    status: str | None = None
    consent: bool


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict:
    return answer_finance_question(request.question, history=request.history)


@app.post("/api/feedback-email")
def send_feedback_email(request: FeedbackEmailRequest) -> dict:
    if not request.consent:
        return {"status": "skipped", "message": "사용자 동의가 없어 전송하지 않았습니다."}

    if not request.question.strip() or not request.answer.strip():
        return {"status": "error", "message": "질문과 답변 내용이 필요합니다."}

    result = _send_feedback_email(request)
    status_code = 200 if result["status"] == "ok" else 500
    return JSONResponse(status_code=status_code, content=result)


def _send_feedback_email(request: FeedbackEmailRequest) -> dict:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("SMTP_FROM_EMAIL") or username
    to_email = os.getenv("FEEDBACK_EMAIL_TO", "11xcv@naver.com")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() != "false"

    if not all([host, username, password, from_email]):
        return {
            "status": "missing_config",
            "message": "이메일 전송 환경변수 SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL 설정이 필요합니다.",
        }

    message = EmailMessage()
    message["Subject"] = "[Corporate Finance Bot] 분석 실패/개선 필요 질문"
    message["From"] = from_email
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                "사용자가 수집에 동의한 질문/답변입니다.",
                "",
                f"Tool: {request.tool or '-'}",
                f"Status: {request.status or '-'}",
                "",
                "[Question]",
                request.question.strip(),
                "",
                "[Answer]",
                request.answer.strip(),
            ]
        )
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
    except Exception:
        logger.exception("Feedback email send failed")
        return {"status": "error", "message": "피드백 이메일 전송에 실패했습니다."}

    return {"status": "ok", "message": "피드백 이메일을 전송했습니다."}
