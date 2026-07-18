from __future__ import annotations

import math
import os
import re
import ssl
import threading
import time as time_module
import urllib.request
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from company_data.financial_store import FinancialStatementStore


_PRICE_CACHE_TTL_SECONDS = int(os.getenv("PRICE_CACHE_TTL_SECONDS", "900"))
_PRICE_CACHE_MAX_ENTRIES = max(1, int(os.getenv("PRICE_CACHE_MAX_ENTRIES", "12")))
_PRICE_CACHE: dict[tuple[str, str, str, str], tuple[float, pd.DataFrame]] = {}
_PRICE_CACHE_LOCK = threading.Lock()


def _get_cached_price_frame(key: tuple[str, str, str, str]) -> pd.DataFrame | None:
    with _PRICE_CACHE_LOCK:
        cached = _PRICE_CACHE.get(key)
        if not cached:
            return None
        cached_at, frame = cached
        if time_module.monotonic() - cached_at > _PRICE_CACHE_TTL_SECONDS:
            _PRICE_CACHE.pop(key, None)
            return None
        return frame.copy()


def _cache_price_frame(key: tuple[str, str, str, str], frame: pd.DataFrame) -> None:
    if frame is None or frame.empty:
        return
    with _PRICE_CACHE_LOCK:
        _PRICE_CACHE[key] = (time_module.monotonic(), frame.copy())
        if len(_PRICE_CACHE) > _PRICE_CACHE_MAX_ENTRIES:
            oldest_key = min(_PRICE_CACHE, key=lambda item: _PRICE_CACHE[item][0])
            _PRICE_CACHE.pop(oldest_key, None)


