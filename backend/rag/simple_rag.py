from pathlib import Path
import re


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


def search_knowledge(question: str, limit: int = 3) -> list[dict]:
    query_terms = tokenize(question)
    scored_docs = []

    for path in KNOWLEDGE_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        score = sum(text.lower().count(term) for term in query_terms)
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
    return [term for term in raw_terms if len(term) >= 2]


def make_snippet(text: str, terms: list[str]) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if any(term in lowered for term in terms):
            return line[:160]
    return lines[0][:160] if lines else ""
