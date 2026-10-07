"""Build the Telegram alert text in plain English."""
FOOTER = "Signal, not advice. You decide. Risk max 1%."


def tv_link(symbol: str) -> str:
    """Plain link to the same coin on TradingView (opens a chart; nothing is read from TradingView)."""
    return "https://www.tradingview.com/chart/?symbol=BINANCE:" + symbol.replace("/", "")


def money(x: float) -> str:
    return f"${x:,.2f}" if x < 100 else f"${x:,.0f}"


def format_alert(r, account: float) -> str:
    icon = "🟢 STRONG" if r.verdict == "STRONG" else "🟡 WATCH"
    risk = 1 if r.verdict == "STRONG" else 0.5
    stop_pct = (r.stop - r.entry) / r.entry * 100
    tgt_pct = (r.target - r.entry) / r.entry * 100
    lines = [f"{icon} setup — {r.symbol} (score {r.score}/10)",
             f"Buy price ~ {money(r.entry)}",
             f"Stop (sell if it falls here)  {money(r.stop)}  ({stop_pct:.1f}%)",
             f"Target (take profit)  {money(r.target)}  (+{tgt_pct:.1f}%)   Reward vs risk: {r.rr:.1f}"]
    if r.size:
        lines.append(f"How much: {money(r.size['usd'])} → most you can lose {money(r.size['max_loss'])} "
                     f"({risk:g}% of {money(account)})")
    lines += ["", "Why:"]
    lines += [("ℹ️ " if c.max_points == 0 else "✅ " if c.passed else "❌ ") + c.text for c in r.checks]
    lines += ["", f"Chart: {tv_link(r.symbol)}", "", FOOTER]
    return "\n".join(lines)
