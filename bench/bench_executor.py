"""Latency profiler for supakiln code execution.

Two modes:

  direct   Instantiates CodeExecutor in-process and drives execute_code
           directly. Must run where DOCKER_HOST points at the daemon that
           hosts user containers (i.e. inside the `backend` service in
           docker-compose, or with DOCKER_HOST set to the dind sidecar).

  http     Hits POST /execute over HTTP. Measures the full API round-trip
           (FastAPI + executor + logging). The server must be running.

Both modes run a warmup, then N timed iterations of a trivial payload, and
additionally probe raw `docker exec /bin/true` + `docker exec python3 -c 'pass'`
against the same container so we can separate namespace-entry cost from
interpreter cold start.

Usage:
    python bench/bench_executor.py direct --iters 30
    python bench/bench_executor.py http   --iters 30 --url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from time import perf_counter
from typing import Callable, Dict, List, Optional


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def pct(values: List[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    frac = k - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def summarize(name: str, samples: List[float]) -> Dict[str, float]:
    if not samples:
        return {"name": name, "n": 0}
    return {
        "name": name,
        "n": len(samples),
        "min": min(samples),
        "p50": pct(samples, 0.50),
        "p90": pct(samples, 0.90),
        "p99": pct(samples, 0.99),
        "max": max(samples),
        "mean": statistics.fmean(samples),
    }


def print_table(rows: List[Dict[str, float]]) -> None:
    if not rows:
        print("(no samples)")
        return
    cols = ["name", "n", "min", "p50", "p90", "p99", "max", "mean"]
    widths = {c: max(len(c), max(len(_fmt(r.get(c))) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print(header)
    print("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  ".join(_fmt(r.get(c)).ljust(widths[c]) for c in cols))


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def collect_phase_samples(phase_traces: List[Dict[str, float]]) -> Dict[str, List[float]]:
    """Transpose list-of-dicts into dict-of-lists, dropping None."""
    out: Dict[str, List[float]] = {}
    for trace in phase_traces:
        for k, v in trace.items():
            if v is None:
                continue
            out.setdefault(k, []).append(float(v))
    return out


def run_direct(iters: int) -> None:
    """Drive CodeExecutor in-process. Must have access to the user-container daemon."""
    from code_executor import CodeExecutor

    executor = CodeExecutor()

    # Warmup: first call builds image + creates container. Not timed.
    print("[direct] warming up (build image + create container)...", flush=True)
    warm = executor.execute_code("pass", [], timeout=30)
    if not warm.get("success"):
        print(f"[direct] warmup failed: {warm.get('error')}")
        executor.cleanup()
        return
    container_id = warm.get("container_id")
    print(f"[direct] warm container: {container_id[:12] if container_id else '?'}")

    # Timed iterations, trivial payload.
    totals: List[float] = []
    phase_traces: List[Dict[str, float]] = []
    for _ in range(iters):
        t0 = perf_counter()
        res = executor.execute_code("pass", [], timeout=30)
        elapsed_ms = (perf_counter() - t0) * 1000
        totals.append(elapsed_ms)
        if "timings_ms" in res:
            phase_traces.append(res["timings_ms"])

    # Raw docker-exec probes against the same container.
    raw_true: List[float] = []
    raw_py_pass: List[float] = []
    env = os.environ.copy()
    for _ in range(iters):
        t0 = perf_counter()
        subprocess.run(
            ["docker", "exec", container_id, "/bin/true"],
            capture_output=True, env=env, check=False,
        )
        raw_true.append((perf_counter() - t0) * 1000)

        t0 = perf_counter()
        subprocess.run(
            ["docker", "exec", container_id, "python3", "-c", "pass"],
            capture_output=True, env=env, check=False,
        )
        raw_py_pass.append((perf_counter() - t0) * 1000)

    # Report.
    print()
    print("=== direct mode ===")
    rows = [summarize("execute_code total (ms)", totals)]
    rows += [
        summarize(f"  phase {k} (ms)", v)
        for k, v in collect_phase_samples(phase_traces).items()
    ]
    rows += [
        summarize("raw docker exec /bin/true (ms)", raw_true),
        summarize("raw docker exec python3 -c pass (ms)", raw_py_pass),
    ]
    print_table(rows)

    # Diagnostic: derived interpreter cold-start = py_pass - true
    if raw_true and raw_py_pass:
        delta = [py - tr for py, tr in zip(raw_py_pass, raw_true)]
        print()
        print("derived 'python3 cold start' (py_pass - /bin/true):")
        print_table([summarize("delta (ms)", delta)])

    executor.cleanup()


def run_http(iters: int, url: str) -> None:
    import urllib.request
    import urllib.error

    endpoint = url.rstrip("/") + "/execute"
    payload = json.dumps({"code": "pass", "packages": []}).encode()
    headers = {"Content-Type": "application/json"}

    def call() -> tuple[float, Optional[Dict]]:
        req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
        t0 = perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()
        elapsed_ms = (perf_counter() - t0) * 1000
        try:
            return elapsed_ms, json.loads(body)
        except json.JSONDecodeError:
            return elapsed_ms, None

    print(f"[http] warming up against {endpoint}...", flush=True)
    _, warm = call()
    if warm and not warm.get("success"):
        print(f"[http] warmup non-success: {warm.get('error')}")

    totals: List[float] = []
    phase_traces: List[Dict[str, float]] = []
    for _ in range(iters):
        ms, body = call()
        totals.append(ms)
        if body and "timings_ms" in body:
            phase_traces.append(body["timings_ms"])

    print()
    print("=== http mode ===")
    rows = [summarize("POST /execute total (ms)", totals)]
    rows += [
        summarize(f"  phase {k} (ms)", v)
        for k, v in collect_phase_samples(phase_traces).items()
    ]
    print_table(rows)

    # If we got server-side totals, the delta is network + FastAPI + logging overhead.
    if phase_traces:
        server_total = [t.get("total_ms") for t in phase_traces if t.get("total_ms") is not None]
        if server_total and len(server_total) == len(totals):
            overhead = [c - s for c, s in zip(totals, server_total)]
            print()
            print("derived 'network + FastAPI + DB-log' overhead (client - server total):")
            print_table([summarize("delta (ms)", overhead)])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["direct", "http"])
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--url", default="http://localhost:8000")
    args = ap.parse_args()

    if args.mode == "direct":
        run_direct(args.iters)
    else:
        run_http(args.iters, args.url)


if __name__ == "__main__":
    main()
