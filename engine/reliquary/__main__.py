from . import env, operators, settings, vault  # noqa: F401  (modules register their methods)
from .rpc import emit, serve

emit("engine.ready", {"version": "0.1.0"})
serve()
