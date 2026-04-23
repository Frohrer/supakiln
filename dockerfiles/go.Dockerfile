FROM golang:1.22-bookworm

# Python hosts the worker. Go's compile toolchain stays as the image base
# so `go run`/`go build` inside the container is fast (no Go download per
# execution).
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    && rm -rf /var/lib/apt/lists/*

RUN getent passwd 1000 >/dev/null 2>&1 || useradd -m -u 1000 codeuser

RUN mkdir -p /opt/supakiln && chmod 0755 /opt/supakiln

COPY workers/worker.py /opt/supakiln/worker.py
RUN chmod 0644 /opt/supakiln/worker.py

# GOCACHE / GOPATH under /tmp so `go run` as UID 1000 can write them.
# /tmp is the tmpfs mount added at container run, so this gives Go a
# clean scratchpad per container and doesn't persist compile state
# across restarts — intentional v1, a code-hash compile cache is the
# follow-up.
ENV GOCACHE=/tmp/.go-build
ENV GOPATH=/tmp/.go

ENV SUPAKILN_RUN_CMD="go run {file}"
ENV SUPAKILN_FILE_EXT=".go"

USER 1000
WORKDIR /tmp

EXPOSE 9999

CMD ["python3", "/opt/supakiln/worker.py"]
