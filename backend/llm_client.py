from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent


def build_final_answer(question: str, tool_name: str, calculation: dict, references: list[dict]) -> str:
    provider = normalize_provider(get_env("LLM_PROVIDER"))
    if provider == "openai":
        try:
            return build_openai_answer(question, tool_name, calculation, references)
        except Exception as exc:
            fallback = build_rule_based_answer(tool_name, calculation, references)
            return f"{fallback}\n\nLLM 해석 레이어 오류: {exc}"
    if provider == "gemini":
        try:
            return build_gemini_answer(question, tool_name, calculation, references)
        except Exception as exc:
            fallback = build_rule_based_answer(tool_name, calculation, references)
            return f"{fallback}\n\nLLM 해석 레이어 오류: {exc}"
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


def build_openai_answer(question: str, tool_name: str, calculation: dict, references: list[dict]) -> str:
    api_key = get_env("LLM_API_KEY")
    model = get_env("LLM_MODEL")
    if not api_key:
        raise ValueError("LLM_API_KEY가 설정되지 않았습니다.")
    if not model:
        raise ValueError("LLM_MODEL이 설정되지 않았습니다.")

    prompt = build_analysis_prompt(question, tool_name, calculation, references)
    response = call_openai_responses(api_key=api_key, model=model, prompt=prompt)
    return response.strip()


def build_gemini_answer(question: str, tool_name: str, calculation: dict, references: list[dict]) -> str:
    api_key = get_env("LLM_API_KEY")
    model = (get_env("LLM_MODEL") or "gemini-3.1-flash-lite").removeprefix("models/")
    if not api_key:
        raise ValueError("LLM_API_KEY가 설정되지 않았습니다.")

    prompt = build_analysis_prompt(question, tool_name, calculation, references)
    response = call_gemini_generate_content(api_key=api_key, model=model, prompt=prompt)
    return response.strip()


def build_analysis_prompt(question: str, tool_name: str, calculation: dict, references: list[dict]) -> str:
    payload = {
        "question": question,
        "tool_name": tool_name,
        "calculation": calculation,
        "references": references,
    }
    return (
        "너는 한국 상장기업을 분석하는 재무 애널리스트 AI다.\n"
        "아래 JSON에는 사용자의 질문, 계산 도구 결과, 재무제표 추이, DART/뉴스 RAG 근거가 들어 있다.\n\n"
        "답변 원칙:\n"
        "1. 숫자 변화와 원인 후보를 분리해서 설명한다.\n"
        "2. 근거 문서에 없는 산업명, 제품명, 업황 원인은 새로 만들어내지 않는다.\n"
        "3. 근거 문서가 부족하면 '추가 근거 필요'라고 말하고, 재무제표 패턴에서 가능한 확인 방향만 제시한다.\n"
        "4. RAG 근거가 있으면 어떤 문단/출처와 연결되는지 짧게 언급한다.\n"
        "5. 투자 추천, 목표주가, 매수/매도 의견은 내지 않는다.\n"
        "6. 답변은 한국어로, 실무 보고서처럼 간결하게 작성한다.\n\n"
        "권장 형식:\n"
        "- 핵심 요약\n"
        "- 숫자 추이\n"
        "- 원인 후보\n"
        "- 확인해야 할 추가 근거\n\n"
        f"JSON:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


def call_openai_responses(api_key: str, model: str, prompt: str) -> str:
    base_url = (get_env("LLM_BASE_URL") or "https://api.openai.com/v1/responses").rstrip("/")
    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            }
        ],
    }
    request = urllib.request.Request(
        base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45, context=_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {error_body[:500]}") from exc

    text = extract_response_text(data)
    if not text:
        raise RuntimeError("OpenAI 응답에서 텍스트를 찾지 못했습니다.")
    return text


def call_gemini_generate_content(api_key: str, model: str, prompt: str) -> str:
    base_url = (get_env("LLM_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    url = f"{base_url}/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1200,
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45, context=_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API HTTP {exc.code}: {error_body[:500]}") from exc

    parts = []
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if part.get("text"):
                parts.append(part["text"])
    if not parts:
        raise RuntimeError("Gemini 응답에서 텍스트를 찾지 못했습니다.")
    return "\n".join(parts)


def extract_response_text(data: dict[str, Any]) -> str:
    if data.get("output_text"):
        return data["output_text"]

    parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts)


def normalize_provider(provider: str | None) -> str | None:
    if not provider:
        return None
    lowered = provider.strip().lower()
    if "gemini" in lowered:
        return "gemini"
    if "openai" in lowered:
        return "openai"
    return lowered


def get_env(name: str) -> str | None:
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


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None
