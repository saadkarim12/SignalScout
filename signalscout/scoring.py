"""The 10-point checklist. Uses closed candles only."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import pandas as pd
from .indicators import sma, rsi, atr, pivot_highs, hidden_bullish_divergence
from .levels import find_support
from .events import upcoming
from .sizing import position_size


@dataclass
class Check:
    name: str
    passed: bool
    points: int
    max_points: int
    text: str
    must: bool = False
    detail: str = ""          # plain-English 'why' with the real numbers behind this line


@dataclass
class ScoreResult:
    symbol: str
    score: int = 0
    verdict: str = "NO_TRADE"
    entry: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    rr: float = 0.0
    rel_strength: float | None = None
    size: dict | None = None
    checks: list = field(default_factory=list)
    df4h: object = None
    fng: tuple | None = None


def _rel_strength(df4h: pd.DataFrame, btc4h: pd.DataFrame | None, days=30):
    n = days * 6
    if btc4h is None or len(df4h) <= n or len(btc4h) <= n:
        return None
    a = df4h["close"].iloc[-1] / df4h["close"].iloc[-1 - n] - 1
    b = btc4h["close"].iloc[-1] / btc4h["close"].iloc[-1 - n] - 1
    return float(a - b)


def score_coin(symbol, df4h, daily, fng, events, cfg, account, btc4h=None, now=None, risk=None, news_note="") -> ScoreResult:
    c, v = cfg["checklist"], cfg["verdict"]
    now = now or datetime.now(timezone.utc)
    r = ScoreResult(symbol, df4h=df4h, fng=fng)
    r.rel_strength = _rel_strength(df4h, btc4h) if symbol != "BTC/USDT" else None
    if len(daily) < c["sma_trend"] + 1 or len(df4h) < 60:
        r.checks.append(Check("data", False, 0, 0, "Not enough price history for this coin", must=True))
        return r

    close = df4h["close"].iloc[-1]
    last = df4h.iloc[-1]
    s200 = sma(daily["close"], c["sma_trend"]).iloc[-1]
    s50 = sma(daily["close"], c["sma_fast"]).iloc[-1]
    dclose = daily["close"].iloc[-1]

    # 1 Trend (MUST)
    ok = bool(dclose > s200)
    r.checks.append(Check("trend", ok, 2 * ok, 2, "Above 200-day average (uptrend)" if ok
                          else "Below 200-day average (downtrend)", must=True,
                          detail=f"The last closed daily candle closed at {dclose:,.6g}. The average of the last {c['sma_trend']} daily closes is {s200:,.6g}. "
                                 "Rule: the close must be ABOVE the average, otherwise the coin is in a downtrend and gets NO_TRADE. Worth 2 points."))
    # 2 Golden-cross zone
    ok = bool(s50 > s200)
    r.checks.append(Check("golden", ok, int(ok), 1, "50-day average above 200-day (healthy trend)" if ok
                          else "50-day average below 200-day",
                          detail=f"Average of the last {c['sma_fast']} daily closes: {s50:,.6g}. Average of the last {c['sma_trend']}: {s200:,.6g}. "
                                 "Rule: the shorter average above the longer one means the medium trend is stronger. Worth 1 point."))
    # 3 Location
    sup = find_support(df4h, daily, symbol, c)
    a4 = atr(df4h).iloc[-1]
    at_support = False
    sup_detail = "No support level was found below the price (support = the 50-day average, a broken old high, or a round number)."
    if sup:
        low3 = df4h["low"].iloc[-c["support_last_candles"]:].min()
        dist = abs(low3 - sup[0]) / sup[0] * 100
        at_support = dist <= c["support_tolerance_pct"]
        sup_detail = (f"Nearest support below the price: {sup[0]:,.6g} ({sup[1]}). The lowest low of the last {c['support_last_candles']} "
                      f"four-hour candles was {low3:,.6g}, which is {dist:.2f}% from it. Rule: within {c['support_tolerance_pct']}%. Worth 2 points.")
        txt = (f"Pulled back to support ${sup[0]:,.4g} ({sup[1]})" if at_support
               else f"Not at support (nearest ${sup[0]:,.4g}, {sup[1]})")
    else:
        txt = "No support level found below price"
    r.checks.append(Check("support", at_support, 2 * at_support, 2, txt, detail=sup_detail))
    # 4 Momentum cooled
    rs = rsi(df4h["close"])
    recent = rs.iloc[-c["rsi_lookback"]:]
    cooled = bool(((recent >= c["rsi_low"]) & (recent <= c["rsi_high"])).any())
    div = hidden_bullish_divergence(df4h, rs, c["div_pivot_bars"], c["div_lookback"], c["div_recent_bars"])
    ok = cooled or div
    zone = recent[(recent >= c["rsi_low"]) & (recent <= c["rsi_high"])]
    if cooled:
        txt = f"RSI cooled to {zone.iloc[-1]:.0f}"
    elif div:
        txt = f"Passed by hidden bullish divergence (RSI {rs.iloc[-1]:.0f} is outside the cooled zone)"
    else:
        txt = f"RSI {rs.iloc[-1]:.0f} is not in the cooled zone ({c['rsi_low']}-{c['rsi_high']})"
    r.checks.append(Check("momentum", ok, int(ok), 1, txt, detail=(
        "RSI (14) of the last 5 four-hour candles, oldest to newest: " + ", ".join(f"{v:.0f}" for v in recent) +
        f". Rule: any value between {c['rsi_low']} and {c['rsi_high']} (the rise has calmed down), OR a hidden bullish divergence "
        "(price makes a higher low while RSI makes a lower low, so selling is weakening). Worth 1 point in total.")))
    r.checks.append(Check("divergence", div, 0, 0,
                          "Hidden bullish divergence: SEEN (price made a higher low while RSI made a lower low)" if div
                          else "Hidden bullish divergence: not seen",
                          detail=("Information only, no points of its own. It is the second way to earn the RSI point above: "
                                  "if the price makes a HIGHER low while RSI makes a LOWER low, selling is weakening. "
                                  "It is only counted when the second low is within the last "
                                  f"{c['div_recent_bars']} four-hour candles. "
                                  + ("It was seen now." if div else "It was not seen now, which is normal: it is rare on a 4-hour chart. "
                                     "If RSI is already cooled you do not need it."))))
    # 5 Bounce confirmation
    rng = last["high"] - last["low"]
    top = rng > 0 and (last["close"] - last["low"]) / rng >= 1 - c["bounce_close_top_pct"] / 100
    volx = last["volume"] / df4h["volume"].rolling(20).mean().iloc[-1]
    ok = bool(last["close"] > last["open"] and top and volx > c["bounce_volume_mult"])
    pos = (last["close"] - last["low"]) / rng * 100 if rng > 0 else 0
    r.checks.append(Check("bounce", ok, int(ok), 1,
                          f"Green bounce candle, volume {volx:.1f}x normal" if ok
                          else f"No clear bounce candle (volume {volx:.1f}x normal)",
                          detail=(f"Last closed 4-hour candle: open {last['open']:,.6g}, high {last['high']:,.6g}, low {last['low']:,.6g}, "
                                  f"close {last['close']:,.6g}. Green (close above open): {'yes' if last['close'] > last['open'] else 'NO'}. "
                                  f"Close is {pos:.0f}% of the way up its range (needs {100 - c['bounce_close_top_pct']}% or more). "
                                  f"Volume is {volx:.1f}x the 20-candle average (needs more than {c['bounce_volume_mult']}x). "
                                  "All three must be true. Worth 1 point.")))
    # 6 Sentiment
    if fng is None:
        r.checks.append(Check("sentiment", False, 0, 1, "Fear & Greed unavailable (scored 0)",
                              detail="The Fear & Greed service could not be reached, so this point is not given."))
    else:
        ok = fng[0] < c["fear_below"]
        r.checks.append(Check("sentiment", ok, int(ok), 1,
                              f"Fear & Greed {fng[0]} ({fng[1]})" + ("" if ok else " - not fearful"),
                              detail=f"The Fear & Greed index today is {fng[0]} out of 100 ({fng[1]}) from alternative.me. "
                                     f"The point is given only when it is below {c['fear_below']} (a scared market). "
                                     "It is one number for the whole market, the same for every coin."))
    # 7 News-clear: big scheduled event within 24h, or a risky headline about this coin / the whole market
    soon = upcoming(events, now, c["news_window_hours"])
    flags = risk or []
    ok = not soon and not flags
    if soon:
        txt = f"Big event soon: {soon[0]['name']}"
    elif flags:
        txt = f"Risky headline: {flags[0]['title'][:80]} ({flags[0]['source']})"
    else:
        txt = "No big scheduled event or risky headline in the last/next 24h" + (f" ({news_note})" if news_note else "")
    ev_txt = ("; ".join(f"{e['name']} at {e['time']:%a %d %b %H:%M} UTC" for e in soon) if soon
              else f"none in the next {c['news_window_hours']} hours")
    hd_txt = ("; ".join(f"\"{h['title'][:90]}\" ({h['source']})" for h in flags) if flags
              else "none mention this coin (or a big platform like Binance or Tether) together with a risk word")
    r.checks.append(Check("news", ok, int(ok), 1, txt, detail=(
        f"Scheduled big events: {ev_txt}. Risky headlines in the last 24 hours (Binance official announcements, CoinDesk, Cointelegraph, "
        f"The Block): {hd_txt}. Sources {news_note or 'not available'}. "
        "The point is given when there is no big event in the next 24 hours AND no risky headline. A Binance delisting notice "
        "that names the coin counts for 7 days. Worth 1 point.")))
    # 8 Reward:Risk (MUST)
    rr_ok = False
    if sup and pd.notna(a4):
        entry = close
        stop = sup[0] - c["atr_stop_mult"] * a4
        lookback = df4h.iloc[-c["swing_lookback"]:].reset_index(drop=True)
        above = [lookback["high"].iloc[i] for i in pivot_highs(lookback["high"], c["pivot_bars"])
                 if lookback["high"].iloc[i] > entry]
        if above:
            target = above[-1]
        else:
            target = entry + c["atr_daily_target_mult"] * atr(daily).iloc[-1]
        if entry > stop:
            cap = c.get("target_cap_rr")
            if cap:
                target = min(target, entry + cap * (entry - stop))
            rr = (target - entry) / (entry - stop)
            r.entry, r.stop, r.target, r.rr = entry, stop, target, rr
            rr_ok = rr >= c["min_rr"] - 1e-9
    r.checks.append(Check("rr", rr_ok, int(rr_ok), 1,
                          f"Reward:Risk {r.rr:.1f} (need {c['min_rr']}+)", must=True,
                          detail=(f"Buy price {r.entry:,.6g} (close of the last closed 4h candle). Stop {r.stop:,.6g} (the support minus half an "
                                  f"average candle). Target {r.target:,.6g} (the most recent swing high above the price, or 3 average daily moves). "
                                  f"Possible win {r.target - r.entry:,.6g} divided by possible loss {r.entry - r.stop:,.6g} = {r.rr:.2f}. "
                                  f"Needs {c['min_rr']} or more, otherwise NO_TRADE. Worth 1 point.") if r.entry else "No valid stop could be worked out."))

    r.score = sum(k.points for k in r.checks)
    if any(k.must and not k.passed for k in r.checks):
        r.verdict = "NO_TRADE"
    elif r.score >= v["strong_min"]:
        r.verdict = "STRONG"
    elif r.score >= v["watch_min"]:
        r.verdict = "WATCH"
    else:
        r.verdict = "SKIP"
    if r.verdict in ("STRONG", "WATCH") and r.entry > r.stop:
        risk = v["strong_risk_pct"] if r.verdict == "STRONG" else v["watch_risk_pct"]
        r.size = position_size(account, risk, r.entry, r.stop, v["max_position_pct"])
    return r


def rank(results: list[ScoreResult]) -> list[ScoreResult]:
    order = {"STRONG": 0, "WATCH": 1, "SKIP": 2, "NO_TRADE": 3}
    return sorted(results, key=lambda x: (order[x.verdict], -x.score, -x.rr,
                                          -(x.rel_strength if x.rel_strength is not None else -9)))
