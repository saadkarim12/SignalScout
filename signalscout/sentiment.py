import requests


def fear_greed() -> tuple[int, str] | None:
    """Current Fear & Greed (0-100). Returns None if unavailable (never guess)."""
    try:
        d = requests.get("https://api.alternative.me/fng/", timeout=10).json()["data"][0]
        return int(d["value"]), d["value_classification"]
    except Exception:
        return None


def fear_greed_history() -> dict:
    """Whole history {date 'YYYY-MM-DD': value}. Empty dict if unavailable."""
    from datetime import datetime, timezone
    try:
        d = requests.get("https://api.alternative.me/fng/?limit=0", timeout=30).json()["data"]
        return {datetime.fromtimestamp(int(x["timestamp"]), timezone.utc).strftime("%Y-%m-%d"): int(x["value"]) for x in d}
    except Exception:
        return {}
