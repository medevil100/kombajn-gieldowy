import os
import json
import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from openai import OpenAI
from tavily import TavilyClient


# =========================================================
# 1. KONFIGURACJA STRONY
# =========================================================

st.set_page_config(
    page_title="AI Monte Carlo Advanced Predictor",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📈 Zaawansowany Predyktor Monte Carlo 52 tygodnie & Deep AI Analyst")


# =========================================================
# 2. KLUCZE API
# =========================================================

def get_key(name: str) -> Optional[str]:
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass

    return os.getenv(name)


OPENAI_KEY = get_key("OPENAI_API_KEY")
TAVILY_KEY = get_key("TAVILY_API_KEY")

openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
tavily_client = TavilyClient(api_key=TAVILY_KEY) if TAVILY_KEY else None


# =========================================================
# 3. PARAMETRY
# =========================================================

DNI_HANDLOWE_ROK = 252
MIN_LICZBA_DANYCH = 80


# =========================================================
# 4. FUNKCJE FORMATUJĄCE
# =========================================================

def fmt_money(value, currency: str = "USD") -> str:
    try:
        value = float(value)
        if np.isnan(value):
            return "brak"
        return f"{value:,.2f} {currency}".replace(",", " ")
    except Exception:
        return "brak"


def fmt_pct(value) -> str:
    try:
        value = float(value)
        if np.isnan(value):
            return "brak"
        return f"{value * 100:.2f}%"
    except Exception:
        return "brak"


def fmt_number(value, digits: int = 2) -> str:
    try:
        value = float(value)
        if np.isnan(value):
            return "brak"
        return f"{value:.{digits}f}"
    except Exception:
        return "brak"


def clean_text(text: str, limit: int = 1200) -> str:
    if text is None:
        return ""

    text = str(text)
    for ch in ["{", "}", "[", "]"]:
        text = text.replace(ch, "")

    return text[:limit]


# =========================================================
# 5. DANE Z YAHOO FINANCE
# =========================================================

@st.cache_data(show_spinner=False, ttl=1800)
def load_price_history(ticker: str, years: int = 3) -> pd.DataFrame:
    end = dt.date.today() + dt.timedelta(days=1)
    start = dt.date.today() - dt.timedelta(days=365 * years + 10)

    df = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        threads=False
    )

    if df is None or df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        if "Close" in df.columns.get_level_values(0):
            df.columns = df.columns.get_level_values(0)
        else:
            df.columns = df.columns.get_level_values(-1)

    df.columns = [str(c).strip().capitalize() for c in df.columns]

    if "Close" not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=["Close"])

    return df


@st.cache_data(show_spinner=False, ttl=3600)
def load_fundamentals(ticker: str, last_price: float) -> dict:
    result = {
        "currency": "USD",
        "shares_outstanding": None,
        "net_income_ttm": None,
        "eps_ttm": None,
        "pe_ttm": None,
        "target_mean_price": None,
        "target_text": "Brak danych",
        "eps_text": "Brak stabilnych danych",
        "pe_text": "Brak stabilnych danych",
    }

    ticker_obj = yf.Ticker(ticker)

    info = {}
    try:
        info = ticker_obj.info or {}
    except Exception:
        info = {}

    try:
        currency = info.get("currency")
        if currency:
            result["currency"] = str(currency)
    except Exception:
        pass

    try:
        shares = info.get("sharesOutstanding")
        if shares and float(shares) > 0:
            result["shares_outstanding"] = float(shares)
    except Exception:
        pass

    try:
        target = info.get("targetMeanPrice")
        if target is not None and float(target) > 0:
            result["target_mean_price"] = float(target)
            result["target_text"] = f"{float(target):.2f} {result['currency']}"
    except Exception:
        pass

    try:
        income_stmt = ticker_obj.quarterly_income_stmt

        if income_stmt is not None and not income_stmt.empty:
            net_income_series = None

            if "Net Income" in income_stmt.index:
                net_income_series = income_stmt.loc["Net Income"]
            else:
                mask = income_stmt.index.astype(str).str.contains("Net Income", case=False, na=False)
                matches = income_stmt.loc[mask]
                if not matches.empty:
                    net_income_series = matches.iloc[0]

            if net_income_series is not None:
                vals = pd.to_numeric(net_income_series, errors="coerce").dropna()

                if len(vals) >= 4:
                    net_income_ttm = float(vals.iloc[:4].sum())
                    result["net_income_ttm"] = net_income_ttm

    except Exception:
        pass

    if result["shares_outstanding"] is None:
        try:
            balance_sheet = ticker_obj.quarterly_balance_sheet

            if balance_sheet is not None and not balance_sheet.empty:
                if "Ordinary Shares Number" in balance_sheet.index:
                    shares_series = balance_sheet.loc["Ordinary Shares Number"]
                    vals = pd.to_numeric(shares_series, errors="coerce").dropna()

                    if not vals.empty and float(vals.iloc[0]) > 0:
                        result["shares_outstanding"] = float(vals.iloc[0])
        except Exception:
            pass

    try:
        net_income = result["net_income_ttm"]
        shares = result["shares_outstanding"]

        if net_income is not None and shares is not None and shares > 0:
            eps = net_income / shares
            result["eps_ttm"] = eps
            result["eps_text"] = f"{eps:.2f} {result['currency']}"

            if eps > 0:
                pe = last_price / eps
                result["pe_ttm"] = pe
                result["pe_text"] = f"{pe:.2f}"
            else:
                result["pe_text"] = "Ujemny EPS / P/E niemiarodajne"

    except Exception:
        pass

    return result


