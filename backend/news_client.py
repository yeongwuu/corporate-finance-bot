from __future__ import annotations

import html
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent
DEFAULT_EXTERNAL_DOCS_DIR = BACKEND_ROOT / "external_docs"


@dataclass(frozen=True)
class NewsItem:
    title: str
    description: str
    link: str
    pub_date: str
    image_url: str | None = None


class NewsClient:
    def __init__(self, external_docs_dir: Path = DEFAULT_EXTERNAL_DOCS_DIR) -> None:
        self.provider = get_env("NEWS_PROVIDER") or "naver"
        self.external_docs_dir = external_docs_dir
        self.external_docs_dir.mkdir(parents=True, exist_ok=True)

    def search(self, query: str, display: int = 10) -> list[NewsItem]:
        if self.provider.lower() == "naver":
            return self._search_naver(query, display=display)
        raise ValueError(f"지원하지 않는 NEWS_PROVIDER입니다: {self.provider}")

    def save_news_for_rag(self, query: str, company_name: str | None = None, display: int = 10) -> dict[str, Any]:
        items = self.search(query, display=display)
        if not items:
            return {"status": "not_found", "message": "뉴스 검색 결과가 없습니다."}

        file_name = f"news_{_safe_filename(company_name or query)}.md"
        output_path = self.external_docs_dir / file_name
        lines = [
            f"# {company_name or query} 뉴스 근거",
            "",
            f"- query: {query}",
            f"- provider: {self.provider}",
            "",
        ]
        for index, item in enumerate(items, start=1):
            lines.extend(
                [
                    f"## {index}. {item.title}",
                    "",
                    f"- published: {item.pub_date}",
                    f"- source_url: {item.link}",
                    *([f"- image_url: {item.image_url}"] if item.image_url else []),
                    "",
                    item.description,
                    "",
                ]
            )
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return {"status": "ok", "path": str(output_path), "count": len(items)}

    def _search_naver(self, query: str, display: int = 10) -> list[NewsItem]:
        client_id = get_env("NAVER_CLIENT_ID")
        client_secret = get_env("NAVER_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ValueError("NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 필요합니다.")

        params = urllib.parse.urlencode({"query": query, "display": display, "sort": "date"})
        request = urllib.request.Request(
            f"https://openapi.naver.com/v1/search/news.json?{params}",
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
                "User-Agent": "corporate-finance-bot/0.1",
            },
        )
        with urllib.request.urlopen(request, timeout=20, context=_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))

        return [
            NewsItem(
                title=_clean_html(item.get("title", "")),
                description=_clean_html(item.get("description", "")),
                link=item.get("originallink") or item.get("link", ""),
                pub_date=item.get("pubDate", ""),
                image_url=_fetch_open_graph_image(item.get("originallink") or item.get("link", "")),
            )
            for item in data.get("items", [])
        ]


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


def _clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def _fetch_open_graph_image(url: str) -> str | None:
    if not url:
        return None
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 corporate-finance-bot/0.1"},
        )
        with urllib.request.urlopen(request, timeout=4, context=_ssl_context()) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type.lower():
                return None
            html_text = response.read(300_000).decode("utf-8", errors="ignore")
    except Exception:
        return None

    patterns = [
        r'<meta\s+[^>]*(?:property|name)=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
        r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']og:image["\']',
        r'<meta\s+[^>]*(?:property|name)=["\']twitter:image["\'][^>]*content=["\']([^"\']+)["\']',
        r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']twitter:image["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            image_url = html.unescape(match.group(1)).strip()
            return urllib.parse.urljoin(url, image_url)
    return None


def _safe_filename(value: str) -> str:
    return re.sub(r"[^가-힣A-Za-z0-9_.-]+", "_", value).strip("_") or "news"


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None
