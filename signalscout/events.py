from datetime import datetime, timedelta, timezone
import yaml
from .config import ROOT


def load_events(path=None) -> list[dict]:
    p = path or ROOT / "events.yaml"
    try:
        with open(p) as f:
            return (yaml.safe_load(f) or {}).get("events") or []
    except FileNotFoundError:
        return []


def upcoming(events: list[dict], now: datetime, hours: int) -> list[dict]:
    out = []
    for e in events:
        t = e["time"]
        if isinstance(t, str):
            t = datetime.strptime(t, "%Y-%m-%d %H:%M")
        t = t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
        if now <= t <= now + timedelta(hours=hours):
            out.append(e)
    return out