# =========================================================
# 6. NEWSY TAVILY
# =========================================================

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_news_tavily(ticker: str, company_query: str = "") -> str:
    if tavily_client is None:
        return "Brak klucza Tavily — newsy nie zostały pobrane."

    current_year = dt.date.today().year

    query = (
        f"{ticker} stock financial catalysts earnings revenue margins AI products risks "
        f"supply chain competition outlook {current_year}"
    )

    if company_query:
        query += f" {company_query}"

    try:
        response = tavily_client.search(
            query=query,
            max_results=6,
            search_depth="advanced"
        )

        results = response.get("results", [])

        if not results:
            return "Brak istotnych newsów."

        lines = []

        for i, item in enumerate(results, start=1):
            title = clean_text(item.get("title", ""), 250)
            content = clean_text(item.get("content", ""), 700)
            url = clean_text(item.get("url", ""), 300)

            lines.append(
                f"Artykuł {i}: {title}\n"
                f"Treść: {content}\n"
                f"Źródło: {url}"
            )

        return "\n\n".join(lines)

    except Exception as e:
        return f"Brak możliwości pobrania newsów: {e}"


# =========================================================
# 7. WSKAŹNIKI TECHNICZNE: ATR, SMI, NAC, TREND
# =========================================================

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    close = pd.to_numeric(df["Close"], errors="coerce")

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    return true_range.rolling(period).mean()


def calculate_smi(
    df: pd.DataFrame,
    k_period: int = 14,
    smooth_1: int = 3,
    smooth_2: int = 3,
    signal_period: int = 5
) -> pd.DataFrame:
    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    close = pd.to_numeric(df["Close"], errors="coerce")

    highest_high = high.rolling(k_period).max()
    lowest_low = low.rolling(k_period).min()

    midpoint = (highest_high + lowest_low) / 2
    distance = close - midpoint
    range_hl = highest_high - lowest_low

    distance_smoothed = ema(ema(distance, smooth_1), smooth_2)
    range_smoothed = ema(ema(range_hl, smooth_1), smooth_2)

    denominator = 0.5 * range_smoothed
    smi = 100 * distance_smoothed / denominator.replace(0, np.nan)
    smi_signal = ema(smi, signal_period)

    return pd.DataFrame(
        {
            "SMI": smi,
            "SMI_signal": smi_signal
        }
    )


def calculate_nac(
    close: pd.Series,
    bandwidth: float = 8.0,
    window: int = 80,
    band_window: int = 50,
    band_mult: float = 2.0
) -> pd.DataFrame:
    """
    NAC = Nadaraya-Watson Adaptive Channel.
    Wygładzona średnia ceny plus/minus zmienność reszt.
    """
    close = pd.to_numeric(close, errors="coerce").astype(float)
    values = close.values
    n = len(values)

    smoothed = np.full(n, np.nan)

    for i in range(n):
        start = max(0, i - window + 1)
        idx = np.arange(start, i + 1)

        x = idx - i
        weights = np.exp(-0.5 * (x / bandwidth) ** 2)

        vals = values[start:i + 1]
        mask = ~np.isnan(vals)

        if mask.sum() > 0:
            smoothed[i] = np.sum(weights[mask] * vals[mask]) / np.sum(weights[mask])

    nac_mid = pd.Series(smoothed, index=close.index)
    residual = close - nac_mid
    width = residual.rolling(band_window).std() * band_mult

    nac_upper = nac_mid + width
    nac_lower = nac_mid - width

    return pd.DataFrame(
        {
            "NAC_mid": nac_mid,
            "NAC_upper": nac_upper,
            "NAC_lower": nac_lower
        }
    )


def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["Close"] = pd.to_numeric(out["Close"], errors="coerce")

    out["SMA20"] = out["Close"].rolling(20).mean()
    out["SMA50"] = out["Close"].rolling(50).mean()
    out["SMA200"] = out["Close"].rolling(200).mean()

    out["EMA20"] = ema(out["Close"], 20)
    out["EMA20_slope_10d_pct"] = out["EMA20"].pct_change(10)

    if {"High", "Low", "Close"}.issubset(out.columns):
        out["ATR14"] = calculate_atr(out, 14)

        smi_df = calculate_smi(out)
        out["SMI"] = smi_df["SMI"]
        out["SMI_signal"] = smi_df["SMI_signal"]
    else:
        out["ATR14"] = np.nan
        out["SMI"] = np.nan
        out["SMI_signal"] = np.nan

    nac_df = calculate_nac(out["Close"])
    out["NAC_mid"] = nac_df["NAC_mid"]
    out["NAC_upper"] = nac_df["NAC_upper"]
    out["NAC_lower"] = nac_df["NAC_lower"]

    return out


