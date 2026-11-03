"""Test the stock and crypto strategies on past data before trusting them.

Run from GitHub: Actions tab -> "Backtest" -> Run workflow, then open the log.
Costs assumed: 0.05% slippage per side for stocks, 0.25% per side for crypto
(roughly Alpaca's crypto taker fee). Results include those costs.
"""
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

import config
import strategies

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
STOCK_COST = 0.0005
CRYPTO_COST = 0.0025


def summarize(name, trade_returns, buy_hold):
    tr = np.array(trade_returns)
    print(f"\n=== {name} ===")
    if len(tr) == 0:
        print("no trades")
        return
    equity = np.cumprod(1 + tr * config.MAX_POSITION_PCT)
    peak = np.maximum.accumulate(equity)
    print(f"trades: {len(tr)}   win rate: {(tr > 0).mean():.0%}   avg trade: {tr.mean():+.3%}")
    print(f"account return (using {config.MAX_POSITION_PCT:.0%} of equity per trade): {equity[-1] - 1:+.2%}")
    print(f"worst drawdown: {(equity / peak - 1).min():.2%}")
    print(f"buy-and-hold over same period: {buy_hold:+.2%}")
    print("VERDICT:", "beat buy-and-hold" if equity[-1] - 1 > buy_hold * config.MAX_POSITION_PCT
          else "did NOT beat simply holding")


def backtest_orb(days=120):
    client = StockHistoricalDataClient(config.ALPACA_KEY, config.ALPACA_SECRET)
    end = dt.datetime.now(UTC) - dt.timedelta(minutes=20)
    df = client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=config.STOCK_SYMBOLS, timeframe=TimeFrame(5, TimeFrameUnit.Minute),
        start=end - dt.timedelta(days=days), end=end, feed=DataFeed.IEX,
    )).df
    for sym in config.STOCK_SYMBOLS:
        bars = df.loc[sym].copy()
        bars.index = bars.index.tz_convert(ET)
        bars = bars.between_time("09:30", "15:55")
        results = []
        for _, day in bars.groupby(bars.index.date):
            results += simulate_orb_day(day)
        bh = bars["close"].iloc[-1] / bars["close"].iloc[0] - 1
        summarize(f"Stocks ORB {sym} ({days} days)", results, bh)


def simulate_orb_day(day: pd.DataFrame):
    """Signal on a bar close, enter next bar's open, exit at stop/target/close."""
    for i in range(config.ORB_BARS + 1, len(day) - 1):
        sig = strategies.orb_signal(day.iloc[: i], config.ORB_BARS, config.ORB_REWARD_RISK)
        if not sig:
            continue
        entry = day["open"].iloc[i] * (1 + STOCK_COST)
        stop, target = sig["stop"], entry + config.ORB_REWARD_RISK * (entry - sig["stop"])
        if entry <= stop:
            return []
        exit_px = day["close"].iloc[-1]
        for _, b in day.iloc[i:].iterrows():
            if b["low"] <= stop:      # assume the stop hits first if both touch
                exit_px = stop
                break
            if b["high"] >= target:
                exit_px = target
                break
        return [exit_px * (1 - STOCK_COST) / entry - 1]
    return []


def backtest_ema(days=120):
    client = CryptoHistoricalDataClient(config.ALPACA_KEY or None, config.ALPACA_SECRET or None)
    df = client.get_crypto_bars(CryptoBarsRequest(
        symbol_or_symbols=config.CRYPTO_SYMBOLS, timeframe=TimeFrame(15, TimeFrameUnit.Minute),
        start=dt.datetime.now(UTC) - dt.timedelta(days=days),
    )).df
    for sym in config.CRYPTO_SYMBOLS:
        closes = df.loc[sym]["close"]
        summarize(f"Crypto EMA {sym} ({days} days)", simulate_ema(closes),
                  closes.iloc[-1] / closes.iloc[0] - 1)


def simulate_ema(closes: pd.Series):
    """Enter/exit at the close of the bar after the signal changes."""
    state = strategies.ema_state(closes, config.EMA_FAST, config.EMA_SLOW, config.EMA_TREND).values
    trades, entry = [], None
    for i in range(1, len(closes)):
        px = closes.iloc[i]
        if state[i - 1] and entry is None:
            entry = px * (1 + CRYPTO_COST)
        elif not state[i - 1] and entry is not None:
            trades.append(px * (1 - CRYPTO_COST) / entry - 1)
            entry = None
    return trades


if __name__ == "__main__":
    print("Backtests use past data. Doing well here does not mean it will work going forward.")
    if config.ENABLE_STOCKS:
        backtest_orb()
    if config.ENABLE_CRYPTO:
        backtest_ema()
    if config.ENABLE_KALSHI:
        print("\n(Kalshi isn't backtested here: it needs historical order-book prices. "
              "Judge it from the demo results it logs over a few weeks.)")
