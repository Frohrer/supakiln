from __future__ import annotations

from .base import Runtime


NODE = Runtime(
    name="node",
    base_image_tag="supakiln-node:base",
    dockerfile_path="dockerfiles/node.Dockerfile",
    # Install into a fixed prefix; the base image sets NODE_PATH so user
    # code's require() resolves to these modules.
    package_install_cmd_template="cd /opt/supakiln/pkgs && npm install --no-audit --no-fund {packages}",
    worker_port=9999,
)
