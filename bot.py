"""One pass of the bot. GitHub Actions runs this every 5 minutes."""
import sys
import traceback

import config
from notify import alert


def main():
    failed = False

    if config.ENABLE_STOCKS or config.ENABLE_CRYPTO:
        try:
            from alpaca_trader import AlpacaBot
            bot = AlpacaBot()
            if config.ENABLE_STOCKS:
                bot.run_stocks()
            if config.ENABLE_CRYPTO:
                bot.run_crypto()
        except Exception:
            failed = True
            alert("[alpaca] ERROR\n" + traceback.format_exc()[-1500:])

    if config.ENABLE_KALSHI:
        try:
            from kalshi_trader import run_kalshi
            run_kalshi()
        except Exception:
            failed = True
            alert("[kalshi] ERROR\n" + traceback.format_exc()[-1500:])

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
