"""Engine entry point: `python -m reliquary` from source, reliquary-engine.exe when frozen."""
import threading

from reliquary import art, env, legacy, operators, settings, steam, vault  # noqa: F401  (modules register their methods)
from reliquary.rpc import emit, serve

threading.Thread(target=vault.prefetch_tool, daemon=True).start()
emit("engine.ready", {"version": "0.5.0"})
serve()
