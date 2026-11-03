# Day-trade bot (paper money only)

Runs every 5 minutes on GitHub's servers, so you don't need a computer on. Everything here
is **fake money**: Alpaca paper trading and Kalshi's demo site. Going live is a deliberate
code change in `config.py`, not a switch.

## What it does

| Market | Strategy | Exits |
|---|---|---|
| Stocks (SPY, QQQ) | **Opening Range Breakout**: after the first 15 min, buy if price closes above that range's high and above VWAP. One trade per symbol per day. | Stop at the range low, take profit at 2x the risk, everything sold 15 min before close |
| Crypto (BTC, ETH) | **EMA trend**: hold while 9-EMA > 21-EMA and price > 200-EMA on 15-min bars | Sells when the trend condition breaks |
| Kalshi BTC 15-min | **Mispricing check**: estimates P(BTC finishes up) from recent volatility; buys YES or NO only if the price is 5¢+ cheaper than the model after fees, in the last 1–6 minutes | Held to settlement, max $5 per window |

Safety: max 20% of the account in one position, 0.5% risk per stock trade, no new trades
after a -3% day.

These are popular strategies, **not proven winners**. Use the Backtest workflow and a few
weeks of paper results to see whether any of them actually make money.

## Setup (all doable from a phone browser)

1. **Alpaca paper keys** — sign up at alpaca.markets → Paper Trading → API Keys → Generate.
2. **Kalshi demo keys** (optional) — make an account at demo.kalshi.co → Account & security →
   API Keys → Create Key. Save the Key ID and the downloaded private key file's text.
3. **GitHub repo** — create a new **public** repo (public repos get unlimited free
   Actions minutes; your keys stay private in Secrets) and add these files.
4. **Secrets** — repo → Settings → Secrets and variables → Actions → New repository secret:
   - `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`
   - `KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY` (paste the whole key, including the BEGIN/END lines)
   - `DISCORD_WEBHOOK_URL` (optional, for trade alerts)
5. **Turn parts off** (optional) — same page, **Variables** tab: set `ENABLE_KALSHI` to `false`, etc.
6. **Test it** — Actions tab → *Backtest* → Run workflow. Then *Trading bot (paper)* → Run workflow
   and open the log to check it connected.

After that it runs on its own every 5 minutes. GitHub pauses scheduled workflows after 60
days with no commits to the repo; any small edit wakes it back up.

## Notes

- Free Alpaca data uses the IEX feed, which is a slice of total volume — fine for testing.
- The Kalshi part follows Kalshi's current order API docs but hasn't been run against the
  live demo yet; check the first runs' logs. Its BTC price comes from Alpaca, while Kalshi
  settles on the CF Benchmarks index, so they can differ by a few dollars.
- Change any setting in `config.py`.
