"""All settings in one place. Change values here or override with environment variables
(GitHub repo -> Settings -> Secrets and variables -> Actions -> Variables)."""
import os


def _f(name, default):
    return float(os.getenv(name, default))


def _b(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ---- What to run -----------------------------------------------------------
ENABLE_STOCKS = _b("ENABLE_STOCKS", True)
ENABLE_CRYPTO = _b("ENABLE_CRYPTO", True)
ENABLE_KALSHI = _b("ENABLE_KALSHI", True)

# ---- Account-wide risk limits (Alpaca) -------------------------------------
MAX_POSITION_PCT = _f("MAX_POSITION_PCT", 0.20)   # max 20% of equity in any one position
RISK_PER_TRADE_PCT = _f("RISK_PER_TRADE_PCT", 0.005)  # lose at most 0.5% of equity if a stock stop hits
DAILY_LOSS_LIMIT_PCT = _f("DAILY_LOSS_LIMIT_PCT", 0.03)  # stop opening trades after -3% on the day

# ---- Stocks: Opening Range Breakout ----------------------------------------
STOCK_SYMBOLS = os.getenv("STOCK_SYMBOLS", "SPY,QQQ").split(",")
ORB_BARS = int(os.getenv("ORB_BARS", 3))          # 3 x 5-min bars = first 15 minutes
ORB_REWARD_RISK = _f("ORB_REWARD_RISK", 2.0)      # take profit at 2x the risk
FLATTEN_MINUTES_BEFORE_CLOSE = int(os.getenv("FLATTEN_MINUTES_BEFORE_CLOSE", 15))

# ---- Crypto: EMA trend ------------------------------------------------------
CRYPTO_SYMBOLS = os.getenv("CRYPTO_SYMBOLS", "BTC/USD,ETH/USD").split(",")
EMA_FAST = int(os.getenv("EMA_FAST", 9))
EMA_SLOW = int(os.getenv("EMA_SLOW", 21))
EMA_TREND = int(os.getenv("EMA_TREND", 200))      # on 15-min bars ~ 50 hours

# ---- Kalshi: BTC 15-minute up/down -----------------------------------------
KALSHI_SERIES = os.getenv("KALSHI_SERIES", "KXBTC15M")
KALSHI_MIN_EDGE = _f("KALSHI_MIN_EDGE", 0.05)     # need model prob >= price + fee + 5 cents
KALSHI_MAX_DOLLARS = _f("KALSHI_MAX_DOLLARS", 5)  # max spent per window
KALSHI_MIN_MINUTES_LEFT = _f("KALSHI_MIN_MINUTES_LEFT", 1)
KALSHI_MAX_MINUTES_LEFT = _f("KALSHI_MAX_MINUTES_LEFT", 6)

# ---- Paper / demo only -------------------------------------------------------
# Deliberately hard-coded. Switching to real money is a code change, not a setting,
# so it can't happen by accident.
ALPACA_PAPER = True
KALSHI_BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"

# ---- Credentials (GitHub Secrets) -----------------------------------------
ALPACA_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY", "")
KALSHI_KEY_ID = os.getenv("KALSHI_API_KEY_ID", "")
KALSHI_PRIVATE_KEY = os.getenv("KALSHI_PRIVATE_KEY", "")  # full PEM text
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")  # optional trade alerts
