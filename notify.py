import requests

import config


def log(msg: str):
    """Goes to the GitHub Actions run log only."""
    print(msg, flush=True)


def alert(msg: str):
    """Trades and errors: run log + Discord (if a webhook is set)."""
    log(msg)
    if config.DISCORD_WEBHOOK_URL:
        try:
            requests.post(config.DISCORD_WEBHOOK_URL, json={"content": msg[:1900]}, timeout=10)
        except Exception as e:  # alerts must never break trading
            print(f"(discord alert failed: {e})")
