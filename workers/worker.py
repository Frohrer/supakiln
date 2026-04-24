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
  GET  /health  -> 200 {"status": "ok", "cooked": bool,
                        "pids": {"current": int, "max": int|null},
                        "memory": {"current": int, "max": int|null}}
                  (unauthenticated). `cooked` flips to true when cgroup
                  pressure crosses SUPAKILN_COOKED_THRESHOLD_PCT (90 by
                  default) — the backend reaper uses this to evict
                  containers that are one fork away from wedging.
  POST /exec    -> body: {"code": str, "env": {str: str}, "timeout_ms": int}
                  headers: X-Supakiln-Token: <secret>
                  resp: {"exit_code": int, "stdout": str, "stderr": str, "timed_out": bool}
                  503  -> {"error": str, "cooked": true} when the container
                          is exhausted (e.g. pid-bomb hit --pids-limit, so
                          Popen fails with EAGAIN before we can spawn).
                          Backend MUST evict the container on this response.
"""

from __future__ import annotations

import errno
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

# Cgroup v2 paths. When --pids-limit/--memory are set, the kernel exposes
# the limits here. Reading them gives us a container's-eye view of how
# close we are to wedging; the backend health-probe reaper uses this to
# evict cooked workers before /exec starts failing.
CGROUP_PIDS_CURRENT = "/sys/fs/cgroup/pids.current"
CGROUP_PIDS_MAX = "/sys/fs/cgroup/pids.max"
CGROUP_MEM_CURRENT = "/sys/fs/cgroup/memory.current"
CGROUP_MEM_MAX = "/sys/fs/cgroup/memory.max"

# Percent-of-limit above which we declare the container "cooked" in /health.
# Tuned so a pid bomb that's still mid-fork trips this before the subsequent
# /exec actually EAGAINs.
try:
    _COOKED_THRESHOLD = float(
        os.environ.get("SUPAKILN_COOKED_THRESHOLD_PCT", "90")
    ) / 100.0
except ValueError:
    _COOKED_THRESHOLD = 0.90

# Fork/memory errnos we treat as "container is exhausted, evict me".
# EAGAIN   = pids.max hit or RLIMIT_NPROC hit (fork bomb)
# ENOMEM   = memory.max hit or RLIMIT_AS hit (memory bomb)
# ENOSPC   = tmpfs full (disk bomb) — we hit this writing the source file
_COOKED_ERRNOS = {errno.EAGAIN, errno.ENOMEM, errno.ENOSPC}


def _build_command(file_path: str) -> list:
    """Render RUN_CMD_TEMPLATE by substituting {file}, respecting shell splitting."""
    parts = shlex.split(RUN_CMD_TEMPLATE)
    return [p.replace("{file}", file_path) for p in parts]


def _read_int_file(path: str) -> int | None:
    """Read an integer from a cgroup file; return None on any failure.

    cgroup-v2 files hold a single integer or the literal "max". We treat
    "max" as None (unbounded) so callers can distinguish "no limit" from
    "limit is N".
    """
    try:
        with open(path, "r") as f:
            v = f.read().strip()
    except OSError:
        return None
    if v == "max":
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _read_cgroup_pressure() -> dict:
    """Snapshot pids/memory usage vs limits from cgroup v2.

    Returns a dict with (current, max) for each resource. The backend
    reaper treats current/max >= _COOKED_THRESHOLD as "cooked" and evicts.
    If the cgroup files aren't readable (older kernel, non-cgroup-v2, or
    permission wall) we return nulls rather than guessing — the backend
    then falls back to pure reachability probing.
    """
    return {
        "pids": {
            "current": _read_int_file(CGROUP_PIDS_CURRENT),
            "max": _read_int_file(CGROUP_PIDS_MAX),
        },
        "memory": {
            "current": _read_int_file(CGROUP_MEM_CURRENT),
            "max": _read_int_file(CGROUP_MEM_MAX),
        },
    }


def _is_cooked(pressure: dict) -> bool:
    """True iff any tracked resource is above _COOKED_THRESHOLD of its limit."""
    for key in ("pids", "memory"):
        entry = pressure.get(key) or {}
        cur = entry.get("current")
        mx = entry.get("max")
        if not isinstance(cur, int) or not isinstance(mx, int) or mx <= 0:
            continue
        if cur / mx >= _COOKED_THRESHOLD:
            return True
    return False


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

    # 2) Wipe /tmp between calls. /home/codeuser is intentionally NOT
    # wiped: runtimes (Go, npm, pip) keep their compile/module caches
    # there and resetting them would turn every call into a cold
    # build. Cross-call state isolation is about processes (handled by
    # the pkill above) and scratch files (/tmp); /home is already a
    # fresh tmpfs at container start, so any persistence is bounded
    # by the idle-TTL restart anyway.
    try:
        for name in os.listdir("/tmp"):
            path = os.path.join("/tmp", name)
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


class WorkerCookedError(Exception):
    """Container-level resource exhaustion surfaced up to the HTTP handler.

    Raised when Popen or the tempfile write fails with EAGAIN/ENOMEM/ENOSPC
    — i.e. the kernel is refusing to spawn a subprocess or allocate memory
    because the container's cgroup limits are saturated. The handler maps
    this to HTTP 503 with cooked=true so the backend evicts us.
    """

    def __init__(self, message: str, origin: str) -> None:
        super().__init__(message)
        self.origin = origin


def _run_code(code: str, env: dict, timeout_ms: int) -> dict:
    """Write code to a temp file and exec it via RUN_CMD_TEMPLATE.

    Raises WorkerCookedError if the container is resource-exhausted.
    """
    timeout_s = max(0.001, timeout_ms / 1000.0)
    fname: str | None = None
    # Use /tmp inside the container (tmpfs-friendly, always writable).
    # A disk bomb that fills the tmpfs will cause this write to ENOSPC;
    # treat that as cooked so the backend recycles the container.
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=FILE_EXT, delete=False, dir="/tmp", encoding="utf-8"
        ) as f:
            f.write(code)
            fname = f.name
    except OSError as e:
        if e.errno in _COOKED_ERRNOS:
            raise WorkerCookedError(
                f"tempfile write failed (errno={e.errno} {os.strerror(e.errno)})",
                origin="tempfile",
            ) from e
        raise

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
        try:
            proc = subprocess.Popen(
                _build_command(fname),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=proc_env,
                cwd="/tmp",
                start_new_session=True,
            )
        except OSError as e:
            # EAGAIN/ENOMEM on fork/exec means the cgroup is saturated.
            # Don't bother trying again; the backend will evict and
            # rebuild. We raise through to the handler.
            if e.errno in _COOKED_ERRNOS:
                raise WorkerCookedError(
                    f"Popen failed (errno={e.errno} {os.strerror(e.errno)})",
                    origin="popen",
                ) from e
            raise
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
        if fname is not None:
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
            # /health is unauthenticated: it's the reachability probe the
            # backend uses when it can't afford a round-trip token check
            # (cold start, reaper sweep). Cgroup numbers are not secrets.
            pressure = _read_cgroup_pressure()
            self._json(200, {
                "status": "ok",
                "cooked": _is_cooked(pressure),
                "pids": pressure["pids"],
                "memory": pressure["memory"],
            })
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

        try:
            result = _run_code(code, env, timeout_ms)
        except WorkerCookedError as e:
            # Don't even try to recover — cooked containers cannot
            # reliably fork. Tell the backend explicitly so it evicts
            # instead of retrying.
            self._json(503, {
                "error": str(e),
                "cooked": True,
                "origin": e.origin,
            })
            return
        # Post-exec pressure check. The 503/cooked path above only fires
        # when OUR Popen hits EAGAIN — i.e. pids.max is saturated at the
        # moment we try to spawn. A subtler failure mode leaves Popen
        # succeeding (the Python subprocess machinery forks exactly
        # once) but the user process's downstream forks thrash against
        # the cgroup limit: bash prints `fork: retry: Resource
        # temporarily unavailable`, the call times out, we return 200
        # with timed_out=true. The container is still cooked — zombies
        # pin pids.current, orphaned shells hold file descriptors — and
        # the next call will fail the same way. Piggyback on the
        # already-paid /exec round-trip to tell the backend to evict.
        pressure = _read_cgroup_pressure()
        if _is_cooked(pressure):
            result = dict(result)
            result["cooked"] = True
            result["pressure"] = pressure
        self._json(200, result)


def _ensure_runtime_dirs() -> None:
    """Recreate directories runtimes expect under $HOME.

    The Dockerfile `mkdir`s these at build time, but we mount
    /home/codeuser as a fresh tmpfs at `docker run` — the tmpfs
    replaces the image's home contents with an empty filesystem, so
    `GOCACHE`/`GOPATH`/`GOTMPDIR` vanish on every container start.
    Recreate anything pointed to by a well-known env var here, before
    user code tries to use it.
    """
    candidates = [
        os.environ.get("GOCACHE"),
        os.environ.get("GOPATH"),
        os.environ.get("GOTMPDIR"),
        os.environ.get("npm_config_cache"),
        os.environ.get("PIP_CACHE_DIR"),
    ]
    for d in candidates:
        if not d:
            continue
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            print(f"[supakiln-worker] could not create {d}: {e}", flush=True)


def main() -> None:
    _ensure_runtime_dirs()
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
