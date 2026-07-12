import logging
import os
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from main_agent import answer_finance_question


app = FastAPI(title="Corporate Finance Bot API")

logger = logging.getLogger("corporate_finance_bot")
logging.basicConfig(level=logging.INFO)
FEEDBACK_LOG_PATH = Path(__file__).resolve().parent / "data" / "feedback_failures.log"
BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent


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


class FeedbackEmailRequest(BaseModel):
    question: str
    answer: str
    attachmentName: str | None = None
    tool: str | None = None
    status: str | None = None
    consent: bool


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


import queue
import threading
import json
from fastapi.responses import StreamingResponse


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    q = queue.Queue()

    def run_agent():
        try:
            def on_step(step_index: int):
                q.put(f"event: step\ndata: {json.dumps({'step_index': step_index})}\n\n")

            res = answer_finance_question(
                question=request.question,
                history=request.history,
                attachment=request.attachment,
                on_step=on_step
            )
            q.put(f"event: result\ndata: {json.dumps(res, ensure_ascii=False)}\n\n")
        except Exception as e:
            logger.exception("Agent execution failed")
            q.put(f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n")
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


@app.post("/api/feedback-email")
def send_feedback_email(request: FeedbackEmailRequest) -> dict:
    if not request.consent:
        return {"status": "skipped", "message": "사용자 동의가 없어 전송하지 않았습니다."}

    if not request.question.strip() or not request.answer.strip():
        return {"status": "error", "message": "질문과 답변 내용이 필요합니다."}

    result = _send_feedback_email(request)
    status_code = 200 if result["status"] in {"ok", "missing_config"} else 500
    return JSONResponse(status_code=status_code, content=result)


def _send_feedback_email(request: FeedbackEmailRequest) -> dict:
    username = _first_config("SMTP_USERNAME", "SMTP_USER", "SMTP_EMAIL", "NAVER_EMAIL", "NAVER_USERNAME")
    password = _first_config("SMTP_PASSWORD", "SMTP_PASS", "SMTP_APP_PASSWORD", "NAVER_APP_PASSWORD", "NAVER_PASSWORD")
    host = _get_config("SMTP_HOST") or _default_smtp_host(username)
    port = _parse_int_config("SMTP_PORT", 587)
    from_email = _get_config("SMTP_FROM_EMAIL") or _get_config("SMTP_FROM") or username
    to_email = _get_config("FEEDBACK_EMAIL_TO") or _get_config("FEEDBACK_TO") or "11xcv@naver.com"
    use_tls = (_get_config("SMTP_USE_TLS") or "true").lower() != "false"
    use_ssl = (_get_config("SMTP_USE_SSL") or "").lower() == "true" or port == 465

    if not all([host, username, password, from_email]):
        _write_feedback_fallback(request, "missing_smtp_config")
        return {
            "status": "missing_config",
            "message": "SMTP 설정이 없어 이메일은 전송하지 못했습니다. 피드백 내용은 서버 로그에 저장했습니다.",
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
                f"Attachment: {request.attachmentName or '-'}",
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
        smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_class(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if use_tls and not use_ssl:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:
        logger.exception("Feedback email send failed")
        _write_feedback_fallback(request, f"smtp_send_failed: {_smtp_error_summary(exc)}")
        return {
            "status": "error",
            "message": "피드백 이메일 전송에 실패해 서버 로그에 저장했습니다.",
            "detail": _smtp_error_summary(exc),
        }

    return {"status": "ok", "message": "피드백 이메일을 전송했습니다."}


def _write_feedback_fallback(request: FeedbackEmailRequest, reason: str) -> None:
    payload = (
        f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {reason}\n"
        f"Tool: {request.tool or '-'}\n"
        f"Status: {request.status or '-'}\n"
        f"Attachment: {request.attachmentName or '-'}\n"
        f"Question: {request.question.strip()}\n"
        f"Answer: {request.answer.strip()}\n"
    )
    logger.warning("Feedback fallback saved reason=%s question=%s", reason, request.question[:120])
    try:
        FEEDBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FEEDBACK_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(payload)
    except Exception:
        logger.exception("Feedback fallback file write failed")


def _get_config(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value.strip()

    for env_path in [BACKEND_ROOT / ".env", PROJECT_ROOT / ".env"]:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            if key.strip() == name:
                cleaned = raw_value.strip().strip('"').strip("'")
                return cleaned or None
    return None


def _first_config(*names: str) -> str | None:
    for name in names:
        value = _get_config(name)
        if value:
            return value
    return None


def _parse_int_config(name: str, default: int) -> int:
    value = _get_config(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid integer config %s=%s. Falling back to %s", name, value, default)
        return default


def _smtp_error_summary(exc: Exception) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "SMTP authentication failed. 네이버/구글 계정은 일반 비밀번호가 아니라 애플리케이션 비밀번호가 필요합니다."
    if isinstance(exc, smtplib.SMTPConnectError):
        return "SMTP connection failed. SMTP_HOST와 SMTP_PORT를 확인하세요."
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return "SMTP server disconnected. TLS/SSL 설정이나 포트를 확인하세요."
    if isinstance(exc, TimeoutError):
        return "SMTP connection timed out. Render 네트워크 또는 SMTP 포트 설정을 확인하세요."
    return exc.__class__.__name__


def _default_smtp_host(username: str | None) -> str | None:
    if not username:
        return None
    lowered = username.lower()
    if lowered.endswith("@gmail.com"):
        return "smtp.gmail.com"
    if lowered.endswith("@naver.com"):
        return "smtp.naver.com"
    if lowered.endswith("@daum.net") or lowered.endswith("@kakao.com"):
        return "smtp.daum.net"
    return None
