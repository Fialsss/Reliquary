"""JSON-lines protocol between the Electron shell and the engine.

Requests arrive on stdin as {"id", "method", "params"}. Each one runs on its own
thread, so a long download never blocks a settings read. Replies and events
share stdout, one JSON object per line: {"id", "result"} / {"id", "error"} or
{"event", "data"}.
"""
from __future__ import annotations

import json
import sys
import threading
import traceback
from typing import Any, Callable

METHODS: dict[str, Callable[..., Any]] = {}
_out = threading.Lock()


class Failure(Exception):
    """An error meant for the user: shown as-is, without a type name."""


def method(name: str):
    def register(function):
        METHODS[name] = function
        return function
    return register


def _send(message: dict) -> None:
    line = json.dumps(message, ensure_ascii=False)
    with _out:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def emit(event: str, data: Any = None) -> None:
    _send({"event": event, "data": data})


def _handle(request: dict) -> None:
    ident = request.get("id")
    try:
        function = METHODS.get(request.get("method", ""))
        if function is None:
            raise Failure(f"Unknown method {request.get('method')!r}")
        _send({"id": ident, "result": function(**(request.get("params") or {}))})
    except Failure as error:
        _send({"id": ident, "error": str(error)})
    except Exception as error:
        traceback.print_exc()
        _send({"id": ident, "error": f"{type(error).__name__}: {error}"})


def serve() -> None:
    workers = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            print(f"Ignored malformed request: {line[:120]}", file=sys.stderr)
            continue
        worker = threading.Thread(target=_handle, args=(request,), daemon=True)
        worker.start()
        workers = [w for w in workers if w.is_alive()] + [worker]
    for worker in workers:  # stdin closed: finish what was asked, then exit
        worker.join()
