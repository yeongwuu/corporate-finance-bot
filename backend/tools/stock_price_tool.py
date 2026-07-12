from __future__ import annotations

import math
import re
import ssl
import urllib.request
from datetime import date, timedelta
from typing import Any

import pandas as pd

from company_data.financial_store import FinancialStatementStore


def analyze_stock_price(question: str) -> dict[str, Any]:
    store = FinancialStatementStore()
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
        return predict_stock_price_rf(question, company)
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

    return {
        "status": "ok",
        "summary": summary,
        "steps": steps,
        "company": company.__dict__,
        "ticker": ticker,
        "price_source": price_source,
        "period": period,
        "prices": prices,
        "stats": stats,
    }


def _download_price_data(ticker: str, start: date, end: date) -> pd.DataFrame:
    import yfinance as yf

    frame = yf.download(
        ticker,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        progress=False,
        auto_adjust=True,
        threads=False,
    )
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    return frame.dropna(subset=["Close"]) if "Close" in frame else pd.DataFrame()


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
    return frame.sort_index()


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
    with urllib.request.urlopen(request, timeout=10, context=_ssl_context()) as response:
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
    today = date.today()
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


def _to_yahoo_ticker(stock_code: str, market: str | None) -> str:
    code = stock_code.zfill(6)
    if market and "KOSDAQ" in market.upper():
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


def predict_stock_price_rf(question: str, company: Any) -> dict[str, Any]:
    if not company:
        return {
            "status": "needs_company",
            "summary": "주가를 예측할 회사명을 찾지 못했습니다.",
            "steps": ["예: 삼성전자 최근 3년 주가를 예측해줘"],
        }

    duration_years = 5
    match = re.search(r"최근\s*(\d+)\s*(?:개년|년)", question)
    if match:
        duration_years = max(1, min(10, int(match.group(1))))

    end_date = date.today()
    start_date = end_date - timedelta(days=int(duration_years * 365.25))

    ticker = _to_yahoo_ticker(company.stock_code, company.market)
    naver_error = None
    try:
        frame = _download_naver_price_data(company.stock_code, start_date, end_date)
    except Exception as exc:
        naver_error = exc
        frame = pd.DataFrame()

    if frame.empty:
        try:
            frame = _download_price_data(ticker, start_date, end_date)
        except Exception as yahoo_error:
            return {
                "status": "price_fetch_error",
                "summary": f"{company.company_name}의 주가 데이터를 불러오지 못했습니다.",
                "steps": [
                    f"네이버 금융 조회 오류: {naver_error or '데이터 없음'}",
                    f"Yahoo Finance 조회 오류: {yahoo_error}",
                ],
                "company": company.__dict__,
                "ticker": ticker,
            }

    if frame.empty or len(frame) < 30:
        return {
            "status": "no_data",
            "summary": f"{company.company_name}의 주가 예측에 필요한 주가 시계열 데이터가 부족합니다.",
            "steps": [f"가용 데이터 개수: {len(frame)}개 (최소 30영업일 이상 필요)"],
            "company": company.__dict__,
            "ticker": ticker,
        }

    import numpy as np
    import pandas as pd

    df = frame[["Close"]].copy()
    df["target"] = df["Close"].shift(-1)

    for i in range(1, 6):
        df[f"lag_{i}"] = df["Close"].shift(i)

    df["ma_5"] = df["Close"].rolling(window=5).mean()
    df["ma_20"] = df["Close"].rolling(window=20).mean()
    df = df.dropna()

    if len(df) < 20:
        return {
            "status": "no_data",
            "summary": "피처 구성에 필요한 학습 데이터 셋이 충분하지 않습니다.",
            "steps": ["가용 연도가 너무 짧아 이동평균선(20일)을 채우지 못했습니다."],
            "company": company.__dict__,
            "ticker": ticker,
        }

    feature_cols = ["lag_1", "lag_2", "lag_3", "lag_4", "lag_5", "ma_5", "ma_20"]
    X = df[feature_cols].values
    y = df["target"].values

    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import r2_score, mean_absolute_error

    split_idx = int(len(df) * 0.9)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    test_r2 = float(r2_score(y_test, y_pred))
    test_mae = float(mean_absolute_error(y_test, y_pred))

    model.fit(X, y)

    latest_close = float(frame.iloc[-1]["Close"])
    forecast_days = _forecast_horizon_days(question)
    forecast_label = "다음주(5영업일)" if forecast_days == 5 else "다음 영업일"
    rolling_closes = [float(value) for value in frame["Close"].values]
    forecast_values = []
    for _ in range(forecast_days):
        lags = [rolling_closes[-i] for i in range(1, 6)]
        ma5 = float(np.mean(rolling_closes[-5:]))
        ma20 = float(np.mean(rolling_closes[-20:]))
        predicted_close = float(model.predict(np.array([[*lags, ma5, ma20]]))[0])
        forecast_values.append(predicted_close)
        rolling_closes.append(predicted_close)

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
    for forecast_date, forecast_close in zip(forecast_dates, forecast_values):
        prices_list.append({
            "date": forecast_date.isoformat(),
            "close": forecast_close,
            "forecast": True,
        })

    summary = (
        f"랜덤포레스트 회귀모델로 {company.company_name}의 {forecast_label} 종가를 예측한 결과, "
        f"현재가 {_format_krw(latest_close)} 대비 **{pred_return:+.2f}%** 변동한 "
        f"**{_format_krw(predicted_next_close)}**으로 전망됩니다. (검증 셋 결정계수 $R^2$: {test_r2:.2f}, MAE: {_format_krw(test_mae)})"
    )

    steps = [
        f"예측 기업: {company.company_name}({company.stock_code})",
        f"학습 기간: {start_date.isoformat()} ~ {end_date.isoformat()} (최근 {duration_years}년, {len(frame)}영업일 데이터)",
        f"학습 알고리즘: RandomForestRegressor (sklearn, n_estimators=100)",
        f"사용 특징(Features): Lag 1~5일 종가, 5일 이동평균(MA5), 20일 이동평균(MA20)",
        f"검증 스코어: R2 결정계수 = {test_r2:.4f} / MAE = {_format_krw(test_mae)}",
        f"{forecast_label} 최종 예측치: {_format_krw(predicted_next_close)} (현재가 {_format_krw(latest_close)} 대비 {pred_return:+.2f}% 변동 예상)"
    ]

    return {
        "status": "ok",
        "mode": "rf_stock_forecast",
        "summary": summary,
        "steps": steps,
        "company": company.__dict__,
        "ticker": ticker,
        "latest_close": latest_close,
        "predicted_next_close": predicted_next_close,
        "pred_return": pred_return,
        "forecast_days": forecast_days,
        "forecast_label": forecast_label,
        "test_r2": test_r2,
        "test_mae": test_mae,
        "prices_list": prices_list
    }


def _forecast_horizon_days(question: str) -> int:
    compact = question.replace(" ", "").lower()
    return 5 if any(term in compact for term in ["다음주", "향후1주", "일주일", "1주일"]) else 1


def _next_business_dates(start: date, count: int) -> list[date]:
    dates = []
    candidate = start
    while len(dates) < count:
        candidate += timedelta(days=1)
        if candidate.weekday() < 5:
            dates.append(candidate)
    return dates
