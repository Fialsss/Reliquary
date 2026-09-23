"""Operators, read from the installed game through the vendored R6 parser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import env
from .rpc import Failure, method

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "r6parser"))


@method("operators.list")
def list_operators() -> list[dict]:
    game = env.find_game()
    if game is None:
        raise Failure("Game folder not found. Set it in Settings.")
    oodle = env.find_oodle()
    if oodle:
        os.environ["R6_OODLE_DLL"] = str(oodle)
    from src.decompress import OodleUnavailableError
    from src.operator_registry import read_operator_registry

    try:
        roster = read_operator_registry(game / "datapc64.forge")
    except OodleUnavailableError as error:
        raise Failure("Oodle runtime not found. Point Reliquary to an oo2core_*_win64.dll in Settings.") from error
    except ValueError as error:
        # the registry layout moves with game updates; say so instead of a stack trace
        raise Failure(f"This game build isn't supported by the operator reader yet ({error})") from error
    return sorted(({"uid": f"{o.uid:016X}", "name": o.name} for o in roster), key=lambda o: o["name"])
