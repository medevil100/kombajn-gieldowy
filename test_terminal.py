# test_terminal.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app import parse_portfolio, backtest_simple_strategy, add_indicators_full

def test_parse_portfolio_basic():
    text = "AAPL, 10, 150\nTSLA,2, 700\nBADLINE\nGOOG,5, 1200"
    parsed = parse_portfolio(text)
    assert "AAPL" in parsed
    assert parsed["AAPL"]["qty"] == 10.0
    assert parsed["TSLA"]["buy"] == 700.0
    assert "BADLINE" not in parsed
    assert parsed["GOOG"]["qty"] == 5.0

def make_sample_ohlcv(days=60, start_price=100.0):
    dates = pd.date_range(end=pd.Timestamp.today(), periods=days, freq='D')
    prices = np.linspace(start_price*0.9, start_price*1.1, days) + np.random.normal(0, 1, days)
    high = prices + np.random.uniform(0.5, 2.0, days)
    low = prices - np.random.uniform(0.5, 2.0, days)
    openp = prices + np.random.normal(0, 0.5, days)
    close = prices
    volume = np.random.randint(1000, 5000, days)
    df = pd.DataFrame({"Open": openp, "High": high, "Low": low, "Close": close, "Volume": volume}, index=dates)
    return df

def test_backtest_simple_strategy_runs_and_returns_metrics():
    df = make_sample_ohlcv(days=120, start_price=50.0)
    # ensure indicators exist by adding them
    df = add_indicators_full(df)
    # run backtest with ATR sizing enabled
    res = backtest_simple_strategy(df, initial_capital=10000, use_atr_positioning=True, risk_per_trade_pct=1.0, atr_multiplier=2.0)
    assert isinstance(res, dict)
    assert "trades" in res
    assert "equity" in res
    # equity should be a pandas Series (possibly empty)
    assert hasattr(res["equity"], "values")
    # total_return numeric
    assert isinstance(res["total_return"], float)
