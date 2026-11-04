"""The only module that reads or writes data/. Plain JSON files, written atomically."""
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config


def _data() -> Path:
    return config.DATA_DIR


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---- sessions -------------------------------------------------------------

def _session_path(sid: str) -> Path:
    if not sid.replace("_", "").isalnum():
        raise ValueError("bad session id")
    return _data() / "chats" / f"{sid}.json"


def new_session(topic: str, model: str, effort: str) -> dict:
    sid = f"s_{int(time.time())}_{secrets.token_hex(3)}"
    title = topic.strip().splitlines()[0][:60] if topic.strip() else "New lesson"
    s = {
        "id": sid,
        "title": title,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "model": model,
        "effort": effort,
        "phase": "probe",
        "messages": [],
        "pending_results": [],
        "probe": None,
        "plan": None,
        "usage": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "cost": 0.0},
    }
    save_session(s)
    return s


def save_session(s: dict) -> None:
    s["updated_at"] = now_iso()
    _write_json(_session_path(s["id"]), s)


def load_session(sid: str) -> dict | None:
    return _read_json(_session_path(sid), None)


def list_sessions() -> list[dict]:
    out = []
    for p in (_data() / "chats").glob("s_*.json"):
        s = _read_json(p, None)
        if s:
            out.append(s)
    out.sort(key=lambda s: s["updated_at"], reverse=True)
    return out


# ---- usage ----------------------------------------------------------------

def append_usage(record: dict) -> None:
    path = _data() / "usage.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def month_cost(month: str | None = None) -> float:
    month = month or now_iso()[:7]
    total = 0.0
    path = _data() / "usage.jsonl"
    if not path.exists():
        return 0.0
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("at", "").startswith(month):
            total += r.get("cost", 0.0)
    return total


# ---- profile & settings ---------------------------------------------------

def load_profile() -> dict:
    return _read_json(_data() / "profile.json", None) or dict(config.DEFAULT_PROFILE)


def save_profile(p: dict) -> None:
    _write_json(_data() / "profile.json", p)


def load_settings() -> dict:
    saved = _read_json(_data() / "settings.json", {})
    return {**config.DEFAULT_SETTINGS, **saved}


def save_settings(s: dict) -> None:
    _write_json(_data() / "settings.json", s)
