"""Weekly buy reminder (DCA = dollar-cost averaging: buy the same small amount every week).

Plain English:
- Every week we look at Market mode. IN -> buy the usual amount of BTC. OUT -> skip this week; the money stays as cash.
- Buys here are PRETEND (a diary). You place any real buy yourself.
- We also track "plain DCA" (buy every week no matter what) so you can see if the Market mode filter really helps.
"""
import pandas as pd

from .indicators import sma


def simulate_history(d: pd.DataFrame, amount: float, weekday: int, sma_days: int = 200) -> dict:
    """d: daily BTC candles (ts, open, close ...). Mode uses the PREVIOUS day's close; the buy happens at that day's open."""
    s = pd.DataFrame({"open": d["open"].to_numpy(), "close": d["close"].to_numpy()},
                     index=pd.to_datetime(d["ts"], unit="ms"))
    ma = sma(s["close"], sma_days)
    mode_in = (s["close"] > ma).shift(1)              # known before today's open
    weeks = s[(s.index.dayofweek == weekday) & mode_in.notna() & ma.shift(1).notna()]
    inn = mode_in.loc[weeks.index].astype(bool)
    plain_units = (amount / weeks["open"]).sum()
    mode_units = (amount / weeks["open"][inn]).sum()
    n, bought = len(weeks), int(inn.sum())
    last = s["close"].iloc[-1]
    put_in_plain = n * amount
    put_in_mode = bought * amount
    plain_val, mode_val = plain_units * last, mode_units * last
    cash_kept = (n - bought) * amount
    return dict(weeks=n, bought=bought, skipped=n - bought,
                plain=dict(invested=put_in_plain, value=plain_val, gain=plain_val / put_in_plain - 1),
                mode=dict(invested=put_in_mode, value=mode_val, cash=cash_kept,
                          gain=mode_val / put_in_mode - 1 if put_in_mode else 0,
                          wealth=mode_val + cash_kept),
                start=weeks.index[0], end=weeks.index[-1])


CHART = "https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT"


def weekly_decision(mode: str, price: float, amount: float) -> dict:
    """The diary records the cautious plan (skip when OUT); the plain plan (always buy) is tracked too."""
    base = (f"🗓 Weekly buy day.\nMarket mode: {mode} ({'uptrend' if mode == 'IN' else 'downtrend'}).\n"
            f"BTC ~ ${price:,.0f}. Your usual buy: ${amount:,.0f} = {amount / price:.6f} BTC.\n\n")
    if mode == "IN":
        tail = "Both plans say: BUY this week. Pretend buy logged. If you buy for real, do it yourself on your exchange."
        return dict(action="buy", units=amount / price, text=base + tail + f"\n\nChart: {CHART}\n\nOnly money you can afford to lose.")
    tail = ("Two ways to think about it:\n"
            "- Cautious plan: skip this week, keep the cash.\n"
            "- Plain plan: buy anyway (in 3 years of history, plain weekly buying ended richer, because it bought cheap in downtrends).\n"
            "Pretend diary logged as SKIP, and plain plan tracked too, so you can compare. You decide.")
    return dict(action="skip", units=0.0, text=base + tail + f"\n\nChart: {CHART}\n\nOnly money you can afford to lose.")


def summarize(rows, price: float) -> dict:
    """rows: (ts, mode, price, amount, action, units)"""
    if not rows:
        return {}
    amt = sum(r[3] for r in rows)
    buys = [r for r in rows if r[4] == "buy"]
    inv = sum(r[3] for r in buys)
    units = sum(r[5] for r in buys)
    plain_units = sum(r[3] / r[2] for r in rows)
    skipped_cash = sum(r[3] for r in rows if r[4] == "skip")
    return dict(weeks=len(rows), bought=len(buys), skipped=len(rows) - len(buys), invested=inv, units=units,
                value=units * price, gain=(units * price / inv - 1) if inv else 0.0,
                mode_wealth=units * price + skipped_cash, plain_value=plain_units * price, plain_invested=amt)


def format_summary(s: dict) -> str:
    if not s:
        return "No weekly buys logged yet. The first reminder comes on your buy day."
    return (f"Weekly buys so far: {s['weeks']} weeks ({s['bought']} bought, {s['skipped']} skipped)\n"
            f"Market-mode plan: put in ${s['invested']:,.0f}, worth ${s['value']:,.0f} now ({s['gain']*100:+.1f}%). "
            f"Plus ${s['plain_invested'] - s['invested']:,.0f} kept as cash.\n"
            f"Plain plan (buy every week): put in ${s['plain_invested']:,.0f}, worth ${s['plain_value']:,.0f} now.\n"
            "Pretend money only. Signal, not advice. You decide. Risk max 1%.")
