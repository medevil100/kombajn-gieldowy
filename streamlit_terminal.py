# tests/test_app.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os
import streamlit as st
st.title("TEST — aplikacja działa")
st.write("Jeśli to widzisz, UI działa poprawnie.")


# upewnij się, że katalog projektu jest w sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__)) if os.path.basename(os.getcwd()) == 'tests' else os.getcwd()
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_parse_portfolio_basic():
    text = "AAPL, 10, 150\nTSLA,2, 700\nBADLINE\nGOOG,5, 1200"
    parsed = parse_portfolio(text)
    assert "AAPL" in parsed
    assert parsed["AAPL"]["qty"] == 10.0
    assert parsed["TSLA"]["buy"] == 700.0
    assert "BADLINE" not in parsed
    assert parsed["GOOG"]["qty"] == 5.0

def make_sample_ohlcv(days=120, start_price=50.0, seed=42):
    np.random.seed(seed)
    dates = pd.date_range(end=pd.Timestamp.today(), periods=days, freq='D')
    # generuj stabilny trend z losowym szumem
    trend = np.linspace(start_price*0.95, start_price*1.05, days)
    noise = np.random.normal(0, 0.5, days)
    prices = trend + noise
    high = prices + np.abs(np.random.normal(0.5, 0.5, days))
    low = prices - np.abs(np.random.normal(0.5, 0.5, days))
    openp = prices + np.random.normal(0, 0.3, days)
    close = prices
    volume = np.random.randint(1000, 5000, days)
    df = pd.DataFrame({"Open": openp, "High": high, "Low": low, "Close": close, "Volume": volume}, index=dates)
    return df

def test_backtest_advanced_runs_and_returns_metrics():
    df = make_sample_ohlcv(days=180, start_price=50.0)
    # ensure indicators exist
    df = add_indicators_full(df)
    res = backtest_advanced(df, initial_capital=10000.0,
                            use_atr_positioning=True, risk_per_trade_pct=1.0,
                            atr_multiplier=2.0, tp_multiplier=2.0,
                            min_lot=1, max_position_cap=5000.0,
                            fee_per_trade=0.0, slippage_pct=0.1,
                            max_concurrent_positions=3)
    assert isinstance(res, dict)
    assert "trades" in res
    assert "equity" in res
    assert hasattr(res["equity"], "values")
    assert isinstance(res["metrics"], dict)
    # metrics keys
    for k in ["total_return", "num_trades", "max_drawdown"]:
        assert k in res["metrics"]
