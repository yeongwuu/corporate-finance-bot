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
    if calculation.get("status") == "latest_news":
        return build_latest_news_answer(calculation)
    if calculation.get("status") == "needs_latest_disclosure":
        return build_rule_based_answer(tool_name, calculation, [])

    provider = normalize_provider(get_env("LLM_PROVIDER"))
    if provider == "openai":
        try:
            return build_openai_answer(question, tool_name, calculation, references)
        except Exception:
            return build_rule_based_answer(tool_name, calculation, references)
    if provider == "gemini":
        try:
            return build_gemini_answer(question, tool_name, calculation, references)
        except Exception:
            return build_rule_based_answer(tool_name, calculation, references)
    return build_rule_based_answer(tool_name, calculation, references)


def build_latest_news_answer(calculation: dict) -> str:
    paragraphs = [calculation.get("summary") or "최신 뉴스 근거를 확인했습니다."]
    documents = calculation.get("external_references") or []
    if documents:
        lines = ["확인된 뉴스 후보는 다음과 같습니다."]
        for doc in documents[:5]:
            source = f" ({doc.get('source_url')})" if doc.get("source_url") else ""
            lines.append(f"- {doc.get('title', '뉴스')}: {doc.get('snippet', '')}{source}")
        paragraphs.append("\n".join(lines))
        paragraphs.append("위 내용은 뉴스 검색 결과의 제목과 요약을 근거로 한 것이므로, 확정 실적 수치는 원문 기사나 DART 잠정실적 공시와 함께 확인하는 것이 좋습니다.")
    else:
        paragraphs.append("뉴스 검색 결과에서 해당 분기 실적 수치를 확인할 만한 근거를 찾지 못했습니다. DART 잠정실적 공시나 회사 IR 자료를 확인해야 합니다.")
    return "\n\n".join(paragraphs)


def build_rule_based_answer(tool_name: str, calculation: dict, references: list[dict]) -> str:
    summary = calculation.get("summary") or calculation.get("message") or "질문을 해석했지만 충분한 계산 결과를 찾지 못했습니다."
    paragraphs = [summary]
    needs_structure = _needs_structured_answer(calculation)

    steps = calculation.get("steps", [])
    if steps:
        narrative_steps = []
        for step in steps:
            cleaned = _clean_step(step)
            if cleaned:
                narrative_steps.append(cleaned)
        if narrative_steps:
            if needs_structure:
                paragraphs.extend(narrative_steps[:5])
            else:
                paragraphs.append(" ".join(narrative_steps[:3]))

    if references and calculation.get("status") not in {"needs_latest_disclosure", "missing_data", "needs_company", "no_data"}:
        paragraphs.append("관련 재무 기준과 내부 지식 문서도 함께 확인해 답변했습니다.")

    return "\n\n".join(paragraphs)


def _needs_structured_answer(calculation: dict) -> bool:
    return bool(calculation.get("metrics") or calculation.get("series") or calculation.get("comparison"))


def _clean_step(step: str) -> str:
    cleaned = str(step).strip()
    prefixes = [
        "조회 대상:",
        "시장/업종:",
        "주요계정:",
        "간단 분석:",
        "계산 요약:",
        "기간 해석:",
        "RAG 근거 후보:",
    ]
    if cleaned.startswith("데이터 원천:"):
        return ""
    if cleaned.startswith("RAG 근거 후보:"):
        return "관련 외부 문서 후보를 함께 확인했습니다."
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned.replace(prefix, "", 1).strip()
            break
    cleaned = cleaned.replace(" | ", ", ")
    cleaned = cleaned.replace(" / ", "\n")
    if cleaned and cleaned[-1] not in ".!?。":
        cleaned = f"{cleaned}."
    return cleaned


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
        "1. 사용자가 단순 사실 확인이나 특정 수치를 물으면 자연스러운 문단형 답변으로 짧게 답한다.\n"
        "2. 근거 문서에 없는 산업명, 제품명, 업황 원인은 새로 만들어내지 않는다.\n"
        "3. 근거 문서가 부족하면 '추가 근거 필요'라고 말하고, 재무제표 패턴에서 가능한 확인 방향만 제시한다.\n"
        "4. RAG 근거가 있으면 어떤 출처와 연결되는지 짧게 언급한다.\n"
        "5. 투자 추천, 목표주가, 매수/매도 의견은 내지 않는다.\n"
        "6. 답변은 한국어로, 실무 보고서처럼 간결하게 작성한다.\n\n"
        "형식 원칙:\n"
        "- 기본은 소제목 없이 1~3개 자연스러운 문단으로 답한다.\n"
        "- 사용자가 비교, 추이, 원인 분석, 여러 지표 분석을 요청한 경우에만 필요한 소제목을 사용한다.\n"
        "- 소제목을 쓰더라도 Markdown 표시는 최소화하고, 불필요한 장식은 피한다.\n\n"
        "수식 표기:\n"
        "- 수식이 필요하면 일반 텍스트로 깨지게 쓰지 말고 LaTeX 형식으로 작성한다.\n"
        "- 짧은 수식은 `$P_0 = \\frac{D_1}{k-g}$`처럼 `$...$` 안에 넣는다.\n"
        "- 긴 수식은 `$$...$$` 블록으로 작성한다.\n\n"
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