def analyze_stock_price(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
    
    # Check for multiple companies to compare
    companies = []
    seen = set()
    for chunk in re.split(r"\s*(?:와|과|랑|하고|및|vs\.?|VS|비교|,)\s*", question):
        cleaned = re.sub(r"(?:의|최근|주가|흐름|분석|비교|해줘|알려줘|차트|보여줘|\d+년|\d+개년)", "", chunk).strip()
        if not cleaned or len(cleaned) < 2:
            continue
        try:
            company = store.resolve_company(cleaned)
            if company and company.stock_code not in seen:
                seen.add(company.stock_code)
                companies.append(company)
        except Exception:
            pass
            
    if len(companies) >= 2:
        return compare_stock_prices(question, companies)

    try:
        company = store.resolve_company(question)
    except FileNotFoundError as exc:
        return {
            "status": "missing_data",
            "summary": "재무제표 데이터에서 종목코드를 확인하지 못했습니다.",
            "steps": [str(exc)],
        }

    normalized = question.lower()
    if any(word in normalized for word in ["예측", "전망", "예상", "모델"]) and any(word in normalized for word in ["주가", "종가", "가격"]):
        return predict_stock_price_arima(question, company)
    if not company:
        return {
            "status": "needs_company",
            "summary": "주가를 조회할 회사명을 찾지 못했습니다.",
            "steps": ["예: 삼성전자 최근 1년 주가 그래프 그려줘, SK하이닉스 주가 수익률 표준편차 계산해줘"],
        }

    period = _extract_period(question)
    ticker = _to_yahoo_ticker(company.stock_code, company.market)
    price_source = "네이버 금융"
    try:
        frame = _download_naver_price_data(company.stock_code, period["start"], period["end"])
        if frame.empty:
            fallback = _download_fallback_naver_price_data(company.stock_code, period)
            if fallback:
                frame, period = fallback
        if frame.empty:
            frame = _download_price_data(ticker, period["start"], period["end"])
            if not frame.empty:
                price_source = "Yahoo Finance"
        if frame.empty:
            fallback = _download_fallback_price_data(ticker, period)
            if fallback:
                frame, period = fallback
                price_source = "Yahoo Finance"
    except ImportError:
        return {
            "status": "missing_dependency",
            "summary": "주가 조회에 필요한 yfinance 패키지가 설치되어 있지 않습니다.",
            "steps": ["backend/requirements.txt에 yfinance를 추가한 뒤 서버를 다시 배포해야 합니다."],
            "company": company.__dict__,
            "ticker": ticker,
        }
    except Exception as exc:
        return {
            "status": "price_fetch_error",
            "summary": f"{company.company_name}의 주가 데이터를 불러오지 못했습니다.",
            "steps": [f"Yahoo Finance 조회 실패: {exc}"],
            "company": company.__dict__,
            "ticker": ticker,
        }

    if frame.empty:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 주가 데이터를 찾지 못했습니다.",
            "steps": [f"조회 티커: {ticker}", f"조회 기간: {period['start']}~{period['end']}"],
            "company": company.__dict__,
            "ticker": ticker,
        }

    prices = _build_price_points(frame)
    stats = _build_backtest_stats(frame)
    data_start_date = frame.index[0].date().isoformat() if hasattr(frame.index[0], "date") else str(frame.index[0])
    data_end_date = frame.index[-1].date().isoformat() if hasattr(frame.index[-1], "date") else str(frame.index[-1])
    summary = (
        f"{company.company_name}의 {period['label']} 주가 추이를 조회했습니다. "
        f"기간 수익률은 {stats['cumulative_return_display']}, "
        f"일평균 수익률은 {stats['daily_return_mean_display']}, "
        f"일간 수익률 표준편차는 {stats['daily_return_std_display']}입니다."
    )
    steps = [
        f"조회 대상: {company.company_name}({company.stock_code}), 가격 데이터 출처 {price_source}",
        f"조회 기간: {period['start']}~{period['end']}",
        f"가격 범위: 시작가 {_format_krw(stats['first_close'])}, 종료가 {_format_krw(stats['last_close'])}",
        f"기간 수익률: {stats['cumulative_return_display']}",
        f"종가 평균/표준편차: {_format_krw(stats['close_mean'])} / {_format_krw(stats['close_std'])}",
        f"일간 수익률 평균/표준편차: {stats['daily_return_mean_display']} / {stats['daily_return_std_display']}",
        f"연율화 수익률/변동성: {stats['annualized_return_display']} / {stats['annualized_volatility_display']}",
        f"최대낙폭(MDD): {stats['max_drawdown_display']}",
    ]
    if period.get("fallback"):
        steps.insert(
            2,
            f"요청 기간({period['requested_start']}~{period['requested_end']}) 데이터가 비어 있어 확인 가능한 과거 구간으로 재조회했습니다.",
        )

    serializable_period = {}
    for k, v in period.items():
        if isinstance(v, date):
            serializable_period[k] = v.isoformat()
        else:
            serializable_period[k] = v

    return {
        "status": "ok",
        "summary": summary,
        "steps": steps,
        "company": company.__dict__,
        "ticker": ticker,
        "price_source": price_source,
        "data_start_date": data_start_date,
        "data_end_date": data_end_date,
        "period": serializable_period,
        "prices": prices,
        "stats": stats,
    }


def _download_price_data(ticker: str, start: date, end: date) -> pd.DataFrame:
    import yfinance as yf

    cache_key = ("yahoo", ticker, start.isoformat(), end.isoformat())
    cached = _get_cached_price_frame(cache_key)
    if cached is not None:
        return cached

    frame = yf.download(
        ticker,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        progress=False,
        auto_adjust=True,
        threads=False,
        timeout=8,
    )
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame = frame.dropna(subset=["Close"]) if "Close" in frame else pd.DataFrame()
    _cache_price_frame(cache_key, frame)
    return frame.copy()


