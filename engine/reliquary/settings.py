"""User settings, stored as JSON in the app's data folder."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .rpc import Failure, method

HOME = Path(os.environ.get("RELIQUARY_HOME") or Path.home() / ".reliquary")
FILE = HOME / "settings.json"

DEFAULTS = {
    "game_dir": "",
    "blender": "",
    "oodle": "",
    "library": str(HOME / "library"),
    "steam_user": "",
}

_lock = threading.Lock()


def load() -> dict:
    try:
        stored = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def update(**changes) -> dict:
    unknown = set(changes) - set(DEFAULTS)
    if unknown:
        raise Failure(f"Unknown settings: {', '.join(sorted(unknown))}")
    with _lock:
        merged = {**load(), **changes}
        HOME.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged


@method("settings.get")
def get() -> dict:
    return load()


@method("settings.set")
def set_(**changes) -> dict:
    return update(**changes)