def get_trend_assessment(tech: pd.DataFrame) -> dict:
    latest = tech.dropna(subset=["Close"]).iloc[-1]

    close = float(latest.get("Close", np.nan))
    sma50 = float(latest.get("SMA50", np.nan))
    sma200 = float(latest.get("SMA200", np.nan))
    ema_slope = float(latest.get("EMA20_slope_10d_pct", np.nan))
    smi = float(latest.get("SMI", np.nan))
    smi_signal = float(latest.get("SMI_signal", np.nan))
    nac_mid = float(latest.get("NAC_mid", np.nan))
    nac_upper = float(latest.get("NAC_upper", np.nan))
    nac_lower = float(latest.get("NAC_lower", np.nan))

    score = 0
    reasons = []

    if not np.isnan(close) and not np.isnan(sma50):
        if close > sma50:
            score += 1
            reasons.append("cena powyżej SMA50")
        else:
            score -= 1
            reasons.append("cena poniżej SMA50")

    if not np.isnan(sma50) and not np.isnan(sma200):
        if sma50 > sma200:
            score += 1
            reasons.append("SMA50 powyżej SMA200")
        else:
            score -= 1
            reasons.append("SMA50 poniżej SMA200")

    if not np.isnan(ema_slope):
        if ema_slope > 0:
            score += 1
            reasons.append("dodatnie nachylenie EMA20")
        else:
            score -= 1
            reasons.append("ujemne nachylenie EMA20")

    if not np.isnan(smi) and not np.isnan(smi_signal):
        if smi > smi_signal:
            score += 1
            reasons.append("SMI powyżej linii sygnału")
        else:
            score -= 1
            reasons.append("SMI poniżej linii sygnału")

    if not np.isnan(close) and not np.isnan(nac_mid):
        if close > nac_mid:
            score += 1
            reasons.append("cena powyżej środka kanału NAC")
        else:
            score -= 1
            reasons.append("cena poniżej środka kanału NAC")

    if score >= 3:
        trend = "byczy"
    elif score <= -3:
        trend = "niedźwiedzi"
    else:
        trend = "neutralny"

    if not np.isnan(close) and not np.isnan(nac_upper) and close > nac_upper:
        nac_position = "powyżej górnego pasma NAC — możliwe wykupienie / silny momentum"
    elif not np.isnan(close) and not np.isnan(nac_lower) and close < nac_lower:
        nac_position = "poniżej dolnego pasma NAC — możliwe wyprzedanie / presja podażowa"
    elif not np.isnan(close) and not np.isnan(nac_mid):
        if close >= nac_mid:
            nac_position = "w kanale NAC, powyżej środka"
        else:
            nac_position = "w kanale NAC, poniżej środka"
    else:
        nac_position = "brak danych"

    return {
        "trend": trend,
        "trend_score": score,
        "reasons": reasons,
        "close": close,
        "sma50": sma50,
        "sma200": sma200,
        "ema20_slope_10d_pct": ema_slope,
        "smi": smi,
        "smi_signal": smi_signal,
        "nac_mid": nac_mid,
        "nac_upper": nac_upper,
        "nac_lower": nac_lower,
        "nac_position": nac_position,
    }


def calculate_sl_tp(
    tech: pd.DataFrame,
    trend_info: dict,
    sl_atr_mult: float = 1.5,
    tp1_atr_mult: float = 1.5,
    tp2_atr_mult: float = 3.0
) -> dict:
    latest = tech.dropna(subset=["Close"]).iloc[-1]

    close = float(latest.get("Close", np.nan))
    atr = float(latest.get("ATR14", np.nan))

    recent = tech.dropna(subset=["Close"]).tail(20)

    support20 = float(recent["Low"].min()) if "Low" in recent.columns else np.nan
    resistance20 = float(recent["High"].max()) if "High" in recent.columns else np.nan

    if np.isnan(atr) or atr <= 0:
        return {
            "direction": "brak",
            "stop_loss": None,
            "take_profit_1": None,
            "take_profit_2": None,
            "risk_reward_tp1": None,
            "risk_reward_tp2": None,
            "support20": support20,
            "resistance20": resistance20,
            "comment": "Brak stabilnego ATR — nie można wyliczyć SL/TP."
        }

    trend = trend_info.get("trend", "neutralny")

    if trend == "niedźwiedzi":
        direction = "SHORT / defensywnie"
        stop_loss = close + sl_atr_mult * atr
        take_profit_1 = min(close - tp1_atr_mult * atr, support20) if not np.isnan(support20) else close - tp1_atr_mult * atr
        take_profit_2 = close - tp2_atr_mult * atr

        risk = stop_loss - close
        reward1 = close - take_profit_1
        reward2 = close - take_profit_2

    else:
        direction = "LONG / wzrostowo"
        stop_loss_atr = close - sl_atr_mult * atr
        stop_loss_support = support20 - 0.25 * atr if not np.isnan(support20) else stop_loss_atr

        stop_loss = min(stop_loss_atr, stop_loss_support)

        take_profit_1 = max(close + tp1_atr_mult * atr, resistance20) if not np.isnan(resistance20) else close + tp1_atr_mult * atr
        take_profit_2 = close + tp2_atr_mult * atr

        risk = close - stop_loss
        reward1 = take_profit_1 - close
        reward2 = take_profit_2 - close

    rr1 = reward1 / risk if risk > 0 else np.nan
    rr2 = reward2 / risk if risk > 0 else np.nan

    return {
        "direction": direction,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "risk_reward_tp1": rr1,
        "risk_reward_tp2": rr2,
        "support20": support20,
        "resistance20": resistance20,
        "atr14": atr,
        "comment": "Poziomy orientacyjne, wyliczone technicznie z ATR i ostatnich ekstremów cenowych."
    }