def _download_fallback_price_data(ticker: str, period: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    duration = max(30, (period["end"] - period["start"]).days)
    today = date.today()
    for offset_days in [30, 90, 180, 365, 730]:
        fallback_end = today - timedelta(days=offset_days)
        fallback_start = fallback_end - timedelta(days=duration)
        frame = _download_price_data(ticker, fallback_start, fallback_end)
        if not frame.empty:
            fallback_period = {
                "start": fallback_start,
                "end": fallback_end,
                "label": f"최근 확인 가능 {period['label']}",
                "fallback": True,
                "requested_start": period["start"],
                "requested_end": period["end"],
            }
            return frame, fallback_period
    return None


def _download_naver_price_data(stock_code: str, start: date, end: date) -> pd.DataFrame:
    code = stock_code.zfill(6)
    cache_key = ("naver", code, start.isoformat(), end.isoformat())
    cached = _get_cached_price_frame(cache_key)
    if cached is not None:
        return cached
    duration = max(30, (end - start).days)
    max_pages = min(260, max(20, math.ceil(duration / 7) + 5))
    rows: list[dict[str, Any]] = []

    for page in range(1, max_pages + 1):
        page_rows = _fetch_naver_price_page(code, page)
        if not page_rows:
            break
        rows.extend(page_rows)
        oldest = min(row["date"] for row in page_rows)
        if oldest < start:
            break

    filtered = [row for row in rows if start <= row["date"] <= end]
    if not filtered:
        return pd.DataFrame()

    frame = pd.DataFrame(
        {"Close": [row["close"] for row in filtered]},
        index=pd.to_datetime([row["date"] for row in filtered]),
    )
    frame = frame[~frame.index.duplicated(keep="last")]
    frame = frame.sort_index()
    _cache_price_frame(cache_key, frame)
    return frame.copy()


def _download_fallback_naver_price_data(
    stock_code: str, period: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    duration = max(30, (period["end"] - period["start"]).days)
    today = date.today()
    for offset_days in [30, 90, 180, 365, 730]:
        fallback_end = today - timedelta(days=offset_days)
        fallback_start = fallback_end - timedelta(days=duration)
        frame = _download_naver_price_data(stock_code, fallback_start, fallback_end)
        if not frame.empty:
            fallback_period = {
                "start": fallback_start,
                "end": fallback_end,
                "label": f"최근 확인 가능 {period['label']}",
                "fallback": True,
                "requested_start": period["start"],
                "requested_end": period["end"],
            }
            return frame, fallback_period
    return None


def _fetch_naver_price_page(stock_code: str, page: int) -> list[dict[str, Any]]:
    url = f"https://finance.naver.com/item/sise_day.naver?code={stock_code}&page={page}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=4, context=_ssl_context()) as response:
        html = response.read().decode("euc-kr", errors="ignore")

    rows = []
    for table_row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        text = re.sub(r"<[^>]+>", " ", table_row)
        text = re.sub(r"\s+", " ", text).strip()
        date_match = re.search(r"(20\d{2})\.(\d{2})\.(\d{2})", text)
        if not date_match:
            continue
        numbers = re.findall(r"\d{1,3}(?:,\d{3})+", text)
        if not numbers:
            continue
        close = float(numbers[0].replace(",", ""))
        rows.append(
            {
                "date": date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))),
                "close": close,
            }
        )
    return rows


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return None


