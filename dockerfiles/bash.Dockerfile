FROM debian:bookworm-slim

# bash is already present; add python3 for the worker and common CLI
# tools users are likely to shell out to.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    ca-certificates \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

RUN getent passwd 1000 >/dev/null 2>&1 || useradd -m -u 1000 codeuser

RUN mkdir -p /opt/supakiln && chmod 0755 /opt/supakiln

COPY workers/worker.py /opt/supakiln/worker.py
RUN chmod 0644 /opt/supakiln/worker.py

ENV SUPAKILN_RUN_CMD="bash {file}"
ENV SUPAKILN_FILE_EXT=".sh"

USER 1000
WORKDIR /tmp

EXPOSE 9999

CMD ["python3", "/opt/supakiln/worker.py"]