# =========================================================
# 8. MONTE CARLO
# =========================================================

def run_monte_carlo(
    close_prices: pd.Series,
    liczba_symulacji: int,
    dni_prognozy: int,
    target_mean_price: Optional[float] = None,
    seed: Optional[int] = None
) -> dict:
    close_prices = close_prices.dropna()

    if len(close_prices) < MIN_LICZBA_DANYCH:
        raise ValueError("Za mało danych historycznych do wykonania Monte Carlo.")

    last_price = float(close_prices.iloc[-1])

    log_returns = np.log(close_prices / close_prices.shift(1)).dropna()

    if log_returns.empty or len(log_returns) < 30:
        raise ValueError("Za mało dziennych zwrotów do wykonania Monte Carlo.")

    mu_hist = float(log_returns.mean())
    sigma_hist = float(log_returns.std())

    if np.isnan(mu_hist):
        mu_hist = 0.0

    if np.isnan(sigma_hist) or sigma_hist <= 0:
        raise ValueError("Nieprawidłowa zmienność historyczna.")

    analyst_daily_mu = None

    try:
        if target_mean_price is not None:
            target_float = float(target_mean_price)
            if target_float > 0 and last_price > 0:
                analyst_daily_mu = np.log(target_float / last_price) / DNI_HANDLOWE_ROK
    except Exception:
        analyst_daily_mu = None

    if analyst_daily_mu is not None and not np.isnan(analyst_daily_mu):
        expected_mu = (mu_hist + analyst_daily_mu) / 2
    else:
        expected_mu = mu_hist

    rng = np.random.default_rng(seed)

    random_log_returns = rng.normal(
        loc=expected_mu,
        scale=sigma_hist,
        size=(dni_prognozy, liczba_symulacji)
    )

    daily_growth = np.exp(random_log_returns)
    paths_without_initial = last_price * np.cumprod(daily_growth, axis=0)

    initial_row = np.full((1, liczba_symulacji), last_price)
    price_paths = np.vstack([initial_row, paths_without_initial])

    scenario_bear = np.percentile(price_paths, 10, axis=1)
    scenario_hold = np.percentile(price_paths, 50, axis=1)
    scenario_bull = np.percentile(price_paths, 90, axis=1)

    final_prices = price_paths[-1, :]

    probability_above_current = float(np.mean(final_prices > last_price))
    probability_above_target = None

    try:
        if target_mean_price is not None:
            target_float = float(target_mean_price)
            if target_float > 0:
                probability_above_target = float(np.mean(final_prices > target_float))
    except Exception:
        probability_above_target = None

    return {
        "last_price": last_price,
        "mu_hist": mu_hist,
        "sigma_hist": sigma_hist,
        "expected_mu": expected_mu,
        "price_paths": price_paths,
        "bear": scenario_bear,
        "hold": scenario_hold,
        "bull": scenario_bull,
        "final_prices": final_prices,
        "probability_above_current": probability_above_current,
        "probability_above_target": probability_above_target,
    }


# =========================================================
# 9. WYKRESY
# =========================================================

def build_mc_chart(
    ticker: str,
    close_prices: pd.Series,
    bear: np.ndarray,
    hold: np.ndarray,
    bull: np.ndarray,
    currency: str
) -> go.Figure:

    hist = close_prices.dropna().tail(120).values
    x_hist = np.arange(-len(hist) + 1, 1)
    x_future = np.arange(0, len(bear))

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=x_hist,
            y=hist,
            mode="lines",
            name="Historia — ostatnie 120 sesji",
            line=dict(color="black", width=2)
        )
    )

    fig.add_trace(
        go.Scatter(
            x=x_future,
            y=bear,
            mode="lines",
            name="BEAR 10%",
            line=dict(color="red", width=2.5)
        )
    )

    fig.add_trace(
        go.Scatter(
            x=x_future,
            y=bull,
            mode="lines",
            name="BULL 90%",
            line=dict(color="green", width=2.5),
            fill="tonexty",
            fillcolor="rgba(0, 180, 0, 0.08)"
        )
    )

    fig.add_trace(
        go.Scatter(
            x=x_future,
            y=hold,
            mode="lines",
            name="HOLD 50% / mediana",
            line=dict(color="blue", width=2.2, dash="dash")
        )
    )

    fig.add_vline(
        x=0,
        line_width=1.5,
        line_dash="dot",
        line_color="purple"
    )

    fig.update_layout(
        title=f"Monte Carlo — prognoza dla {ticker}",
        xaxis_title="Dni giełdowe, 0 = dzisiaj",
        yaxis_title=f"Cena akcji ({currency})",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )

    return fig


