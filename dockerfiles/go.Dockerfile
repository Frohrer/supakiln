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

# Go needs three writable directories that must be on an exec filesystem:
#   GOCACHE   compile cache
#   GOPATH    module cache + bin
#   GOTMPDIR  the work dir `go run` creates and exec()s the linked binary
#             from (defaults to $TMPDIR or /tmp). Our /tmp is a docker
#             --tmpfs mount that defaults to noexec, so without GOTMPDIR
#             `go run` fails with "fork/exec: permission denied" on its
#             own output.
ENV GOCACHE=/home/codeuser/.cache/go-build
ENV GOPATH=/home/codeuser/go
ENV GOTMPDIR=/home/codeuser/.gotmp
RUN mkdir -p $GOCACHE $GOPATH $GOTMPDIR && chown -R 1000:1000 /home/codeuser

ENV SUPAKILN_RUN_CMD="go run {file}"
ENV SUPAKILN_FILE_EXT=".go"

USER 1000
WORKDIR /tmp

EXPOSE 9999

CMD ["python3", "/opt/supakiln/worker.py"]