def _extract_period(question: str) -> dict[str, Any]:
    today = _latest_completed_close_date()
    normalized = question.lower().replace(" ", "")
    years = [int(match) for match in re.findall(r"(20[0-3]\d)", question)]
    if len(years) >= 2:
        start = date(min(years[:2]), 1, 1)
        end = date(max(years[:2]), 12, 31)
        return {"start": start, "end": min(end, today), "label": f"{start.year}~{end.year}년"}
    if len(years) == 1:
        start = date(years[0], 1, 1)
        end = min(date(years[0], 12, 31), today)
        return {"start": start, "end": end, "label": f"{years[0]}년"}

    month_match = re.search(r"최근\s*(\d+)\s*(?:개월|달)", question)
    if month_match:
        months = max(1, int(month_match.group(1)))
        return {"start": today - timedelta(days=months * 31), "end": today, "label": f"최근 {months}개월"}

    year_match = re.search(r"최근\s*(\d+)\s*(?:년|개년)", question)
    if year_match:
        count = max(1, int(year_match.group(1)))
        return {"start": today - timedelta(days=count * 365), "end": today, "label": f"최근 {count}년"}

    if "6개월" in normalized:
        return {"start": today - timedelta(days=186), "end": today, "label": "최근 6개월"}
    if "3개월" in normalized:
        return {"start": today - timedelta(days=93), "end": today, "label": "최근 3개월"}
    if "5년" in normalized or "5개년" in normalized:
        return {"start": today - timedelta(days=365 * 5), "end": today, "label": "최근 5년"}
    return {"start": today - timedelta(days=365), "end": today, "label": "최근 1년"}


def _latest_completed_close_date(now: datetime | None = None) -> date:
    korea_now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    completed_date = korea_now.date()
    # 장중 일별 시세는 확정 종가가 아니므로 정규장 종료 후 반영 여유까지 제외합니다.
    if korea_now.weekday() < 5 and korea_now.time() < time(16, 0):
        completed_date -= timedelta(days=1)
    return completed_date


def _to_yahoo_ticker(stock_code: str, market: str | None) -> str:
    code = stock_code.zfill(6)
    normalized_market = (market or "").upper()
    if "KOSDAQ" in normalized_market or "코스닥" in (market or ""):
        return f"{code}.KQ"
    return f"{code}.KS"


def _build_price_points(frame: pd.DataFrame) -> list[dict[str, Any]]:
    sampled = _sample_frame(frame, max_points=160)
    points = []
    for index, (dt, row) in enumerate(sampled.iterrows()):
        close = float(row["Close"])
        points.append(
            {
                "x": index,
                "date": dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10],
                "close": close,
                "display": _format_krw(close),
            }
        )
    return points


def _sample_frame(frame: pd.DataFrame, max_points: int) -> pd.DataFrame:
    if len(frame) <= max_points:
        return frame
    step = math.ceil(len(frame) / max_points)
    sampled = frame.iloc[::step].copy()
    if sampled.index[-1] != frame.index[-1]:
        sampled = pd.concat([sampled, frame.tail(1)])
    return sampled


def _build_backtest_stats(frame: pd.DataFrame) -> dict[str, Any]:
    close = frame["Close"].astype(float)
    returns = close.pct_change().dropna()
    first_close = float(close.iloc[0])
    last_close = float(close.iloc[-1])
    max_close = float(close.max())
    min_close = float(close.min())
    cumulative_return = (last_close / first_close - 1) if first_close else 0.0
    daily_mean = float(returns.mean()) if not returns.empty else 0.0
    daily_std = float(returns.std()) if len(returns) >= 2 else 0.0
    annualized_return = ((1 + daily_mean) ** 252 - 1) if daily_mean > -1 else -1.0
    annualized_volatility = daily_std * math.sqrt(252)
    running_max = close.cummax()
    drawdown = close / running_max - 1
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0

    return {
        "first_close": first_close,
        "last_close": last_close,
        "max_close": max_close,
        "min_close": min_close,
        "close_mean": float(close.mean()),
        "close_std": float(close.std()) if len(close) >= 2 else 0.0,
        "daily_return_mean": daily_mean,
        "daily_return_std": daily_std,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "cumulative_return": cumulative_return,
        "max_drawdown": max_drawdown,
        "daily_return_mean_display": _format_percent(daily_mean),
        "daily_return_std_display": _format_percent(daily_std),
        "annualized_return_display": _format_percent(annualized_return),
        "annualized_volatility_display": _format_percent(annualized_volatility),
        "cumulative_return_display": _format_percent(cumulative_return),
        "max_drawdown_display": _format_percent(max_drawdown),
    }


