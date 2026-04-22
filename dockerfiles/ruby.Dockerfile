FROM ruby:3.3-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    && rm -rf /var/lib/apt/lists/*

RUN getent passwd 1000 >/dev/null 2>&1 || useradd -m -u 1000 codeuser

RUN mkdir -p /opt/supakiln && chown -R 1000:1000 /opt/supakiln
COPY --chown=1000:1000 workers/worker.py /opt/supakiln/worker.py

ENV SUPAKILN_RUN_CMD="ruby {file}"
ENV SUPAKILN_FILE_EXT=".rb"

USER 1000
WORKDIR /tmp

EXPOSE 9999

CMD ["python3", "/opt/supakiln/worker.py"]
