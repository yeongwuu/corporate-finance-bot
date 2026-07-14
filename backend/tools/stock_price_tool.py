from __future__ import annotations

import math
import re
import ssl
import urllib.request
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from company_data.financial_store import FinancialStatementStore


_LSTM_FORECAST_CACHE: dict[tuple, dict[str, Any]] = {}


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

    forecast_days = _forecast_horizon_days(question)
    forecast_label = _forecast_horizon_label(forecast_days)

    df = frame[["Close"]].copy()
    df["log_return"] = np.log(df["Close"] / df["Close"].shift(1))
    for i in range(5):
        df[f"return_lag_{i}"] = df["log_return"].shift(i)

    df["return_ma_5"] = df["log_return"].rolling(window=5).mean()
    df["return_ma_20"] = df["log_return"].rolling(window=20).mean()
    df["return_vol_20"] = df["log_return"].rolling(window=20).std()
    df["momentum_5"] = np.log(df["Close"] / df["Close"].shift(5))
    df["momentum_20"] = np.log(df["Close"] / df["Close"].shift(20))
    feature_df = df.dropna().copy()

    if len(feature_df) < 20 + forecast_days:
        return {
            "status": "no_data",
            "summary": "피처 구성에 필요한 학습 데이터 셋이 충분하지 않습니다.",
            "steps": ["가용 연도가 너무 짧아 이동평균선(20일)을 채우지 못했습니다."],
            "company": company.__dict__,
            "ticker": ticker,
        }

    feature_cols = [
        "return_lag_0", "return_lag_1", "return_lag_2", "return_lag_3", "return_lag_4",
        "return_ma_5", "return_ma_20", "return_vol_20", "momentum_5", "momentum_20",
    ]

    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import r2_score, mean_absolute_error

    latest_close = float(frame.iloc[-1]["Close"])
    latest_features = feature_df[feature_cols].iloc[-1:].values
    forecast_values = []
    test_r2 = 0.0
    test_mae = 0.0
    naive_test_mae = 0.0
    for horizon in range(1, forecast_days + 1):
        horizon_df = feature_df.copy()
        horizon_df["target_return"] = np.log(frame["Close"].shift(-horizon) / frame["Close"])
        horizon_df["target_close"] = frame["Close"].shift(-horizon)
        horizon_df = horizon_df.dropna()
        X = horizon_df[feature_cols].values
        y = horizon_df["target_return"].values
        split_idx = max(1, min(len(horizon_df) - 1, int(len(horizon_df) * 0.9)))
        train_end = max(1, split_idx - horizon)
        X_train, X_test = X[:train_end], X[split_idx:]
        y_train, y_test = y[:train_end], y[split_idx:]

        model = RandomForestRegressor(n_estimators=100, random_state=42 + horizon, n_jobs=-1)
        model.fit(X_train, y_train)
        if horizon == forecast_days:
            predicted_returns = model.predict(X_test)
            base_prices = horizon_df["Close"].values[split_idx:]
            actual_prices = horizon_df["target_close"].values[split_idx:]
            predicted_prices = base_prices * np.exp(predicted_returns)
            test_r2 = float(r2_score(y_test, predicted_returns)) if len(y_test) >= 2 else 0.0
            test_mae = float(mean_absolute_error(actual_prices, predicted_prices))
            naive_test_mae = float(mean_absolute_error(actual_prices, base_prices))
        model.fit(X, y)
        forecast_return = float(model.predict(latest_features)[0])
        forecast_values.append(float(latest_close * np.exp(forecast_return)))

    rf_forecast_values = list(forecast_values)
    rf_test_r2, rf_test_mae, rf_naive_test_mae = test_r2, test_mae, naive_test_mae
    lstm_result = _predict_stock_price_lstm(frame["Close"], forecast_days)
    lstm_forecast_values = lstm_result.get("forecast_values") or []
    lstm_test_r2 = lstm_result.get("test_r2")
    lstm_test_mae = lstm_result.get("test_mae")
    rf_weight, lstm_weight = 1.0, 0.0
    model_name = "기간별 직접 랜덤포레스트"
    if lstm_result.get("status") == "ok" and len(lstm_forecast_values) == forecast_days:
        if lstm_test_mae <= rf_test_mae * 1.05:
            inverse_rf = 1.0 / max(rf_test_mae, 1.0)
            inverse_lstm = 1.0 / max(lstm_test_mae, 1.0)
            lstm_weight = inverse_lstm / (inverse_rf + inverse_lstm)
            rf_weight = 1.0 - lstm_weight
            forecast_values = [
                rf_value * rf_weight + lstm_value * lstm_weight
                for rf_value, lstm_value in zip(rf_forecast_values, lstm_forecast_values)
            ]
            model_name = "랜덤포레스트·LSTM 검증 가중 앙상블"
        else:
            model_name = "랜덤포레스트 (LSTM 검증 후 성능 우선 선택)"

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
        f"{model_name}으로 {company.company_name}의 {forecast_label} 종가를 예측한 결과, "
        f"현재가 {_format_krw(latest_close)} 대비 **{pred_return:+.2f}%** 변동한 "
        f"**{_format_krw(predicted_next_close)}**으로 전망됩니다."
    )

    steps = [
        f"예측 기업: {company.company_name}({company.stock_code})",
        f"학습 기간: {start_date.isoformat()} ~ {end_date.isoformat()} (최근 {duration_years}년, {len(frame)}영업일 데이터)",
        f"최종 예측 모델: {model_name}",
        f"RF: 기간별 직접 예측 RandomForestRegressor (sklearn, n_estimators=100)",
        "LSTM: 최근 40영업일 연속 종가로 요청 기간 전체를 동시 예측",
        "RF 특징: 로그수익률 Lag 0~4, 5·20일 평균수익률, 20일 변동성, 5·20일 모멘텀",
        f"RF {forecast_label} 검증: R2 = {rf_test_r2:.4f} / MAE = {_format_krw(rf_test_mae)}",
        f"RF 무변동 기준 MAE: {_format_krw(rf_naive_test_mae)}",
        (
            f"LSTM {forecast_label} 검증: R2 = {lstm_test_r2:.4f} / MAE = {_format_krw(lstm_test_mae)}"
            if lstm_result.get("status") == "ok"
            else f"LSTM 적용 보류: {lstm_result.get('message', '학습 환경을 확인하지 못했습니다.')}"
        ),
        f"앙상블 가중치: RF {rf_weight*100:.1f}% / LSTM {lstm_weight*100:.1f}%",
        *[f"{index}영업일 뒤 예측치: {_format_krw(value)}" for index, value in enumerate(forecast_values, 1)],
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
        "forecast_values": forecast_values,
        "test_r2": test_r2,
        "test_mae": test_mae,
        "rf_test_r2": rf_test_r2,
        "rf_test_mae": rf_test_mae,
        "rf_naive_test_mae": rf_naive_test_mae,
        "lstm_test_r2": lstm_test_r2,
        "lstm_test_mae": lstm_test_mae,
        "rf_forecast_values": rf_forecast_values,
        "lstm_forecast_values": lstm_forecast_values,
        "model_name": model_name,
        "ensemble_weights": {"rf": rf_weight, "lstm": lstm_weight},
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


def _predict_stock_price_lstm(close_series: Any, forecast_days: int) -> dict[str, Any]:
    try:
        import numpy as np
        import torch
        from sklearn.metrics import mean_absolute_error, r2_score
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError:
        return {"status": "missing_dependency", "message": "PyTorch가 설치되어 있지 않습니다."}

    values = pd.to_numeric(close_series, errors="coerce").dropna().astype(float).to_numpy()
    sequence_length = 40
    if len(values) < sequence_length + forecast_days + 40:
        return {"status": "no_data", "message": "LSTM 학습에 필요한 연속 주가 데이터가 부족합니다."}

    cache_key = (
        len(values),
        round(float(values.mean()), 4),
        round(float(values.std()), 4),
        round(float(values[-1]), 4),
        forecast_days,
    )
    cached = _LSTM_FORECAST_CACHE.get(cache_key)
    if cached:
        return cached

    torch.manual_seed(42)
    np.random.seed(42)
    torch.set_num_threads(1)
    log_returns = np.diff(np.log(values))
    scale_cutoff = max(sequence_length + forecast_days, int(len(log_returns) * 0.9))
    scale_mean = float(log_returns[:scale_cutoff].mean())
    scale_std = float(log_returns[:scale_cutoff].std()) or 1.0
    normalized = (log_returns - scale_mean) / scale_std

    sequences, targets, base_prices = [], [], []
    for target_start in range(sequence_length, len(normalized) - forecast_days + 1):
        sequences.append(normalized[target_start - sequence_length:target_start])
        targets.append(normalized[target_start:target_start + forecast_days])
        base_prices.append(values[target_start])
    X = np.asarray(sequences, dtype=np.float32)[..., np.newaxis]
    y = np.asarray(targets, dtype=np.float32)
    split_idx = max(1, min(len(X) - 1, int(len(X) * 0.9)))
    train_end = max(1, split_idx - forecast_days)
    X_train = torch.from_numpy(X[:train_end])
    y_train = torch.from_numpy(y[:train_end])
    X_val = torch.from_numpy(X[split_idx:])
    y_val = torch.from_numpy(y[split_idx:])

    class PriceLSTM(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(input_size=1, hidden_size=32, num_layers=1, batch_first=True)
            self.output = nn.Linear(32, forecast_days)

        def forward(self, inputs):
            output, _ = self.lstm(inputs)
            return self.output(output[:, -1, :])

    model = PriceLSTM()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.006, weight_decay=1e-5)
    loss_fn = nn.MSELoss()
    loader = DataLoader(TensorDataset(X_train, y_train), batch_size=64, shuffle=False)
    best_loss, best_state, patience = float("inf"), None, 0
    for _ in range(45):
        model.train()
        for batch_x, batch_y in loader:
            optimizer.zero_grad()
            loss = loss_fn(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            validation_loss = float(loss_fn(model(X_val), y_val).item())
        if validation_loss < best_loss - 1e-5:
            best_loss = validation_loss
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
            patience = 0
        else:
            patience += 1
            if patience >= 7:
                break
    if best_state:
        model.load_state_dict(best_state)

    model.eval()
    with torch.no_grad():
        validation_pred_returns = model(X_val).numpy() * scale_std + scale_mean
        validation_actual_returns = y_val.numpy() * scale_std + scale_mean
        latest_sequence = torch.from_numpy(normalized[-sequence_length:].astype(np.float32).reshape(1, sequence_length, 1))
        forecast_returns = model(latest_sequence).numpy()[0] * scale_std + scale_mean
    validation_bases = np.asarray(base_prices[split_idx:], dtype=float)
    actual_cumulative_returns = validation_actual_returns.sum(axis=1)
    predicted_cumulative_returns = validation_pred_returns.sum(axis=1)
    final_actual = validation_bases * np.exp(actual_cumulative_returns)
    final_pred = validation_bases * np.exp(predicted_cumulative_returns)
    forecast = values[-1] * np.exp(np.cumsum(forecast_returns))
    result = {
        "status": "ok",
        "forecast_values": [float(value) for value in forecast],
        "test_r2": float(r2_score(actual_cumulative_returns, predicted_cumulative_returns)) if len(final_actual) >= 2 else 0.0,
        "test_mae": float(mean_absolute_error(final_actual, final_pred)),
        "naive_test_mae": float(mean_absolute_error(final_actual, validation_bases)),
        "sequence_length": sequence_length,
    }
    if len(_LSTM_FORECAST_CACHE) >= 32:
        _LSTM_FORECAST_CACHE.pop(next(iter(_LSTM_FORECAST_CACHE)))
    _LSTM_FORECAST_CACHE[cache_key] = result
    return result


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
