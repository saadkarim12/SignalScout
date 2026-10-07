def position_size(account: float, risk_pct: float, entry: float, stop: float, cap_pct: float = 25) -> dict:
    """Size so that hitting the stop loses risk_pct of the account (capped)."""
    stop_dist = (entry - stop) / entry
    usd = account * risk_pct / 100 / stop_dist
    usd = min(usd, account * cap_pct / 100)
    return {"usd": usd, "coins": usd / entry, "max_loss": usd * stop_dist}
