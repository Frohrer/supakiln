FROM golang:1.22-bookworm

# Python hosts the worker. Go's compile toolchain stays as the image base
# so `go run`/`go build` inside the container is fast (no Go download per
# execution).
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    && rm -rf /var/lib/apt/lists/*

RUN getent passwd 1000 >/dev/null 2>&1 || useradd -m -u 1000 codeuser

RUN mkdir -p /opt/supakiln && chown -R 1000:1000 /opt/supakiln
COPY --chown=1000:1000 workers/worker.py /opt/supakiln/worker.py

# Writable GOCACHE and GOPATH so `go run` works as UID 1000.
ENV GOCACHE=/tmp/.go-build
ENV GOPATH=/tmp/.go
RUN mkdir -p $GOCACHE $GOPATH && chown -R 1000:1000 $GOCACHE $GOPATH

ENV SUPAKILN_RUN_CMD="go run {file}"
ENV SUPAKILN_FILE_EXT=".go"

USER 1000
WORKDIR /tmp

EXPOSE 9999

CMD ["python3", "/opt/supakiln/worker.py"]
