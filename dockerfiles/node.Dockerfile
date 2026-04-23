FROM node:20-slim

# Python is the worker runtime. It's a small addition (~20MB) and keeps
# worker maintenance to one implementation across all languages.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# node:20-slim already ships a `node` user at UID 1000 — reuse it.
RUN getent passwd 1000 >/dev/null 2>&1 || useradd -m -u 1000 codeuser

# /opt/supakiln is root-owned world-readable (+x for dir, 0644 for files)
# so user code as UID 1000 can read but not modify worker.py or the
# installed npm packages.
RUN mkdir -p /opt/supakiln/pkgs && chmod 0755 /opt/supakiln /opt/supakiln/pkgs

COPY workers/worker.py /opt/supakiln/worker.py
RUN chmod 0644 /opt/supakiln/worker.py

# User code requires('pkg') resolves via NODE_PATH → installed packages.
ENV NODE_PATH="/opt/supakiln/pkgs/node_modules"
ENV SUPAKILN_RUN_CMD="node {file}"
ENV SUPAKILN_FILE_EXT=".js"

USER 1000
WORKDIR /tmp

EXPOSE 9999

CMD ["python3", "/opt/supakiln/worker.py"]