def _format_krw(value: float) -> str:
    return f"{value:,.0f}원"


def _format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def predict_stock_price_arima(question: str, company: Any) -> dict[str, Any]:
    if not company:
        return {
            "status": "needs_company",
            "summary": "주가를 예측할 회사명을 찾지 못했습니다.",
            "steps": ["예: 삼성전자 최근 3년 주가를 예측해줘"],
        }

    duration_years = 5
    match = re.search(r"최근\s*(\d+)\s*(?:개년|년)", question)
    if match:
        duration_years = max(2, min(5, int(match.group(1))))

    end_date = date.today()
    start_date = end_date - timedelta(days=int(duration_years * 365.25))

    ticker = _to_yahoo_ticker(company.stock_code, company.market)
    yahoo_error = None
    try:
        frame = _download_price_data(ticker, start_date, end_date)
    except Exception as exc:
        yahoo_error = exc
        frame = pd.DataFrame()

    if frame.empty:
        try:
            frame = _download_naver_price_data(company.stock_code, start_date, end_date)
        except Exception as naver_error:
            return {
                "status": "price_fetch_error",
                "summary": f"{company.company_name}의 주가 데이터를 불러오지 못했습니다.",
                "steps": [
                    f"Yahoo Finance 조회 오류: {yahoo_error or '데이터 없음'}",
                    f"네이버 금융 조회 오류: {naver_error}",
                ],
                "company": company.__dict__,
                "ticker": ticker,
            }

    if frame.empty or len(frame) < 120:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 주가 예측에 필요한 주가 시계열 데이터가 부족합니다.",
            "steps": [f"가용 데이터 개수: {len(frame)}개 (최소 120영업일 이상 필요)"],
            "company": company.__dict__,
            "ticker": ticker,
        }

    import numpy as np
    forecast_days = _forecast_horizon_days(question)
    forecast_label = _forecast_horizon_label(forecast_days)
    from statsmodels.tsa.arima.model import ARIMA
    import warnings

    closes = pd.to_numeric(frame["Close"], errors="coerce").dropna().astype(float)
    log_prices = np.log(closes.to_numpy())
    latest_close = float(closes.iloc[-1])
    candidate_orders = [(0, 1, 0), (1, 1, 0), (0, 1, 1), (1, 1, 1), (2, 1, 0), (0, 1, 2)]
    validation_start = max(80, len(log_prices) - 60)
    possible_origins = np.arange(validation_start, len(log_prices) - forecast_days + 1)
    if len(possible_origins) > 8:
        possible_origins = np.unique(np.linspace(possible_origins[0], possible_origins[-1], 8).astype(int))

    actual_values = np.asarray([closes.iloc[origin + forecast_days - 1] for origin in possible_origins])
    naive_values = np.asarray([closes.iloc[origin - 1] for origin in possible_origins])
    naive_test_mae = float(np.mean(np.abs(actual_values - naive_values)))
    order_scores: list[tuple[float, tuple[int, int, int]]] = []
    for order in candidate_orders:
        predictions = []
        try:
            for origin in possible_origins:
                train = log_prices[max(0, origin - 756):origin]
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    fitted = ARIMA(train, order=order, trend="n").fit()
                predictions.append(float(np.exp(fitted.forecast(steps=forecast_days)[-1])))
            order_scores.append((float(np.mean(np.abs(actual_values - predictions))), order))
        except Exception:
            continue

    order_scores.sort(key=lambda item: item[0])
    best_arima_mae, best_order = order_scores[0] if order_scores else (float("inf"), (0, 1, 0))
    use_arima = best_arima_mae < naive_test_mae
    model_name = f"ARIMA{best_order}" if use_arima else "랜덤워크"

    if use_arima:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fitted = ARIMA(log_prices[-756:], order=best_order, trend="n").fit()
        forecast_result = fitted.get_forecast(steps=forecast_days)
        forecast_values = np.exp(np.asarray(forecast_result.predicted_mean, dtype=float)).tolist()
        confidence = np.asarray(forecast_result.conf_int(alpha=0.05), dtype=float)
        forecast_lower = np.exp(confidence[:, 0]).tolist()
        forecast_upper = np.exp(confidence[:, 1]).tolist()
        selected_test_mae = best_arima_mae
    else:
        forecast_values = [latest_close] * forecast_days
        daily_volatility = float(np.diff(log_prices).std(ddof=1)) if len(log_prices) > 2 else 0.0
        forecast_lower = [latest_close * math.exp(-1.96 * daily_volatility * math.sqrt(day)) for day in range(1, forecast_days + 1)]
        forecast_upper = [latest_close * math.exp(1.96 * daily_volatility * math.sqrt(day)) for day in range(1, forecast_days + 1)]
        selected_test_mae = naive_test_mae

    predicted_next_close = forecast_values[-1]
    pred_return = (predicted_next_close / latest_close - 1.0) * 100.0

    recent_closes = frame[["Close"]].tail(15).copy()
    prices_list = []
    for date_idx, close_row in zip(recent_closes.index, recent_closes.itertuples()):
        date_str = date_idx.strftime("%Y-%m-%d") if hasattr(date_idx, "strftime") else str(date_idx)
        prices_list.append({
            "date": date_str,
            "close": float(close_row.Close),
            "forecast": False
        })
    last_date = frame.index[-1].date() if hasattr(frame.index[-1], "date") else date.today()
    forecast_dates = _next_business_dates(last_date, forecast_days)
    for index, (forecast_date, forecast_close) in enumerate(zip(forecast_dates, forecast_values)):
        prices_list.append({
            "date": forecast_date.isoformat(),
            "close": forecast_close,
            "lower": forecast_lower[index],
            "upper": forecast_upper[index],
            "forecast": True,
        })

    summary = (
        f"시간순 롤링 검증에서 선택된 {model_name}으로 {company.company_name}의 {forecast_label} 종가를 예측한 결과, "
        f"현재가 {_format_krw(latest_close)} 대비 **{pred_return:+.2f}%** 변동한 "
        f"**{_format_krw(predicted_next_close)}**으로 전망됩니다. "
        f"95% 예측구간은 {_format_krw(forecast_lower[-1])}~{_format_krw(forecast_upper[-1])}입니다."
    )

    steps = [
        f"예측 기업: {company.company_name}({company.stock_code})",
        f"학습 기간: {start_date.isoformat()} ~ {end_date.isoformat()} (최근 {duration_years}년, {len(frame)}영업일 데이터)",
        f"최종 예측 모델: {model_name}",
        f"후보 모델: {', '.join(f'ARIMA{order}' for order in candidate_orders)}",
        f"ARIMA 최저 롤링 검증 MAE: {_format_krw(best_arima_mae) if math.isfinite(best_arima_mae) else '계산 실패'}",
        f"랜덤워크 롤링 검증 MAE: {_format_krw(naive_test_mae)}",
        *[
            f"{index}영업일 뒤: {_format_krw(value)} (95% 예측구간 {_format_krw(forecast_lower[index - 1])}~{_format_krw(forecast_upper[index - 1])})"
            for index, value in enumerate(forecast_values, 1)
        ],
        f"{forecast_label} 최종 예측치: {_format_krw(predicted_next_close)} (현재가 {_format_krw(latest_close)} 대비 {pred_return:+.2f}% 변동 예상)"
    ]

    return {
        "status": "ok",
        "mode": "arima_stock_forecast",
        "summary": summary,
        "steps": steps,
        "company": company.__dict__,
        "ticker": ticker,
        "latest_close": latest_close,
        "predicted_next_close": predicted_next_close,
        "pred_return": pred_return,
        "forecast_days": forecast_days,
        "forecast_label": forecast_label,
        "forecast_values": forecast_values,
        "test_mae": selected_test_mae,
        "arima_test_mae": best_arima_mae if math.isfinite(best_arima_mae) else None,
        "naive_test_mae": naive_test_mae,
        "arima_order": list(best_order),
        "forecast_lower": forecast_lower,
        "forecast_upper": forecast_upper,
        "model_name": model_name,
        "prices_list": prices_list
    }