def build_technical_chart(
    ticker: str,
    tech: pd.DataFrame,
    sltp: dict,
    currency: str
) -> go.Figure:

    view = tech.tail(220).copy()

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=view.index,
            y=view["Close"],
            mode="lines",
            name="Close",
            line=dict(color="black", width=2)
        )
    )

    for col, color in [
        ("SMA50", "blue"),
        ("SMA200", "orange"),
        ("NAC_mid", "purple"),
        ("NAC_upper", "green"),
        ("NAC_lower", "red"),
    ]:
        if col in view.columns:
            fig.add_trace(
                go.Scatter(
                    x=view.index,
                    y=view[col],
                    mode="lines",
                    name=col,
                    line=dict(color=color, width=1.4, dash="dash" if "NAC" in col else "solid")
                )
            )

    last_date = view.index[-1]

    if sltp.get("stop_loss") is not None:
        fig.add_hline(
            y=sltp["stop_loss"],
            line_dash="dot",
            line_color="red",
            annotation_text="SL",
            annotation_position="bottom right"
        )

    if sltp.get("take_profit_1") is not None:
        fig.add_hline(
            y=sltp["take_profit_1"],
            line_dash="dot",
            line_color="green",
            annotation_text="TP1",
            annotation_position="top right"
        )

    if sltp.get("take_profit_2") is not None:
        fig.add_hline(
            y=sltp["take_profit_2"],
            line_dash="dash",
            line_color="darkgreen",
            annotation_text="TP2",
            annotation_position="top right"
        )

    fig.update_layout(
        title=f"Technika: Trend, NAC, SL/TP — {ticker}",
        xaxis_title="Data",
        yaxis_title=f"Cena ({currency})",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )

    return fig


def build_smi_chart(ticker: str, tech: pd.DataFrame) -> go.Figure:
    view = tech.tail(220).copy()

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=view.index,
            y=view["SMI"],
            mode="lines",
            name="SMI",
            line=dict(color="blue", width=2)
        )
    )

    fig.add_trace(
        go.Scatter(
            x=view.index,
            y=view["SMI_signal"],
            mode="lines",
            name="SMI signal",
            line=dict(color="orange", width=1.7)
        )
    )

    fig.add_hline(y=40, line_dash="dot", line_color="red", annotation_text="wykupienie +40")
    fig.add_hline(y=-40, line_dash="dot", line_color="green", annotation_text="wyprzedanie -40")
    fig.add_hline(y=0, line_dash="dash", line_color="gray")

    fig.update_layout(
        title=f"SMI — Stochastic Momentum Index dla {ticker}",
        xaxis_title="Data",
        yaxis_title="SMI",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )

    return fig


# =========================================================
# 10. RAPORT AI
# =========================================================

