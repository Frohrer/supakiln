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
  SUPAKILN_WORKER_TOKEN  required bearer secret; caller must send it as
                         `X-Supakiln-Token`. Blocks sibling containers
                         (no auth previously → cross-worker RCE).

Wire contract:
  GET  /health  -> 200 {"status": "ok"}      (unauthenticated)
  POST /exec    -> body: {"code": str, "env": {str: str}, "timeout_ms": int}
                  headers: X-Supakiln-Token: <secret>
                  resp: {"exit_code": int, "stdout": str, "stderr": str, "timed_out": bool}
"""

from __future__ import annotations

import hmac
import json
import os
import shlex
import signal
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


DEFAULT_PORT = 9999
MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MiB guard against runaway payloads

RUN_CMD_TEMPLATE = os.environ.get("SUPAKILN_RUN_CMD", "python3 {file}")
FILE_EXT = os.environ.get("SUPAKILN_FILE_EXT", ".py")
# Set by the backend at `docker run` time. If empty, /exec is wide open
# (dev-only fallback). In production the backend always sets it.
EXPECTED_TOKEN = os.environ.get("SUPAKILN_WORKER_TOKEN", "")


def _build_command(file_path: str) -> list:
    """Render RUN_CMD_TEMPLATE by substituting {file}, respecting shell splitting."""
    parts = shlex.split(RUN_CMD_TEMPLATE)
    return [p.replace("{file}", file_path) for p in parts]


def _reap_leftover_state(own_pid: int, own_script_path: str | None) -> None:
    """Kill straggler processes and wipe scratch dirs between /exec calls.

    Runs in the worker's finally after every execution — successful,
    failed, or timed out. We own uid 1000; the worker process is pid 1
    inside its container (or very close to it). Everything else owned
    by this uid is user code that may have forked, backgrounded, or
    otherwise outlived the request. Kill it so state never leaks into
    the next call.

    Scratch wipe also bounds tmpfs usage: a misbehaving run can't fill
    /tmp permanently because the next call clears it.
    """
    # 1) Kill every uid-1000 process except us.
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == own_pid:
                continue
            try:
                with open(f"/proc/{pid}/status", "r") as f:
                    body = f.read()
                # "Uid:\treal\teffective\tsaved\tfs"
                for line in body.splitlines():
                    if line.startswith("Uid:"):
                        parts = line.split()
                        if len(parts) >= 2 and parts[1] == str(os.getuid()):
                            try:
                                os.kill(pid, signal.SIGKILL)
                            except (ProcessLookupError, PermissionError):
                                pass
                        break
            except (OSError, ValueError):
                continue
    except OSError:
        pass

    # 2) Wipe /tmp and /home/codeuser. Keep the directories themselves
    # (tmpfs mount points must exist). Don't delete the script path if
    # we haven't removed it yet — the caller handles it.
    for root in ("/tmp", "/home/codeuser"):
        try:
            for name in os.listdir(root):
                path = os.path.join(root, name)
                if path == own_script_path:
                    continue
                try:
                    if os.path.isdir(path) and not os.path.islink(path):
                        import shutil
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.unlink(path)
                except OSError:
                    pass
        except OSError:
            pass


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
    # Caller-supplied env vars win over inherited ones. Strip the worker
    # token from the child's env — user code has no business reading it.
    proc_env.pop("SUPAKILN_WORKER_TOKEN", None)
    proc_env.update({str(k): str(v) for k, v in (env or {}).items()})

    proc: subprocess.Popen | None = None
    try:
        # start_new_session makes the child the leader of a new process
        # group. On timeout / normal exit we kill the whole group via
        # killpg, which catches `cmd &` background subprocesses that
        # `subprocess.run`'s plain kill would otherwise leak.
        proc = subprocess.Popen(
            _build_command(fname),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=proc_env,
            cwd="/tmp",
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
            return {
                "exit_code": proc.returncode,
                "stdout": (stdout or b"").decode("utf-8", "replace"),
                "stderr": (stderr or b"").decode("utf-8", "replace"),
                "timed_out": False,
            }
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            # Drain whatever the child emitted before we killed it.
            try:
                stdout, stderr = proc.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
            return {
                "exit_code": -1,
                "stdout": (stdout or b"").decode("utf-8", "replace"),
                "stderr": (stderr or b"").decode("utf-8", "replace")
                         + f"\n--- Execution timed out after {timeout_s:.3f}s ---",
                "timed_out": True,
            }
    finally:
        # Make sure the process group is gone even on success; user code
        # may have forked daemons that we need to reap.
        if proc is not None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            os.remove(fname)
        except OSError:
            pass
        # Final scrub: kill lingering uid-1000 processes the user may
        # have nohup'd outside the process group, and wipe scratch dirs.
        _reap_leftover_state(own_pid=os.getpid(), own_script_path=None)


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

        # Bearer-token check. Constant-time compare to avoid exposing
        # the token through timing differences. When EXPECTED_TOKEN is
        # empty (legacy/dev) we skip the check.
        if EXPECTED_TOKEN:
            supplied = self.headers.get("X-Supakiln-Token", "")
            if not hmac.compare_digest(supplied, EXPECTED_TOKEN):
                self._json(401, {"error": "invalid or missing token"})
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
