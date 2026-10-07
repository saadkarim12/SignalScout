"""Pick the top-N USDT spot coins by 24h volume."""
import re

LEVERAGED = re.compile(r"(UP|DOWN|BULL|BEAR)$")


def pick_universe(tickers: dict, markets: dict, cfg: dict) -> list[str]:
    skip = set(cfg["stablecoins"]) | set(cfg["wrapped_or_dupes"])
    rows = []
    for sym, t in tickers.items():
        m = markets.get(sym)
        if not m or not m.get("spot") or m.get("quote") != "USDT" or not m.get("active", True):
            continue
        base = m["base"]
        if base in skip or LEVERAGED.search(base):
            continue
        vol = t.get("quoteVolume") or 0
        if vol < cfg.get("min_quote_volume_usd", 0) and sym != "BTC/USDT":
            continue
        rows.append((vol, sym))
    top = [s for _, s in sorted(rows, reverse=True)]
    top = [s for s in top if s != "BTC/USDT"][: cfg["universe_size"] - 1]
    return ["BTC/USDT"] + top
