"""Search the project's internal corporate-finance knowledge documents."""

from pathlib import Path
import re


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


def search_knowledge(question: str, limit: int = 3) -> list[dict]:
    query_terms = tokenize(question)
    scored_docs = []

    for path in KNOWLEDGE_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        headings = "\n".join(line.lower() for line in text.splitlines() if line.lstrip().startswith("#"))
        line_matches = [sum(term in line.lower() for term in query_terms) for line in text.splitlines()]
        score = (
            sum(lowered.count(term) for term in query_terms)
            + 2 * sum(headings.count(term) for term in query_terms)
            + 3 * max(line_matches or [0]) ** 2
        )
        if score > 0:
            scored_docs.append(
                {
                    "title": path.stem,
                    "score": score,
                    "snippet": make_snippet(text, query_terms),
                }
            )

    return sorted(scored_docs, key=lambda item: item["score"], reverse=True)[:limit]


def tokenize(text: str) -> list[str]:
    raw_terms = re.findall(r"[가-힣A-Za-z0-9]+", text.lower())
    stop_terms = {"관계", "설명", "설명해줘", "알려줘", "어떻게", "무엇", "뭐야", "대해"}
    terms = []
    for term in raw_terms:
        normalized = strip_korean_particle(term)
        if len(normalized) >= 2 and normalized not in stop_terms:
            terms.append(normalized)
    return terms


def strip_korean_particle(term: str) -> str:
    """Remove common Korean particles so domain terms match knowledge text."""
    if not re.fullmatch(r"[가-힣]+", term):
        return term
    for particle in ("으로부터", "에서는", "에게서", "으로는", "에서", "에게", "으로", "와의", "과의", "까지", "부터", "처럼", "보다", "하고", "이며", "에서의", "은", "는", "이", "가", "을", "를", "과", "와", "의", "에", "도", "로"):
        if term.endswith(particle) and len(term) - len(particle) >= 2:
            return term[: -len(particle)]
    return term


def make_snippet(text: str, terms: list[str]) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if any(term in lowered for term in terms):
            return line[:160]
    return lines[0][:160] if lines else ""