def _forecast_horizon_days(question: str) -> int:
    compact = question.replace(" ", "").lower()
    if any(term in compact for term in ["다음주", "향후1주", "일주일", "1주일"]):
        return 5
    patterns = [
        r"(\d+)(?:영업일|거래일|일)(?:뒤|후)",
        r"(?:향후|앞으로)(\d+)(?:영업일|거래일|일)",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            return max(1, min(20, int(match.group(1))))
    return 1


def _forecast_horizon_label(forecast_days: int) -> str:
    if forecast_days == 1:
        return "다음 영업일"
    if forecast_days == 5:
        return "다음주(5영업일 뒤)"
    return f"{forecast_days}영업일 뒤"


def _next_business_dates(start: date, count: int) -> list[date]:
    dates = []
    candidate = start
    while len(dates) < count:
        candidate += timedelta(days=1)
        if candidate.weekday() < 5:
            dates.append(candidate)
    return dates


def compare_stock_prices(question: str, companies: list[Any]) -> dict[str, Any]:
    period = _extract_period(question)
    results = []
    failures = []
    
    for company in companies[:3]:
        ticker = _to_yahoo_ticker(company.stock_code, company.market)
        price_source = "네이버 금융"
        try:
            frame = _download_naver_price_data(company.stock_code, period["start"], period["end"])
            if frame.empty:
                fallback = _download_fallback_naver_price_data(company.stock_code, period)
                if fallback:
                    frame, _ = fallback
            if frame.empty:
                frame = _download_price_data(ticker, period["start"], period["end"])
                if not frame.empty:
                    price_source = "Yahoo Finance"
            if frame.empty:
                fallback = _download_fallback_price_data(ticker, period)
                if fallback:
                    frame, _ = fallback
                    price_source = "Yahoo Finance"
        except Exception as e:
            failures.append(f"{company.company_name}: 주가 조회 오류 ({e})")
            continue
            
        if frame.empty:
            failures.append(f"{company.company_name}: 데이터 없음")
            continue
            
        stats = _build_backtest_stats(frame)
        prices = _build_price_points(frame)
        results.append({
            "company": company.__dict__,
            "ticker": ticker,
            "price_source": price_source,
            "stats": stats,
            "prices": prices
        })
        
    if not results:
        return {
            "status": "no_data",
            "summary": "비교 대상 기업들의 주가 데이터를 조회하지 못했습니다.",
            "steps": failures
        }
        
    steps = [
        f"조회 기간: {period['start']}~{period['end']}",
    ]
    summary_parts = []
    for item in results:
        comp_name = item["company"]["company_name"]
        stats = item["stats"]
        summary_parts.append(
            f"{comp_name}은 시작 종가 {_format_krw(stats['first_close'])}, 최근 종가 {_format_krw(stats['last_close'])}로 기간 수익률 {stats['cumulative_return_display']}를 기록했습니다."
        )
        steps.append(
            f"{comp_name}: 수익률 {stats['cumulative_return_display']}, 최고/최저 {_format_krw(stats['max_close'])} / {_format_krw(stats['min_close'])}, MDD {stats['max_drawdown_display']}"
        )
        
    return {
        "status": "ok",
        "mode": "stock_price_comparison",
        "summary": " ".join(summary_parts),
        "steps": steps,
        "comparison": results,
        "period": {
            "start": period["start"].isoformat(),
            "end": period["end"].isoformat(),
            "label": period["label"]
        }
    }
