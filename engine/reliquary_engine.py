"""Engine entry point: `python -m reliquary` from source, reliquary-engine.exe when frozen."""
from reliquary import env, operators, settings, vault  # noqa: F401  (modules register their methods)
from reliquary.rpc import emit, serve

emit("engine.ready", {"version": "0.1.0"})
serve()
