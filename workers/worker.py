"""Supakiln multi-language worker.

Long-running HTTP server inside each runtime container. Receives
code-execution requests over TCP, writes the submitted code to a temp
file, then spawns the language-specific interpreter/compiler as a
subprocess. Exists to bypass `docker exec` on the hot path (~75ms
namespace-entry cost) — the backend reaches us directly over the dind
bridge network instead.

The worker is language-agnostic: it is configured per-image via env vars.

  SUPAKILN_RUN_CMD   shell command template; {file} is replaced with the
                     path to the temp source file. Example:
                       "python3 {file}"   "node {file}"   "bash {file}"
                       "go run {file}"    "ruby {file}"
  SUPAKILN_FILE_EXT  suffix for the temp file (".py", ".js", ".rb", ...).
                     Some interpreters (e.g. go run) need a correct ext.
  SUPAKILN_WORKER_PORT, SUPAKILN_WORKER_BIND   listen config.

Wire contract:
  GET  /health  -> 200 {"status": "ok"}
  POST /exec    -> body: {"code": str, "env": {str: str}, "timeout_ms": int}
                  resp: {"exit_code": int, "stdout": str, "stderr": str, "timed_out": bool}
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


DEFAULT_PORT = 9999
MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MiB guard against runaway payloads

RUN_CMD_TEMPLATE = os.environ.get("SUPAKILN_RUN_CMD", "python3 {file}")
FILE_EXT = os.environ.get("SUPAKILN_FILE_EXT", ".py")


def _build_command(file_path: str) -> list:
    """Render RUN_CMD_TEMPLATE by substituting {file}, respecting shell splitting."""
    parts = shlex.split(RUN_CMD_TEMPLATE)
    return [p.replace("{file}", file_path) for p in parts]


def _run_code(code: str, env: dict, timeout_ms: int) -> dict:
    """Write code to a temp file and exec it via RUN_CMD_TEMPLATE."""
    timeout_s = max(0.001, timeout_ms / 1000.0)
    # Use /tmp inside the container (tmpfs-friendly, always writable).
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=FILE_EXT, delete=False, dir="/tmp", encoding="utf-8"
    ) as f:
        f.write(code)
        fname = f.name

    proc_env = os.environ.copy()
    # Caller-supplied env vars win over inherited ones.
    proc_env.update({str(k): str(v) for k, v in (env or {}).items()})

    try:
        result = subprocess.run(
            _build_command(fname),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=proc_env,
            cwd="/tmp",
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "exit_code": -1,
            "stdout": (e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")),
            "stderr": (e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or ""))
                     + f"\n--- Execution timed out after {timeout_s:.3f}s ---",
            "timed_out": True,
        }
    finally:
        try:
            os.remove(fname)
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    # Silence default access logging — the backend already logs executions.
    def log_message(self, *args, **kwargs) -> None:
        return

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/exec":
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "invalid content-length"})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json(400, {"error": "invalid body size"})
            return

        raw = self.rfile.read(length)
        try:
            req = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            self._json(400, {"error": f"invalid json: {e}"})
            return

        code = req.get("code")
        if not isinstance(code, str):
            self._json(400, {"error": "`code` must be a string"})
            return
        env = req.get("env") or {}
        if not isinstance(env, dict):
            self._json(400, {"error": "`env` must be an object"})
            return
        timeout_ms = int(req.get("timeout_ms", 30000))

        result = _run_code(code, env, timeout_ms)
        self._json(200, result)


def main() -> None:
    port = int(os.environ.get("SUPAKILN_WORKER_PORT", DEFAULT_PORT))
    bind = os.environ.get("SUPAKILN_WORKER_BIND", "0.0.0.0")
    server = ThreadingHTTPServer((bind, port), Handler)
    print(f"[supakiln-worker] listening on {bind}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
