"""Runtime interface shared by all supported languages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class Runtime:
    """Describes how to build and run a language-specific worker container.

    The Runtime is intentionally data-only — the build and run logic lives
    in CodeExecutor, which treats all runtimes uniformly. To add behaviour
    that differs per-language (e.g. compiled languages needing a build
    step), extend the Runtime with the extra fields the executor consumes.
    """

    name: str                         # "python", "node", ...
    base_image_tag: str               # e.g. "supakiln-python:base"
    dockerfile_path: str              # "dockerfiles/python.Dockerfile"
    package_install_cmd_template: Optional[str]
    # ^ Shell command template run inside the image build to install a list
    #   of packages. `{packages}` is substituted with the shell-quoted
    #   package list. None means this runtime does not support ad-hoc
    #   packages (e.g. bash).
    worker_port: int = 9999
    # The worker's HTTP contract is identical across languages; only the
    # implementation (the binary invoked by the Dockerfile's CMD) differs.


def build_package_install_snippet(runtime: Runtime, packages: List[str]) -> str:
    """Render a Dockerfile RUN line to install `packages`, or empty string.

    Returns "" if no packages or the runtime doesn't support install.
    Uses shell-safe double-quoting since package specifiers can contain
    version markers (e.g. `numpy>=1.26`).
    """
    if not packages or not runtime.package_install_cmd_template:
        return ""
    quoted = " ".join(f'"{pkg}"' for pkg in packages)
    cmd = runtime.package_install_cmd_template.format(packages=quoted)
    return f"USER root\nRUN {cmd}\nUSER codeuser\n"
