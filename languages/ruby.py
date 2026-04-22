from __future__ import annotations

from .base import Runtime


RUBY = Runtime(
    name="ruby",
    base_image_tag="supakiln-ruby:base",
    dockerfile_path="dockerfiles/ruby.Dockerfile",
    # System-wide gem install; user code `require "gem"` resolves via
    # Ruby's default load paths.
    package_install_cmd_template="gem install --no-document {packages}",
    worker_port=9999,
)
