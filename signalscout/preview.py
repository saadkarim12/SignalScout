"""Show what a Telegram alert would look like - WITHOUT sending anything."""
from pathlib import Path
from .alerts import format_alert
from .charts import make_chart
from .config import ROOT, load_config
from .scan import run_scan
from . import settings

if __name__ == "__main__":
    res = [r for r in run_scan(load_config(), False) if r.verdict in ("STRONG", "WATCH")]
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    if not res:
        print("No STRONG/WATCH setups right now, so there is nothing to preview.")
    else:
        r = res[0]
        print(format_alert(r, settings.get_account()))
        (out / "alert_preview.png").write_bytes(make_chart(r.df4h, r.symbol, r.entry, r.stop, r.target))
        print("\nChart saved: reports/alert_preview.png")
