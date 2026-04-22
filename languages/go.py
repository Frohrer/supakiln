from __future__ import annotations

from .base import Runtime


# Go dependency management is per-module (go.mod). Ad-hoc `go run` without
# a module doesn't mesh with `npm install`-style package layering. v1
# supports stdlib-only Go; dependencies are a follow-up (likely via a
# synthesized go.mod).
GO = Runtime(
    name="go",
    base_image_tag="supakiln-go:base",
    dockerfile_path="dockerfiles/go.Dockerfile",
    package_install_cmd_template=None,
    worker_port=9999,
)
