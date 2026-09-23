"""Operators: the roster from the installed game, exported to glTF and opened in Blender.

Everything goes through the vendored R6-parser: its registry reader lists the
operators, its asset index (SQLite, built once and refreshed after game
updates) finds every mesh and texture, and its exporter writes each default
head and body model. Blender imports them with the parser's add-on, which
rebuilds the Siege materials.
"""
from __future__ import annotations

import functools
import os
import subprocess
import sys
import threading
from pathlib import Path

from . import env, settings
from .rpc import Failure, emit, method

ENGINE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
PARSER = ENGINE / "r6parser"
sys.path.insert(0, str(PARSER))

_busy = threading.Lock()  # indexing and exporting both read the whole game: one at a time


def _game() -> Path:
    game = env.find_game()
    if game is None:
        raise Failure("Game folder not found. Set it in Settings.")
    oodle = env.find_oodle()
    if oodle:
        os.environ["R6_OODLE_DLL"] = str(oodle)
    return game


def _database() -> Path:
    return settings.HOME / "r6-assets.sqlite"


@functools.lru_cache(maxsize=1)
def _read_roster(archive: str, modified: int) -> tuple:
    from src.decompress import OodleUnavailableError
    from src.operator_registry import read_operator_registry

    try:
        return read_operator_registry(archive)
    except OodleUnavailableError as error:
        raise Failure("Oodle runtime not found. Point Reliquary to an oo2core_*_win64.dll in Settings.") from error
    except ValueError as error:
        # the registry layout moves with game updates; say so instead of a stack trace
        raise Failure(f"This game build isn't supported by the operator reader yet ({error})") from error


def _roster() -> tuple:
    archive = _game() / "datapc64.forge"
    return _read_roster(str(archive), archive.stat().st_mtime_ns)  # cached until the game updates


def _folder_name(name: str) -> str:
    return "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in name).strip().rstrip(".") or "operator"


def _parts(operator) -> list[tuple[str, int]]:
    """The primary (group 0) models of the default body and head, as the parser's own app exports them."""
    return [(label, uid) for label, part in (("body", operator.body), ("head", operator.head))
            for uid in dict.fromkeys(part.model_groups[0] if part.model_groups else ())]


def _exported(name: str) -> str:
    folder = Path(settings.load()["exports"]) / _folder_name(name)
    return str(folder) if any(folder.glob("*/*/*.gltf")) else ""


@method("operators.list")
def list_operators() -> list[dict]:
    return sorted(({"uid": f"{o.uid:016X}", "name": o.name, "models": len(_parts(o)), "exported": _exported(o.name)}
                   for o in _roster()), key=lambda o: o["name"])


@method("operators.status")
def status() -> dict:
    database = _database()
    return {"indexed": database.is_file(), "bytes": database.stat().st_size if database.is_file() else 0,
            "exports": settings.load()["exports"], "busy": _busy.locked()}


@method("operators.index")
def build_index() -> dict:
    """Index every archive of the game (only the changed ones on later runs): a few minutes the first time."""
    from src.database import index_archive

    game = _game()
    if not _busy.acquire(blocking=False):
        raise Failure("error.opBusy")
    try:
        archives = sorted(game.glob("*.forge"))
        failed = []
        for done, archive in enumerate(archives):
            emit("operators.progress", {"step": "index", "done": done, "total": len(archives), "file": archive.name})
            try:
                index_archive(archive, _database())
            except Exception as error:  # one unreadable archive shouldn't cost the whole index
                print(f"Index failed for {archive.name}: {error}", file=sys.stderr)
                failed.append(archive.name)
        emit("operators.progress", {"step": "index", "done": len(archives), "total": len(archives), "file": ""})
    finally:
        _busy.release()
    return {**status(), "failed": failed}


def _export_model(uid: int, children: dict, database: Path, output: Path) -> None:
    """The parser CLI's `model --depgraph --database` path, without its console output."""
    from src.cli import _load_database_model_index
    from src.database import load_asset_index
    from src.depgraph import load_depgraph
    from src.model import export_model

    if uid not in children:  # some models live in their own bundle's dependency graph
        record = load_asset_index(database, {uid}).primary(uid)
        own = record.archive.with_suffix(".depgraphbin") if record is not None else None
        if own is not None and own.is_file():
            own_children = load_depgraph(own)
            if uid in own_children:
                children = own_children
    export_model(uid, children, _load_database_model_index(database, uid, children), output)


@method("operators.export")
def export(uid: str) -> dict:
    from src.depgraph import load_depgraph

    game = _game()
    if not _database().is_file():
        raise Failure("error.noIndex")
    operator = next((o for o in _roster() if f"{o.uid:016X}" == uid), None)
    if operator is None:
        raise Failure(f"Unknown operator {uid}")
    parts = _parts(operator)
    if not parts:
        raise Failure(f"No default models found for {operator.name}")
    target = Path(settings.load()["exports"]) / _folder_name(operator.name)
    if not _busy.acquire(blocking=False):
        raise Failure("error.opBusy")
    try:
        children = load_depgraph(game / "datapc64_ondemand.depgraphbin")
        for done, (label, model) in enumerate(parts):
            emit("operators.progress", {"step": "export", "uid": uid, "done": done, "total": len(parts), "file": label})
            try:
                _export_model(model, children, _database(), target / label / f"{model:016X}")
            except (FileNotFoundError, ValueError) as error:
                raise Failure(f"{operator.name}: {label} model {model:016X} failed ({error})") from error
        emit("operators.progress", {"step": "export", "uid": uid, "done": len(parts), "total": len(parts), "file": ""})
    finally:
        _busy.release()
    return {"folder": str(target), "models": len(parts)}


@method("operators.blender")
def open_in_blender(folder: str) -> bool:
    """Start Blender on an exported operator: the parser's add-on imports it with the Siege materials."""
    blender, _ = env.find_blender()
    if blender is None:
        raise Failure("error.noBlender")
    if not any(Path(folder).glob("*/*/*.gltf")):
        raise Failure("error.notExported")
    script = Path(__file__).resolve().parent / "blender_import.py"
    subprocess.Popen([str(blender), "--python", str(script), "--", str(PARSER / "blender_addon"), folder],
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return True