def generate_ai_report(dane_rynkowe: dict) -> str:
    if openai_client is None:
        return "Brak klucza OpenAI — raport AI nie został wygenerowany."

    system_prompt = (
        "Jesteś profesjonalnym analitykiem rynku akcji. "
        "Piszesz po polsku, konkretnie i bez lania wody. "
        "Twoim zadaniem jest przygotować raport inwestycyjny na podstawie dostarczonych danych. "
        "Nie udawaj pewności, jeśli dane są niepełne. "
        "Wyraźnie rozdziel fakty, model statystyczny i interpretację. "
        "Nie dawaj gwarancji zysków. "
        "Dodaj krótkie zastrzeżenie, że to nie jest rekomendacja inwestycyjna."
    )

    user_prompt = f"""
Otrzymujesz dane rynkowe w formacie JSON:

{json.dumps(dane_rynkowe, ensure_ascii=False, indent=2)}

Przygotuj profesjonalny raport po polsku.

Struktura raportu:

1. WERDYKT
- Jeden z wariantów: byczy / neutralny / niedźwiedzi.
- Krótkie uzasadnienie w 3–5 zdaniach.

2. OBRAZ TECHNICZNO-STATYSTYCZNY
- Omów wyniki Monte Carlo.
- Odnieś się do scenariuszy BEAR, HOLD i BULL.
- Oceń prawdopodobieństwo zamknięcia okresu powyżej obecnej ceny.

3. TREND, SMI I NAC
- Oceń trend.
- Omów SMI i linię sygnału.
- Omów położenie ceny względem kanału NAC.

4. FUNDAMENTY
- Oceń EPS TTM i P/E, jeśli dane są dostępne.
- Jeżeli P/E jest niedostępne albo EPS jest ujemny, jasno to wyjaśnij.
- Odnieś się do ceny docelowej analityków, jeśli jest dostępna.

5. SENTYMENT I NEWSY
- Wypunktuj najważniejsze czynniki z newsów.
- Oddziel katalizatory pozytywne od ryzyk.

6. POZIOMY SL / TP
- Omów orientacyjne SL, TP1 i TP2.
- Oceń relację risk/reward.
- Wyraźnie zaznacz, że poziomy są techniczne i orientacyjne.

7. SCENARIUSZ BEAR
- Podaj orientacyjny poziom cenowy z modelu.
- Wskaż konkretne ryzyka biznesowe, rynkowe lub wynikowe.

8. SCENARIUSZ BASE / HOLD
- Podaj orientacyjny poziom cenowy z modelu.
- Opisz realistyczną narrację bazową.

9. SCENARIUSZ BULL
- Podaj orientacyjny poziom cenowy z modelu.
- Wskaż konkretne katalizatory wzrostowe.

10. PODSUMOWANIE
- Krótka konkluzja.
- Najważniejsze poziomy do obserwacji.
- Zastrzeżenie: to nie jest rekomendacja inwestycyjna.

Pisz konkretnie.
"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.35,
            max_tokens=2200
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Błąd generowania raportu AI: {e}"


# =========================================================
# 11. SIDEBAR
# =========================================================

st.sidebar.header("⚙️ Parametry analizy")

with st.sidebar.expander("Status API"):
    st.write("OpenAI:", "✅ aktywny" if OPENAI_KEY else "❌ brak")
    st.write("Tavily:", "✅ aktywny" if TAVILY_KEY else "❌ brak")

ticker = st.sidebar.text_input(
    "Ticker spółki",
    value="AAPL",
    help="Przykłady: AAPL, MSFT, TSLA, NVDA, AMZN"
).upper().strip()

liczba_symulacji = st.sidebar.slider(
    "Liczba symulacji Monte Carlo",
    min_value=1000,
    max_value=10000,
    value=5000,
    step=1000
)

dni_prognozy = st.sidebar.slider(
    "Horyzont prognozy — dni giełdowe",
    min_value=60,
    max_value=252,
    value=252,
    step=21
)

seed_input = st.sidebar.number_input(
    "Seed Monte Carlo",
    min_value=0,
    max_value=999999,
    value=42,
    step=1,
    help="Dzięki seed wyniki Monte Carlo są powtarzalne."
)

st.sidebar.subheader("🎯 SL / TP")

sl_atr_mult = st.sidebar.slider(
    "SL — mnożnik ATR",
    min_value=0.5,
    max_value=4.0,
    value=1.5,
    step=0.25
)

tp1_atr_mult = st.sidebar.slider(
    "TP1 — mnożnik ATR",
    min_value=0.5,
    max_value=5.0,
    value=1.5,
    step=0.25
)

tp2_atr_mult = st.sidebar.slider(
    "TP2 — mnożnik ATR",
    min_value=1.0,
    max_value=8.0,
    value=3.0,
    step=0.25
)

company_query = st.sidebar.text_input(
    "Dodatkowe hasła do newsów, opcjonalnie",
    value=""
)

generuj = st.sidebar.button("🚀 Uruchom głęboką analizę")


# =========================================================
# 12. GŁÓWNA LOGIKA APLIKACJI
# =========================================================

if not OPENAI_KEY:
    st.warning("⚠️ Brak OPENAI_API_KEY — część AI nie będzie działać.")

if not TAVILY_KEY:
    st.warning("⚠️ Brak TAVILY_API_KEY — newsy Tavily nie będą pobierane.")

st.info(
    "Aplikacja wykonuje symulację Monte Carlo, analizę techniczną, SMI, NAC, SL/TP "
    "oraz generuje raport AI na bazie danych rynkowych, fundamentalnych i newsów."
)

with st.expander("Założenia modelu Monte Carlo i wskaźników"):
    st.write(
        """
        Model Monte Carlo zakłada, że dzienne logarytmiczne stopy zwrotu są losowane
        z rozkładu normalnego o średniej i zmienności oszacowanej z danych historycznych.
        Jeżeli dostępny jest target analityków, wpływa on częściowo na dryf modelu.

        SMI to Stochastic Momentum Index — wskaźnik momentum.
        NAC w tej aplikacji oznacza Nadaraya-Watson Adaptive Channel —
        wygładzony kanał ceny oparty o estymację Nadaraya-Watson i zmienność reszt.
        SL/TP są poziomami orientacyjnymi opartymi o ATR i lokalne poziomy wsparcia/oporu.
        """
    )

if generuj:
    if not ticker:
        st.error("Podaj ticker.")
        st.stop()

    with st.spinner("Pobieranie danych cenowych z Yahoo Finance..."):
        dane = load_price_history(ticker, years=3)

    if dane.empty:
        st.error(f"❌ Nie udało się pobrać poprawnych danych cenowych dla tickera: {ticker}")
        st.stop()

    if "Close" not in dane.columns:
        st.error("❌ Brak kolumny Close w danych z Yahoo Finance.")
        st.write("Dostępne kolumny:", dane.columns.tolist())
        st.stop()

    ceny_zamkniecia = dane["Close"].dropna()

    if len(ceny_zamkniecia) < MIN_LICZBA_DANYCH:
        st.error("❌ Za mało danych historycznych do wykonania analizy.")
        st.stop()

    ostatnia_cena = float(ceny_zamkniecia.iloc[-1])

    with st.spinner("Pobieranie danych fundamentalnych..."):
        fundamentals = load_fundamentals(ticker, ostatnia_cena)

    currency = fundamentals.get("currency", "USD")
    target_mean_price = fundamentals.get("target_mean_price")

    with st.spinner("Liczenie wskaźników technicznych: SMI, NAC, trend, ATR..."):
        tech = calculate_technical_indicators(dane)
        trend_info = get_trend_assessment(tech)
        sltp = calculate_sl_tp(
            tech=tech,
            trend_info=trend_info,
            sl_atr_mult=sl_atr_mult,
            tp1_atr_mult=tp1_atr_mult,
            tp2_atr_mult=tp2_atr_mult
        )

    with st.spinner("Uruchamianie symulacji Monte Carlo..."):
        try:
            mc = run_monte_carlo(
                close_prices=ceny_zamkniecia,
                liczba_symulacji=liczba_symulacji,
                dni_prognozy=dni_prognozy,
                target_mean_price=target_mean_price,
                seed=int(seed_input)
            )
        except Exception as e:
            st.error(f"❌ Błąd Monte Carlo: {e}")
            st.stop()

    bear = mc["bear"]
    hold = mc["hold"]
    bull = mc["bull"]

    final_bear = float(bear[-1])
    final_hold = float(hold[-1])
    final_bull = float(bull[-1])

    prob_above_current = mc["probability_above_current"]
    prob_above_target = mc["probability_above_target"]

    # -----------------------------------------------------
    # PODSUMOWANIE LICZBOWE
    # -----------------------------------------------------

    st.subheader("📌 Podsumowanie liczbowe")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Aktualna cena", fmt_money(ostatnia_cena, currency))

    col2.metric(
        "BEAR 10%",
        fmt_money(final_bear, currency),
        delta=f"{((final_bear / ostatnia_cena) - 1) * 100:.1f}%"
    )

    col3.metric(
        "HOLD 50%",
        fmt_money(final_hold, currency),
        delta=f"{((final_hold / ostatnia_cena) - 1) * 100:.1f}%"
    )

    col4.metric(
        "BULL 90%",
        fmt_money(final_bull, currency),
        delta=f"{((final_bull / ostatnia_cena) - 1) * 100:.1f}%"
    )

    col5, col6, col7, col8 = st.columns(4)

    col5.metric("Prawdopodobieństwo > obecna cena", fmt_pct(prob_above_current))
    col6.metric("Zmienność dzienna", fmt_pct(mc["sigma_hist"]))
    col7.metric("Target analityków", fundamentals.get("target_text", "Brak danych"))

    if prob_above_target is not None:
        col8.metric("Prawdopodobieństwo > target", fmt_pct(prob_above_target))
    else:
        col8.metric("Prawdopodobieństwo > target", "brak")

    # -----------------------------------------------------
    # TECHNIKA, SMI, NAC, SL/TP
    # -----------------------------------------------------

    st.subheader("🧭 Trend, SMI, NAC oraz SL/TP")

    t1, t2, t3, t4 = st.columns(4)

    t1.metric("Trend", str(trend_info["trend"]).upper(), delta=f"score {trend_info['trend_score']}")
    t2.metric("SMI", fmt_number(trend_info["smi"]), delta=f"signal {fmt_number(trend_info['smi_signal'])}")
    t3.metric("NAC mid", fmt_money(trend_info["nac_mid"], currency))
    t4.metric("ATR14", fmt_money(sltp.get("atr14"), currency))

    st.write("**Powody oceny trendu:**", ", ".join(trend_info.get("reasons", [])))
    st.write("**Pozycja względem NAC:**", trend_info.get("nac_position", "brak danych"))

    sltp_table = pd.DataFrame(
        {
            "Poziom": [
                "Kierunek",
                "Stop Loss",
                "Take Profit 1",
                "Take Profit 2",
                "Risk/Reward TP1",
                "Risk/Reward TP2",
                "Wsparcie 20 sesji",
                "Opór 20 sesji"
            ],
            "Wartość": [
                sltp.get("direction", "brak"),
                fmt_money(sltp.get("stop_loss"), currency),
                fmt_money(sltp.get("take_profit_1"), currency),
                fmt_money(sltp.get("take_profit_2"), currency),
                fmt_number(sltp.get("risk_reward_tp1")),
                fmt_number(sltp.get("risk_reward_tp2")),
                fmt_money(sltp.get("support20"), currency),
                fmt_money(sltp.get("resistance20"), currency)
            ]
        }
    )

    st.dataframe(sltp_table, use_container_width=True, hide_index=True)
    st.caption(sltp.get("comment", ""))

    # -----------------------------------------------------
    # FUNDAMENTY
    # -----------------------------------------------------

    st.subheader("🏦 Dane fundamentalne")

    fundamental_table = pd.DataFrame(
        {
            "Wskaźnik": [
                "Ticker",
                "Waluta",
                "Cena bieżąca",
                "EPS TTM",
                "P/E TTM",
                "Target mean price",
                "Liczba akcji",
                "Net Income TTM"
            ],
            "Wartość": [
                ticker,
                currency,
                fmt_money(ostatnia_cena, currency),
                fundamentals.get("eps_text", "Brak danych"),
                fundamentals.get("pe_text", "Brak danych"),
                fundamentals.get("target_text", "Brak danych"),
                f"{fundamentals['shares_outstanding']:,.0f}".replace(",", " ") if fundamentals.get("shares_outstanding") else "Brak danych",
                fmt_money(fundamentals["net_income_ttm"], currency) if fundamentals.get("net_income_ttm") else "Brak danych"
            ]
        }
    )

    st.dataframe(fundamental_table, use_container_width=True, hide_index=True)

    # -----------------------------------------------------
    # SCENARIUSZE MONTE CARLO
    # -----------------------------------------------------

    st.subheader("📊 Scenariusze Monte Carlo")

    scenario_table = pd.DataFrame(
        {
            "Scenariusz": ["BEAR 10%", "HOLD 50%", "BULL 90%"],
            "Cena końcowa": [
                fmt_money(final_bear, currency),
                fmt_money(final_hold, currency),
                fmt_money(final_bull, currency)
            ],
            "Zmiana vs obecna cena": [
                f"{((final_bear / ostatnia_cena) - 1) * 100:.2f}%",
                f"{((final_hold / ostatnia_cena) - 1) * 100:.2f}%",
                f"{((final_bull / ostatnia_cena) - 1) * 100:.2f}%"
            ]
        }
    )

    st.dataframe(scenario_table, use_container_width=True, hide_index=True)

    # -----------------------------------------------------
    # WYKRESY
    # -----------------------------------------------------

    st.subheader("📈 Wykres Monte Carlo")

    fig_mc = build_mc_chart(
        ticker=ticker,
        close_prices=ceny_zamkniecia,
        bear=bear,
        hold=hold,
        bull=bull,
        currency=currency
    )

    st.plotly_chart(fig_mc, use_container_width=True)

    st.subheader("📉 Wykres techniczny — SMA, NAC, SL/TP")

    fig_tech = build_technical_chart(
        ticker=ticker,
        tech=tech,
        sltp=sltp,
        currency=currency
    )

    st.plotly_chart(fig_tech, use_container_width=True)

    st.subheader("⚡ SMI — Stochastic Momentum Index")

    fig_smi = build_smi_chart(ticker, tech)
    st.plotly_chart(fig_smi, use_container_width=True)

    # -----------------------------------------------------
    # NEWSY
    # -----------------------------------------------------

    st.subheader("📰 News summary — Tavily")

    with st.spinner("Pobieranie newsów i katalizatorów z Tavily..."):
        newsy = fetch_news_tavily(ticker, company_query)

    with st.expander("Pokaż pobrane newsy"):
        st.text(newsy)

    # -----------------------------------------------------
    # DANE DLA AI
    # -----------------------------------------------------

    dane_rynkowe = {
        "ticker": ticker,
        "waluta": currency,
        "aktualna_cena": fmt_money(ostatnia_cena, currency),
        "horyzont_prognozy_dni_gieldowe": dni_prognozy,
        "liczba_symulacji_monte_carlo": liczba_symulacji,
        "seed_monte_carlo": int(seed_input),
        "monte_carlo": {
            "bear_10_percent": fmt_money(final_bear, currency),
            "hold_50_percent_mediana": fmt_money(final_hold, currency),
            "bull_90_percent": fmt_money(final_bull, currency),
            "probability_final_price_above_current": fmt_pct(prob_above_current),
            "probability_final_price_above_target": fmt_pct(prob_above_target) if prob_above_target is not None else "brak",
            "historyczna_srednia_dzienna_log_return": fmt_pct(mc["mu_hist"]),
            "oczekiwany_dzienny_log_return_modelu": fmt_pct(mc["expected_mu"]),
            "historyczna_zmiennosc_dzienna": fmt_pct(mc["sigma_hist"]),
        },
        "technika": {
            "trend": trend_info["trend"],
            "trend_score": trend_info["trend_score"],
            "trend_reasons": trend_info["reasons"],
            "sma50": fmt_money(trend_info["sma50"], currency),
            "sma200": fmt_money(trend_info["sma200"], currency),
            "ema20_slope_10d": fmt_pct(trend_info["ema20_slope_10d_pct"]),
            "smi": fmt_number(trend_info["smi"]),
            "smi_signal": fmt_number(trend_info["smi_signal"]),
            "nac_mid": fmt_money(trend_info["nac_mid"], currency),
            "nac_upper": fmt_money(trend_info["nac_upper"], currency),
            "nac_lower": fmt_money(trend_info["nac_lower"], currency),
            "nac_position": trend_info["nac_position"],
        },
        "sl_tp": {
            "direction": sltp.get("direction"),
            "stop_loss": fmt_money(sltp.get("stop_loss"), currency),
            "take_profit_1": fmt_money(sltp.get("take_profit_1"), currency),
            "take_profit_2": fmt_money(sltp.get("take_profit_2"), currency),
            "risk_reward_tp1": fmt_number(sltp.get("risk_reward_tp1")),
            "risk_reward_tp2": fmt_number(sltp.get("risk_reward_tp2")),
            "support20": fmt_money(sltp.get("support20"), currency),
            "resistance20": fmt_money(sltp.get("resistance20"), currency),
            "atr14": fmt_money(sltp.get("atr14"), currency),
        },
        "fundamenty": {
            "eps_ttm": fundamentals.get("eps_text"),
            "pe_ttm": fundamentals.get("pe_text"),
            "target_mean_price": fundamentals.get("target_text"),
            "shares_outstanding": fundamentals.get("shares_outstanding"),
            "net_income_ttm": fundamentals.get("net_income_ttm"),
        },
        "newsy_tavily": newsy,
    }

    # -----------------------------------------------------
    # RAPORT AI
    # -----------------------------------------------------

    st.subheader("🔬 Profesjonalna analiza fundamentalno-sentymentowa AI")

    with st.spinner("Generowanie raportu AI..."):
        raport = generate_ai_report(dane_rynkowe)

    st.markdown(raport)

    st.caption(
        "Uwaga: model Monte Carlo i poziomy SL/TP są narzędziami statystyczno-technicznymi. "
        "Nie przewidują przyszłości i nie stanowią rekomendacji inwestycyjnej."
    )
