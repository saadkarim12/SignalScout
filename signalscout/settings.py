"""Settings you can change from Telegram (saved in data/settings.json)."""
import json
from .config import ROOT, load_config

F = ROOT / "data" / "settings.json"


def get_account() -> float:
    try:
        return float(json.loads(F.read_text())["account_size_usd"])
    except Exception:
        return float(load_config()["account_size_usd"])


def set_account(usd: float):
    F.parent.mkdir(exist_ok=True)
    try:
        d = json.loads(F.read_text())
    except Exception:
        d = {}
    d["account_size_usd"] = usd
    F.write_text(json.dumps(d))


def get_last_mode():
    try:
        return json.loads(F.read_text()).get("last_mode")
    except Exception:
        return None


def set_last_mode(m: str):
    try:
        d = json.loads(F.read_text())
    except Exception:
        d = {}
    d["last_mode"] = m
    F.parent.mkdir(exist_ok=True)
    F.write_text(json.dumps(d))


def get_dca_amount() -> float:
    try:
        return float(json.loads(F.read_text())["dca_amount"])
    except Exception:
        return float(load_config()["dca"]["amount_usd"])


def set_dca_amount(usd: float):
    try:
        d = json.loads(F.read_text())
    except Exception:
        d = {}
    d["dca_amount"] = usd
    F.parent.mkdir(exist_ok=True)
    F.write_text(json.dumps(d))


def get_tp_state() -> dict:
    try:
        return json.loads(F.read_text()).get("tp_state", {})
    except Exception:
        return {}


def set_tp_state(d: dict):
    try:
        cur = json.loads(F.read_text())
    except Exception:
        cur = {}
    cur["tp_state"] = d
    F.parent.mkdir(exist_ok=True)
    F.write_text(json.dumps(cur))
