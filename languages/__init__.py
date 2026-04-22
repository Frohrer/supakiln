"""Language runtimes for supakiln code execution.

Each runtime describes how to build a per-language container image (base
image tag, Dockerfile path, package-install snippet) and what port the
in-container worker listens on. The runtime is the single source of truth
for "what does language X need"; CodeExecutor stays language-agnostic.

Adding a language means: drop a new Runtime instance into its own module
(e.g. languages/node.py) and import it from here so registration happens
at import time.
"""

from __future__ import annotations

from typing import Dict, List

from .base import Runtime
from .python import PYTHON


_REGISTRY: Dict[str, Runtime] = {}


def register(runtime: Runtime) -> None:
    _REGISTRY[runtime.name] = runtime


def get(name: str) -> Runtime:
    if name not in _REGISTRY:
        raise KeyError(f"unknown language: {name!r} (known: {sorted(_REGISTRY)})")
    return _REGISTRY[name]


def names() -> List[str]:
    return sorted(_REGISTRY)


# Register built-ins at import time.
register(PYTHON)


__all__ = ["Runtime", "register", "get", "names", "PYTHON"]
