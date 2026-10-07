"""Chart picture: last 120 four-hour candles, 50/200 averages, entry/stop/target lines."""
import io
import matplotlib
matplotlib.use("Agg")
import mplfinance as mpf
import pandas as pd
from .indicators import sma


def make_chart(df: pd.DataFrame, symbol: str, entry=0, stop=0, target=0) -> bytes:
    d = df.copy()
    d.index = pd.to_datetime(d["ts"], unit="ms")
    d.columns = [c.capitalize() if c != "ts" else c for c in d.columns]
    ma50, ma200 = sma(d["Close"], 50), sma(d["Close"], 200)
    d, ma50, ma200 = d.iloc[-120:], ma50.iloc[-120:], ma200.iloc[-120:]
    ap = [mpf.make_addplot(ma50, color="orange", width=1), mpf.make_addplot(ma200, color="purple", width=1)]
    lines = [(v, c) for v, c in ((entry, "blue"), (stop, "red"), (target, "green")) if v]
    kw = {"hlines": {"hlines": [v for v, _ in lines], "colors": [c for _, c in lines], "linestyle": "--"}} if lines else {}
    buf = io.BytesIO()
    mpf.plot(d[["Open", "High", "Low", "Close", "Volume"]], type="candle", addplot=ap, volume=True,
             style="yahoo", title=f"{symbol} 4-hour (blue=entry, red=stop, green=target)",
             savefig=dict(fname=buf, dpi=110, format="png"), **kw)
    return buf.getvalue()
