from __future__ import annotations

from .base import Runtime


PYTHON = Runtime(
    name="python",
    base_image_tag="supakiln-python:base",
    dockerfile_path="dockerfiles/python.Dockerfile",
    package_install_cmd_template="pip install --no-cache-dir {packages}",
    file_extension=".py",
    display_name="Python",
    package_manager="pip",
    worker_port=9999,
)
