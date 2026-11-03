"""Kalshi BTC 15-minute up/down markets (DEMO environment, fake money)."""
import base64
import datetime as dt
import math
import time
import uuid
from urllib.parse import urlparse

import pandas as pd
import requests
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import config
import strategies
from notify import alert, log

UTC = dt.timezone.utc


class KalshiClient:
    def __init__(self, base_url=config.KALSHI_BASE_URL):
        if not (config.KALSHI_KEY_ID and config.KALSHI_PRIVATE_KEY):
            raise RuntimeError("Missing KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY secrets")
        self.base = base_url
        self.key_id = config.KALSHI_KEY_ID
        self.key = serialization.load_pem_private_key(config.KALSHI_PRIVATE_KEY.encode(), password=None)

    def _sign(self, ts: str, method: str, path: str) -> str:
        msg = f"{ts}{method}{path.split('?')[0]}".encode()
        if isinstance(self.key, Ed25519PrivateKey):
            sig = self.key.sign(msg)
        else:  # RSA key
            sig = self.key.sign(
                msg,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                hashes.SHA256(),
            )
        return base64.b64encode(sig).decode()

    def request(self, method: str, path: str, params=None, json=None):
        url = self.base + path
        ts = str(int(time.time() * 1000))
        headers = {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": self._sign(ts, method, urlparse(url).path),
        }
        r = requests.request(method, url, headers=headers, params=params, json=json, timeout=15)
        if r.status_code >= 400:
            raise RuntimeError(f"Kalshi {method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()


def _dollars(market: dict, field: str):
    """Kalshi has moved from cent integers to dollar strings; accept either."""
    v = market.get(f"{field}_dollars")
    if v not in (None, ""):
        return float(v)
    v = market.get(field)
    return float(v) / 100 if v not in (None, "") else None


def _btc_closes(minutes=120) -> pd.Series:
    client = CryptoHistoricalDataClient(config.ALPACA_KEY or None, config.ALPACA_SECRET or None)
    bars = client.get_crypto_bars(CryptoBarsRequest(
        symbol_or_symbols="BTC/USD", timeframe=TimeFrame.Minute,
        start=dt.datetime.now(UTC) - dt.timedelta(minutes=minutes),
    )).df
    return bars.loc["BTC/USD"]["close"]


def run_kalshi():
    k = KalshiClient()
    markets = k.request("GET", "/markets", params={"series_ticker": config.KALSHI_SERIES,
                                                    "status": "open", "limit": 20})["markets"]
    if not markets:
        log("[kalshi] no open BTC 15-min market")
        return
    now = dt.datetime.now(UTC)
    for m in markets:
        m["_close"] = dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
    m = min(markets, key=lambda x: x["_close"])
    minutes_left = (m["_close"] - now).total_seconds() / 60
    ticker = m["ticker"]

    if not (config.KALSHI_MIN_MINUTES_LEFT <= minutes_left <= config.KALSHI_MAX_MINUTES_LEFT):
        log(f"[kalshi] {ticker}: {minutes_left:.1f} min left, waiting for the trade window")
        return

    strike = m.get("floor_strike")
    if strike in (None, ""):
        log(f"[kalshi] {ticker}: no strike in market data, skipping")
        return
    strike = float(strike)

    # Don't stack bets: skip if we already hold or have an order resting in this window
    pos = k.request("GET", "/portfolio/positions", params={"ticker": ticker})
    held = [p for p in pos.get("market_positions", []) if p.get("ticker") == ticker
            and float(p.get("position_fp", p.get("position", 0)) or 0) != 0]
    resting = k.request("GET", "/portfolio/orders", params={"ticker": ticker, "status": "resting"})
    if held or resting.get("orders"):
        log(f"[kalshi] {ticker}: already in this window")
        return

    closes = _btc_closes()
    spot = float(closes.iloc[-1])
    sigma = strategies.sigma_from_closes(closes)
    p_up = strategies.prob_up(spot, strike, sigma, minutes_left)
    yes_ask, no_ask = _dollars(m, "yes_ask"), _dollars(m, "no_ask")
    log(f"[kalshi] {ticker}: BTC ${spot:,.2f} vs strike ${strike:,.2f}, {minutes_left:.1f} min left, "
        f"model P(up)={p_up:.2f}, YES ask={yes_ask}, NO ask={no_ask}")

    decision = strategies.kalshi_decision(p_up, yes_ask, no_ask, config.KALSHI_MIN_EDGE)
    if not decision:
        log(f"[kalshi] {ticker}: no edge, no trade")
        return
    side, price, edge = decision
    count = math.floor(config.KALSHI_MAX_DOLLARS / (price + strategies.kalshi_fee(price)))
    if count < 1:
        return

    # Kalshi's order API is quoted on the YES leg: buying YES = "bid" at the YES price;
    # buying NO = selling YES ("ask") at 1 - NO price.
    yes_leg_price = price if side == "yes" else 1 - price
    order = {
        "ticker": ticker,
        "side": "bid" if side == "yes" else "ask",
        "count": str(count),
        "price": f"{yes_leg_price:.4f}",
        "time_in_force": "good_till_canceled",
        "self_trade_prevention_type": "taker_at_cross",
        "client_order_id": str(uuid.uuid4()),
    }
    k.request("POST", "/portfolio/events/orders", json=order)
    alert(f"[kalshi] BUY {count} {side.upper()} on {ticker} @ ${price:.2f}  "
          f"model edge {edge:+.2f} (DEMO)")
