"""Stocks + crypto on Alpaca (paper account)."""
import datetime as dt
import math
from zoneinfo import ZoneInfo

import pandas as pd
from alpaca.common.exceptions import APIError
from alpaca.data.enums import DataFeed
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

import config
import strategies
from notify import alert, log

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def _completed(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Drop the still-forming bar so signals only use finished bars."""
    now = dt.datetime.now(UTC)
    ts = df.index.get_level_values("timestamp") if isinstance(df.index, pd.MultiIndex) else df.index
    return df[(ts + pd.Timedelta(minutes=minutes)) <= now]


class AlpacaBot:
    def __init__(self):
        if not (config.ALPACA_KEY and config.ALPACA_SECRET):
            raise RuntimeError("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY secrets")
        self.trading = TradingClient(config.ALPACA_KEY, config.ALPACA_SECRET, paper=config.ALPACA_PAPER)
        self.stock_data = StockHistoricalDataClient(config.ALPACA_KEY, config.ALPACA_SECRET)
        self.crypto_data = CryptoHistoricalDataClient(config.ALPACA_KEY, config.ALPACA_SECRET)
        self.account = self.trading.get_account()
        self.equity = float(self.account.equity)
        last = float(self.account.last_equity) or self.equity
        self.day_pnl_pct = (self.equity - last) / last
        self.halted = self.day_pnl_pct <= -config.DAILY_LOSS_LIMIT_PCT
        log(f"[alpaca] equity ${self.equity:,.2f}  today {self.day_pnl_pct:+.2%}"
            + ("  -> DAILY LOSS LIMIT HIT, no new trades" if self.halted else ""))

    # ---------------------------------------------------------------- helpers
    def _position(self, symbol: str):
        try:
            return self.trading.get_open_position(symbol.replace("/", ""))
        except APIError:
            return None

    def _orders_today(self, symbol: str, since: dt.datetime):
        req = GetOrdersRequest(status=QueryOrderStatus.ALL, after=since, symbols=[symbol], limit=50)
        return self.trading.get_orders(filter=req)

    # ----------------------------------------------------------------- stocks
    def run_stocks(self):
        clock = self.trading.get_clock()
        if not clock.is_open:
            log("[stocks] market closed")
            return
        now = dt.datetime.now(UTC)
        minutes_to_close = (clock.next_close - now).total_seconds() / 60
        today_open = dt.datetime.now(ET).replace(hour=9, minute=30, second=0, microsecond=0)

        if minutes_to_close <= config.FLATTEN_MINUTES_BEFORE_CLOSE:
            for sym in config.STOCK_SYMBOLS:
                for o in self._orders_today(sym, today_open):
                    if o.status.value in ("new", "accepted", "held", "partially_filled", "pending_new"):
                        self.trading.cancel_order_by_id(o.id)
                if self._position(sym):
                    self.trading.close_position(sym)
                    alert(f"[stocks] {sym}: flattened before close")
            return

        if self.halted:
            return

        bars = self.stock_data.get_stock_bars(StockBarsRequest(
            symbol_or_symbols=config.STOCK_SYMBOLS,
            timeframe=TimeFrame(5, TimeFrameUnit.Minute),
            start=today_open.astimezone(UTC),
            feed=DataFeed.IEX,
        )).df
        if bars.empty:
            log("[stocks] no bars yet")
            return
        bars = _completed(bars, 5)

        for sym in config.STOCK_SYMBOLS:
            if sym not in bars.index.get_level_values("symbol"):
                continue
            if self._position(sym) or self._orders_today(sym, today_open):
                log(f"[stocks] {sym}: already traded today")
                continue  # one ORB trade per symbol per day
            sig = strategies.orb_signal(bars.loc[sym], config.ORB_BARS, config.ORB_REWARD_RISK)
            if not sig:
                log(f"[stocks] {sym}: no breakout")
                continue
            risk_per_share = sig["entry"] - sig["stop"]
            qty = min(
                math.floor(self.equity * config.RISK_PER_TRADE_PCT / risk_per_share),
                math.floor(self.equity * config.MAX_POSITION_PCT / sig["entry"]),
            )
            if qty < 1:
                continue
            self.trading.submit_order(MarketOrderRequest(
                symbol=sym, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=round(sig["target"], 2)),
                stop_loss=StopLossRequest(stop_price=round(sig["stop"], 2)),
            ))
            alert(f"[stocks] BUY {qty} {sym} ~${sig['entry']:.2f}  stop ${sig['stop']:.2f}  "
                  f"target ${sig['target']:.2f} (paper)")

    # ----------------------------------------------------------------- crypto
    def run_crypto(self):
        start = dt.datetime.now(UTC) - dt.timedelta(days=4)
        bars = self.crypto_data.get_crypto_bars(CryptoBarsRequest(
            symbol_or_symbols=config.CRYPTO_SYMBOLS,
            timeframe=TimeFrame(15, TimeFrameUnit.Minute),
            start=start,
        )).df
        bars = _completed(bars, 15)

        for sym in config.CRYPTO_SYMBOLS:
            if sym not in bars.index.get_level_values("symbol"):
                continue
            closes = bars.loc[sym]["close"]
            want = strategies.ema_signal(closes, config.EMA_FAST, config.EMA_SLOW, config.EMA_TREND)
            pos = self._position(sym)
            if want == "flat" and pos:
                self.trading.close_position(sym.replace("/", ""))
                alert(f"[crypto] SELL all {sym} @ ~${closes.iloc[-1]:,.2f}  "
                      f"(unrealized was ${float(pos.unrealized_pl):+,.2f}) (paper)")
            elif want == "long" and not pos and not self.halted:
                notional = round(self.equity * config.MAX_POSITION_PCT, 2)
                self.trading.submit_order(MarketOrderRequest(
                    symbol=sym, notional=notional, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
                ))
                alert(f"[crypto] BUY ${notional:,.2f} of {sym} @ ~${closes.iloc[-1]:,.2f} (paper)")
            else:
                log(f"[crypto] {sym}: signal={want}, holding={'yes' if pos else 'no'}")
