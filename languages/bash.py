from __future__ import annotations

from .base import Runtime


# Bash scripts call external tools; we don't try to be a package manager.
BASH = Runtime(
    name="bash",
    base_image_tag="supakiln-bash:base",
    dockerfile_path="dockerfiles/bash.Dockerfile",
    package_install_cmd_template=None,
    file_extension=".sh",
    display_name="Bash",
    package_manager=None,
    worker_port=9999,
)
