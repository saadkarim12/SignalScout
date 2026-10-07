"""Buy-or-wait suggestion for a signal, in plain English.

Rules (fixed in advance, written down here so nobody can bend them later):
BUY needs ALL of these. Otherwise WAIT, and we say exactly what is missing.
1. The signal is STRONG or WATCH.
2. A bounce candle has appeared (a green candle closing near its high on higher-than-normal volume).
3. The live price has not run away: still within 1% of the signal's buy price.
4. Reward vs risk at the LIVE price is still at least 2.
5. Market mode is IN (Bitcoin above its 200-day average).
"""
MAX_DRIFT = 0.01


def suggest(r, live=None, mode=None, min_rr=2.0) -> dict:
    bad, good = [], []
    if r.verdict not in ("STRONG", "WATCH"):
        return dict(label="SKIP", bad=["This coin is not a STRONG or WATCH signal."], good=[])
    b = next((c for c in r.checks if c.name == "bounce"), None)
    if b and b.passed:
        good.append("A bounce candle has appeared: buyers are stepping in.")
    else:
        bad.append("No bounce yet. Wait for a green candle that closes near its high on higher-than-normal volume. "
                   "That is the sign buyers are returning.")
    if live is not None and live > 0:
        drift = live / r.entry - 1
        if abs(drift) > MAX_DRIFT:
            bad.append(f"The price has moved {drift * 100:+.1f}% since the signal. The setup has changed.")
        else:
            good.append("The price is still close to the signal's buy price.")
        rr = (r.target - live) / (live - r.stop) if live > r.stop else -1.0
        if rr < min_rr - 1e-9:
            bad.append(f"At the live price the reward vs risk is only {rr:.1f} (needs {min_rr:.0f}+).")
        else:
            good.append(f"Reward vs risk at the live price is still {rr:.1f}.")
    if mode and mode.get("mode") == "OUT":
        bad.append("Market mode is OUT (Bitcoin's big trend is down). Extra careful.")
    elif mode:
        good.append("Market mode is IN (Bitcoin's big trend is up).")
    return dict(label="BUY" if not bad else "WAIT", bad=bad, good=good)


def one_line(s: dict) -> str:
    if s["label"] == "BUY":
        return "All conditions met."
    if not s["bad"]:
        return ""
    first = s["bad"][0]
    cut = first.find(". ")
    return first if cut < 0 else first[:cut + 1]
