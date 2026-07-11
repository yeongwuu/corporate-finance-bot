from __future__ import annotations

import json
import os
import re
import ssl
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent
DEFAULT_CACHE_DIR = BACKEND_ROOT / "data" / "dart"
DEFAULT_EXTERNAL_DOCS_DIR = BACKEND_ROOT / "external_docs"

DART_BASE_URL = "https://opendart.fss.or.kr/api"


@dataclass(frozen=True)
class DartCompany:
    corp_code: str
    corp_name: str
    stock_code: str
    modify_date: str


@dataclass(frozen=True)
class DartReport:
    corp_code: str
    corp_name: str
    stock_code: str
    report_name: str
    rcept_no: str
    rcept_date: str
    corp_cls: str


class DartClient:
    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        external_docs_dir: Path = DEFAULT_EXTERNAL_DOCS_DIR,
    ) -> None:
        self.api_key = api_key or load_dart_api_key()
        if not self.api_key:
            raise ValueError("DART_API_KEY가 없습니다. backend/.env 또는 환경변수에 DART_API_KEY를 설정하세요.")
        self.cache_dir = cache_dir
        self.external_docs_dir = external_docs_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.external_docs_dir.mkdir(parents=True, exist_ok=True)

    def find_company(self, stock_code: str | None = None, corp_name: str | None = None) -> DartCompany | None:
        companies = self.load_corp_codes()
        if stock_code:
            normalized_stock_code = re.sub(r"\D", "", stock_code).zfill(6)
            for company in companies:
                if company.stock_code == normalized_stock_code:
                    return company
        if corp_name:
            compact_query = _compact(corp_name)
            exact = [company for company in companies if _compact(company.corp_name) == compact_query]
            if exact:
                return exact[0]
            partial = [company for company in companies if compact_query in _compact(company.corp_name)]
            if partial:
                return sorted(partial, key=lambda item: len(item.corp_name))[0]
        return None

    def load_corp_codes(self, force_refresh: bool = False) -> list[DartCompany]:
        cache_path = self.cache_dir / "corp_codes.json"
        if cache_path.exists() and not force_refresh:
            return [DartCompany(**row) for row in json.loads(cache_path.read_text(encoding="utf-8"))]

        payload = self._request_bytes("corpCode.xml")
        xml_text = _extract_first_text_from_zip(payload, preferred_suffix=".xml")
        root = ElementTree.fromstring(xml_text)
        companies = []
        for item in root.findall("list"):
            stock_code = (item.findtext("stock_code") or "").strip()
            companies.append(
                DartCompany(
                    corp_code=(item.findtext("corp_code") or "").strip(),
                    corp_name=(item.findtext("corp_name") or "").strip(),
                    stock_code=stock_code.zfill(6) if stock_code else "",
                    modify_date=(item.findtext("modify_date") or "").strip(),
                )
            )

        cache_path.write_text(
            json.dumps([company.__dict__ for company in companies], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return companies

    def list_business_reports(
        self,
        corp_code: str,
        begin_date: str,
        end_date: str,
        final_only: bool = True,
    ) -> list[DartReport]:
        data = self._request_json(
            "list.json",
            {
                "corp_code": corp_code,
                "bgn_de": begin_date,
                "end_de": end_date,
                "last_reprt_at": "Y" if final_only else "N",
                "pblntf_ty": "A",
                "pblntf_detail_ty": "A001",
                "sort": "date",
                "sort_mth": "desc",
                "page_count": "100",
            },
        )
        if data.get("status") != "000":
            return []
        return [
            DartReport(
                corp_code=row.get("corp_code", ""),
                corp_name=row.get("corp_name", ""),
                stock_code=row.get("stock_code", ""),
                report_name=row.get("report_nm", ""),
                rcept_no=row.get("rcept_no", ""),
                rcept_date=row.get("rcept_dt", ""),
                corp_cls=row.get("corp_cls", ""),
            )
            for row in data.get("list", [])
        ]

    def find_business_report(
        self,
        stock_code: str | None = None,
        corp_name: str | None = None,
        fiscal_year: int | None = None,
    ) -> DartReport | None:
        company = self.find_company(stock_code=stock_code, corp_name=corp_name)
        if not company:
            return None

        if fiscal_year:
            reports = self.list_business_reports(
                company.corp_code,
                begin_date=f"{fiscal_year + 1}0101",
                end_date=f"{fiscal_year + 1}1231",
            )
            matched = [report for report in reports if str(fiscal_year) in report.report_name]
            return matched[0] if matched else (reports[0] if reports else None)

        reports = self.list_business_reports(company.corp_code, begin_date="20150101", end_date="20261231")
        return reports[0] if reports else None

    def download_document(self, rcept_no: str) -> str:
        payload = self._request_bytes("document.xml", {"rcept_no": rcept_no})
        cache_path = self.cache_dir / f"{rcept_no}.txt"
        text = _extract_document_text(payload)
        cache_path.write_text(text, encoding="utf-8")
        return text

    def save_business_report_for_rag(
        self,
        stock_code: str | None = None,
        corp_name: str | None = None,
        fiscal_year: int | None = None,
    ) -> dict[str, Any]:
        report = self.find_business_report(stock_code=stock_code, corp_name=corp_name, fiscal_year=fiscal_year)
        if not report:
            return {
                "status": "not_found",
                "message": "조건에 맞는 사업보고서를 찾지 못했습니다.",
            }

        text = self.download_document(report.rcept_no)
        filtered = _extract_relevant_sections(text)
        file_name = f"{_safe_filename(report.corp_name)}_{fiscal_year or report.rcept_date[:4]}_{report.rcept_no}.md"
        output_path = self.external_docs_dir / file_name
        output_path.write_text(
            "\n".join(
                [
                    f"# {report.corp_name} {report.report_name}",
                    "",
                    f"- company: {report.corp_name}",
                    f"- stock_code: {report.stock_code}",
                    f"- corp_code: {report.corp_code}",
                    f"- rcept_no: {report.rcept_no}",
                    f"- rcept_date: {report.rcept_date}",
                    f"- source_url: https://dart.fss.or.kr/dsaf001/main.do?rcpNo={report.rcept_no}",
                    "",
                    filtered,
                ]
            ),
            encoding="utf-8",
        )
        return {
            "status": "ok",
            "report": report.__dict__,
            "path": str(output_path),
            "chars": len(filtered),
        }

    def fetch_financial_accounts(
        self,
        stock_code: str | None = None,
        corp_name: str | None = None,
        fiscal_year: int | None = None,
        fs_div: str = "CFS",
    ) -> dict[str, Any]:
        company = self.find_company(stock_code=stock_code, corp_name=corp_name)
        if not company:
            return {"status": "not_found", "message": "DART에서 회사를 찾지 못했습니다."}
        if not fiscal_year:
            fiscal_year = 2025

        data = self._request_json(
            "fnlttSinglAcntAll.json",
            {
                "corp_code": company.corp_code,
                "bsns_year": str(fiscal_year),
                "reprt_code": "11011",
                "fs_div": fs_div,
            },
        )
        if data.get("status") != "000":
            return {
                "status": "not_found",
                "message": data.get("message") or "DART 재무제표 계정 조회 결과가 없습니다.",
                "company": company.__dict__,
                "year": fiscal_year,
            }
        return {
            "status": "ok",
            "company": company.__dict__,
            "year": fiscal_year,
            "accounts": data.get("list", []),
            "source": "DART fnlttSinglAcntAll",
        }

    def _request_json(self, endpoint: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        payload = self._request_bytes(endpoint, params)
        return json.loads(payload.decode("utf-8"))

    def _request_bytes(self, endpoint: str, params: dict[str, str] | None = None) -> bytes:
        query = {"crtfc_key": self.api_key}
        if params:
            query.update(params)
        url = f"{DART_BASE_URL}/{endpoint}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(url, headers={"User-Agent": "corporate-finance-bot/0.1"})
        context = _ssl_context()
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return response.read()


def load_dart_api_key() -> str | None:
    env_value = os.getenv("DART_API_KEY")
    if env_value:
        return env_value.strip()

    for env_path in [BACKEND_ROOT / ".env", PROJECT_ROOT / ".env"]:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "DART_API_KEY":
                return value.strip().strip('"').strip("'")
    return None


def _extract_first_text_from_zip(payload: bytes, preferred_suffix: str = ".xml") -> str:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(preferred_suffix)]
        if not names:
            names = archive.namelist()
        raw = archive.read(names[0])
    return _decode_bytes(raw)


def _extract_document_text(payload: bytes) -> str:
    if zipfile.is_zipfile(BytesIO(payload)):
        parts = []
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith((".xml", ".html", ".htm", ".txt")):
                    continue
                parts.append(_decode_bytes(archive.read(name)))
        return "\n\n".join(_strip_markup(part) for part in parts)
    return _strip_markup(_decode_bytes(payload))


def _decode_bytes(raw: bytes) -> str:
    for encoding in ["utf-8", "cp949", "euc-kr"]:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _strip_markup(text: str) -> str:
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|tr|table|section|title)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_relevant_sections(text: str, max_chars: int = 120_000) -> str:
    keywords = [
        "사업의 내용",
        "영업의 개황",
        "주요 제품",
        "주요 서비스",
        "매출 및 수주상황",
        "매출에 관한 사항",
        "원재료",
        "생산설비",
        "위험관리",
        "연구개발",
        "부문정보",
    ]
    lines = text.splitlines()
    selected = []
    keep_until = -1
    for index, line in enumerate(lines):
        if any(keyword in line for keyword in keywords):
            keep_until = max(keep_until, index + 80)
        if index <= keep_until:
            selected.append(line)
    if not selected:
        selected = lines
    compacted = "\n".join(selected)
    return compacted[:max_chars]


def _safe_filename(value: str) -> str:
    return re.sub(r"[^가-힣A-Za-z0-9_.-]+", "_", value).strip("_") or "dart_report"


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None
