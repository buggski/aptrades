"""Pure strategy logic: no network calls, so it can be tested and backtested.

These are popular, well-documented rule sets, NOT proven money-makers.
Run backtest.py before trusting any of them.
"""
import math

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Stocks: Opening Range Breakout (ORB) with a VWAP filter
# ---------------------------------------------------------------------------
def vwap(bars: pd.DataFrame) -> pd.Series:
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3
    vol = bars["volume"].replace(0, np.nan)
    return (typical * vol).cumsum() / vol.cumsum()


def orb_signal(day_bars: pd.DataFrame, or_bars: int = 3, reward_risk: float = 2.0):
    """day_bars: today's COMPLETED 5-min bars starting 9:30 ET, oldest first.

    Long-only. Fires only on the first bar that closes above the opening-range high
    while also above VWAP (no chasing a breakout that already happened).
    Returns {"entry", "stop", "target"} or None.
    """
    if len(day_bars) <= or_bars:
        return None
    opening = day_bars.iloc[:or_bars]
    hi, lo = float(opening["high"].max()), float(opening["low"].min())
    after = day_bars.iloc[or_bars:]
    if (after["close"].iloc[:-1] > hi).any():
        return None  # breakout already happened on an earlier bar
    last_close = float(after["close"].iloc[-1])
    if last_close > hi and last_close > float(vwap(day_bars).iloc[-1]):
        risk = last_close - lo
        if risk <= 0:
            return None
        return {"entry": last_close, "stop": lo, "target": last_close + reward_risk * risk}
    return None


# ---------------------------------------------------------------------------
# Crypto: EMA trend following (long-only)
# ---------------------------------------------------------------------------
def ema_state(closes: pd.Series, fast=9, slow=21, trend=200) -> pd.Series:
    """True on bars where the bot wants to be long: fast EMA above slow EMA and price
    above the long trend EMA. State-based, so a missed run doesn't miss the signal."""
    f = closes.ewm(span=fast, adjust=False).mean()
    s = closes.ewm(span=slow, adjust=False).mean()
    t = closes.ewm(span=trend, adjust=False).mean()
    state = (f > s) & (closes > t)
    state.iloc[: trend] = False  # not enough history yet
    return state


def ema_signal(closes: pd.Series, fast=9, slow=21, trend=200) -> str:
    """'long' = want a position, 'flat' = want none."""
    if len(closes) < trend + 1:
        return "flat"
    return "long" if bool(ema_state(closes, fast, slow, trend).iloc[-1]) else "flat"


# ---------------------------------------------------------------------------
# Kalshi BTC 15-min: is the contract mispriced vs. a simple volatility model?
# ---------------------------------------------------------------------------
def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def kalshi_fee(price: float, count: int = 1) -> float:
    """Approximate Kalshi taker fee: 0.07 * C * P * (1-P), rounded up to the cent."""
    return math.ceil(0.07 * count * price * (1 - price) * 100 - 1e-9) / 100


def prob_up(spot: float, strike: float, sigma_per_min: float, minutes_left: float) -> float:
    """Chance BTC finishes at/above strike, assuming a driftless random walk."""
    if minutes_left <= 0 or sigma_per_min <= 0:
        return 1.0 if spot >= strike else 0.0
    z = math.log(spot / strike) / (sigma_per_min * math.sqrt(minutes_left))
    return norm_cdf(z)


def sigma_from_closes(closes: pd.Series) -> float:
    """Std-dev of 1-minute log returns."""
    r = np.log(closes.astype(float)).diff().dropna()
    return float(r.std()) if len(r) > 10 else 0.0


def kalshi_decision(p_up: float, yes_ask: float, no_ask: float, min_edge: float = 0.05):
    """Returns ("yes"|"no", price, edge) or None. Prices in dollars (0.01-0.99)."""
    best = None
    for side, p_win, ask in (("yes", p_up, yes_ask), ("no", 1 - p_up, no_ask)):
        if ask is None or not (0.01 <= ask <= 0.99):
            continue
        edge = p_win - ask - kalshi_fee(ask)
        if edge >= min_edge and (best is None or edge > best[2]):
            best = (side, ask, edge)
    return best
