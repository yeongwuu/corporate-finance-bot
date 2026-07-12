from __future__ import annotations

import re
from pathlib import Path


import email.utils
from datetime import datetime

EXTERNAL_DOCS_DIR = Path(__file__).resolve().parents[1] / "external_docs"
BUSINESS_TERMS = [
    "매출",
    "영업이익",
    "수요",
    "공급",
    "가격",
    "판가",
    "출하",
    "업황",
    "시장",
    "반도체",
    "메모리",
    "디스플레이",
    "모바일",
    "서버",
    "ai",
    "환율",
    "원재료",
    "제품",
    "부문",
    "수익성",
]


def parse_published_timestamp(published_str: str | None) -> float:
    if not published_str:
        return 0.0
    try:
        dt = email.utils.parsedate_to_datetime(published_str)
        return dt.timestamp()
    except Exception:
        try:
            dt = datetime.strptime(published_str.split()[0], "%Y-%m-%d")
            return dt.timestamp()
        except Exception:
            return 0.0


def search_external_docs(query: str, company_name: str | None = None, limit: int = 5) -> list[dict]:
    terms = tokenize(query)
    if company_name:
        company_term = re.sub(r"\s+", "", company_name.lower())
        terms = [term for term in terms if term != company_term and term not in company_term]
    if not EXTERNAL_DOCS_DIR.exists():
        return []

    scored_chunks = []
    for path in list(EXTERNAL_DOCS_DIR.glob("*.md")) + list(EXTERNAL_DOCS_DIR.glob("*.txt")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        if company_name and not _document_matches_company(path, text, company_name):
            continue
        for chunk_index, chunk in enumerate(chunk_text(text)):
            score = score_chunk(chunk, terms, company_name)
            if score <= 0:
                continue
            metadata = parse_metadata(chunk) or parse_metadata(text)
            published_str = metadata.get("published")
            pub_ts = parse_published_timestamp(published_str)

            # Apply recency bonus to news articles
            is_news = path.name.startswith("news_")
            if is_news and pub_ts > 0:
                # Calculate years since 2020-01-01 (1577836800)
                # 1 year is approx 31536000 seconds. Add 5.0 bonus score points per year.
                years_since_2020 = (pub_ts - 1577836800) / 31536000.0
                if years_since_2020 > 0:
                    score += int(years_since_2020 * 5.0)

            scored_chunks.append(
                {
                    "title": path.stem,
                    "source": str(path),
                    "source_url": metadata.get("source_url"),
                    "image_url": metadata.get("image_url"),
                    "published": published_str,
                    "score": score,
                    "chunk_index": chunk_index,
                    "snippet": make_snippet(chunk, terms),
                }
            )

    return sorted(scored_chunks, key=lambda item: item["score"], reverse=True)[:limit]


def tokenize(text: str) -> list[str]:
    raw_terms = re.findall(r"[가-힣A-Za-z0-9]+", text.lower())
    stopwords = {"최근", "추이", "분석", "이유", "원인", "설명", "기업", "회사", "사업보고서", "뉴스"}
    terms = []
    for term in raw_terms:
        if len(term) < 2 or term in stopwords:
            continue
        if term.isdigit() or re.fullmatch(r"20[1-2]\d", term):
            continue
        terms.append(term)
    return terms


def make_snippet(text: str, terms: list[str]) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("- ")]
    for line in lines:
        lowered = line.lower()
        if any(term in lowered for term in terms + BUSINESS_TERMS):
            return line[:220]
    return lines[0][:220] if lines else ""


def parse_metadata(text: str) -> dict[str, str]:
    metadata = {}
    for line in text.splitlines()[:20]:
        if line.startswith("- ") and ":" in line:
            key, value = line[2:].split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata


def chunk_text(text: str, max_chars: int = 1400) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", text) if paragraph.strip()]
    chunks = []
    current = []
    current_size = 0
    for paragraph in paragraphs:
        if paragraph.startswith("# ") or paragraph.startswith("- "):
            continue
        paragraph_size = len(paragraph)
        if current and current_size + paragraph_size > max_chars:
            chunks.append("\n".join(current))
            current = []
            current_size = 0
        current.append(paragraph)
        current_size += paragraph_size
    if current:
        chunks.append("\n".join(current))
    return chunks


def score_chunk(chunk: str, terms: list[str], company_name: str | None) -> int:
    lowered = chunk.lower()
    score = sum(lowered.count(term) * 3 for term in terms)
    business_score = sum(lowered.count(term) for term in BUSINESS_TERMS)
    score += business_score
    if any(term in lowered for term in ["영업의 개황", "사업의 내용", "매출 및 수주상황", "주요 제품"]):
        score += 4
    if business_score <= 0:
        return 0
    return score


def _document_matches_company(path: Path, text: str, company_name: str) -> bool:
    compact_company = re.sub(r"\s+", "", company_name.lower())
    compact_path = re.sub(r"\s+", "", path.stem.lower())
    compact_head = re.sub(r"\s+", "", text[:2000].lower())
    return compact_company in compact_path or compact_company in compact_head
