# Benchmarks

`bench_executor.py` attributes end-to-end execution latency across:

- `execute_code` total (direct mode) or `POST /execute` total (http mode)
- Internal phases reported by `CodeExecutor` (package_hash, detect_web_service, base64 encode, `exec_run`, etc.)
- Raw `docker exec /bin/true` (pure namespace-entry cost) and `docker exec python3 -c pass` (exec + interpreter cold start) against the same cached container
- A derived "python3 cold start" figure (py_pass − /bin/true)
- A derived "network + FastAPI + DB-log" figure (http total − server total)

## Prerequisites

`docker-compose up` (or `docker-compose -f docker-compose.dev.yml up`) with backend and docker-daemon services healthy.

## Run it

The `direct` mode must run where `DOCKER_HOST` points at the dind sidecar — easiest is to exec into the backend container:

```bash
docker-compose exec backend python bench/bench_executor.py direct --iters 30
```

The `http` mode can run from anywhere that can reach the API:

```bash
# from host
python bench/bench_executor.py http --iters 30 --url http://localhost:8000

# or from inside the backend container
docker-compose exec backend python bench/bench_executor.py http --iters 30 --url http://localhost:8000
```

## Reading the output

Each row reports `min / p50 / p90 / p99 / max / mean` in milliseconds over N iterations.

Key rows:

- **`execute_code total`** — what a caller sees (minus FastAPI overhead)
- **`phase exec_run_ms`** — time for the `container.exec_run()` call: this is `docker exec` round-trip + interpreter cold start + user code
- **`phase containers_get_ms`** — docker-py SDK `containers.get()`; should be single-digit ms
- **`phase detect_web_service_ms`** — called unconditionally; currently does a socket-bind port allocation even when the code isn't a web service (suspected waste)
- **`raw docker exec /bin/true`** — pure namespace entry; the floor for any `docker exec` approach
- **`derived 'python3 cold start'`** — the cost we'd eliminate with a persistent worker

If `derived 'python3 cold start'` is a large fraction of `execute_code total`, a persistent-worker architecture is the right next step. If `raw /bin/true` alone is already >100ms, we need to skip `docker exec` entirely (e.g. talk to a socket inside the container).

Paste the output back and we'll pick the optimization.
