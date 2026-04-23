import subprocess
import os
import json
import time
import hashlib
import threading
import base64
import docker
import random
import logging
import requests
from time import perf_counter
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from urllib.parse import urlparse
from services.docker_client import docker_client
from languages import get as get_runtime
from languages.base import Runtime, build_package_install_snippet

logger = logging.getLogger(__name__)

# Label used to identify containers managed by this app
APP_LABEL = "managed-by=supakiln"

# Default tmpfs size for the worker container's /tmp. Caps how much
# scratch space user code can consume inside a single container.
DEFAULT_TMPFS_SIZE = os.environ.get("SUPAKILN_CONTAINER_TMPFS_SIZE", "128m")


class WorkerUnreachableError(Exception):
    """Raised when the worker container's HTTP endpoint is unreachable.

    Distinct from errors in user code (non-zero exit / stderr / timeouts):
    those are returned as normal results. This is for "the worker process
    itself isn't there anymore" — we should evict the cache and recreate.
    """


def _worker_host_from_env() -> str:
    """Resolve the hostname the backend uses to reach user-container published ports.

    In the docker-compose/dind setup, published ports bind on the dind
    daemon's host (the `docker-daemon` service). If DOCKER_HOST is a TCP
    URL, its hostname is that. Otherwise (host docker socket), user
    containers publish to localhost.
    """
    override = os.environ.get("SUPAKILN_WORKER_HOST")
    if override:
        return override
    docker_host = os.environ.get("DOCKER_HOST", "")
    if docker_host.startswith("tcp://"):
        parsed = urlparse(docker_host)
        return parsed.hostname or "localhost"
    return "localhost"


class CodeExecutor:
    def __init__(self, image_name: str = "python-executor"):
        # Legacy image name retained for the web-service execution path,
        # which still uses the pre-existing `python-executor:*` images.
        self.image_name = image_name
        # Legacy cache: package_hash -> container_id (used by web services
        # and debug endpoints). Kept for backwards compatibility.
        self.containers: Dict[str, str] = {}
        self.web_service_containers: Dict[str, Dict] = {}  # container_id -> service_info

        # Worker-path cache: "lang:package_hash" -> container_id
        self.worker_containers: Dict[str, str] = {}
        # Worker endpoints: container_id -> (host, port) to reach its HTTP API
        self.worker_endpoints: Dict[str, Tuple[str, int]] = {}
        # Per-container metadata the lifecycle API surfaces: language,
        # package_hash, cache_key, created_at, last_used. Updated on
        # creation and on every /exec call.
        self.worker_meta: Dict[str, Dict] = {}
        # HTTP session with connection pooling so each /exec POST reuses a
        # TCP connection to the worker when possible.
        self._http = requests.Session()
        self._worker_host = _worker_host_from_env()
        # Concurrency: one lock per cache_key guards cold-start so parallel
        # first-time requests for the same (language, packages) don't both
        # build+run, leaving one orphan. The guard-lock protects the dict
        # of per-key locks; per-key locks protect slow work.
        self._cache_lock_guard = threading.Lock()
        self._cache_locks: Dict[str, threading.Lock] = {}

        # Network mode configuration (defaults to 'none' for security)
        # Can be set to 'bridge' to allow network access when needed
        self.container_network_mode = os.environ.get('CONTAINER_NETWORK_MODE', 'none')
        print(f"🔒 Container network mode: {self.container_network_mode}")
        self._base_image_ready = False
        self._runtime_images_ready: Dict[str, bool] = {}
        
    def _run_docker_command(self, command: List[str], timeout: int = 30) -> Tuple[bool, str, Optional[str]]:
        """Run a Docker command and return (success, output, error)."""
        try:
            # Make sure we pass the current environment including DOCKER_HOST
            env = os.environ.copy()
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
            if result.returncode == 0:
                return True, result.stdout, None
            return False, None, result.stderr
        except subprocess.TimeoutExpired:
            return False, None, f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, None, str(e)
        
    def _ensure_base_image(self):
        """Ensure the base image exists, build it if it doesn't."""
        if self._base_image_ready:
            return
            
        try:
            docker_host = os.environ.get('DOCKER_HOST', 'default')
            print(f"Using Docker daemon at: {docker_host}")
            
            # Check if image exists
            success, _, error = self._run_docker_command(["docker", "image", "inspect", f"{self.image_name}:base"])
            if not success:
                print("Building base image...")
                success, output, error = self._run_docker_command([
                    "docker", "build",
                    "-t", f"{self.image_name}:base",
                    "-f", "Dockerfile",
                    "."
                ])
                if not success:
                    raise Exception(f"Failed to build base image: {error}")
                print("Base image built successfully")
            
            self._base_image_ready = True
        except Exception as e:
            print(f"Error ensuring base image: {e}")
            raise
        
    def _get_package_hash(self, packages: List[str]) -> str:
        """Generate a valid Docker tag for a list of packages."""
        sorted_packages = sorted(packages)
        package_str = "-".join(sorted_packages)
        hash_obj = hashlib.md5(package_str.encode())
        return hash_obj.hexdigest()[:12]
    

    def _allocate_port(self) -> int:
        """Allocate a random available port between 9000-9999."""
        for _ in range(100):  # Try up to 100 times
            port = random.randint(9000, 9999)
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    return port
            except OSError:
                continue
        raise Exception("No available ports in range 9000-9999")
    
    def _detect_web_service(self, code: str, packages: List[str]) -> Optional[Dict]:
        """Detect if code contains a web service and return service info with dynamic port."""
        code_lower = code.lower()
        
        # Allocate a dynamic internal port for this service
        internal_port = self._allocate_port()
        
        # Gradio detection
        if 'gradio' in packages:
            return {
                'type': 'gradio',
                'internal_port': internal_port,
                'start_command': 'cd /tmp && python app.py'
            }
        
        # FastAPI detection
        if 'fastapi' in packages or 'uvicorn' in packages:
            return {
                'type': 'fastapi', 
                'internal_port': internal_port,
                'start_command': f'cd /tmp && python -c "import sys; sys.path.insert(0, \\"/tmp\\"); from app import app; import uvicorn; uvicorn.run(app, host=\\"0.0.0.0\\", port={internal_port})"'
            }
        
        # Flask detection
        if 'flask' in packages:
            return {
                'type': 'flask',
                'internal_port': internal_port, 
                'start_command': f'cd /tmp && python -c "import sys; sys.path.insert(0, \\"/tmp\\"); from app import app; app.run(host=\\"0.0.0.0\\", port={internal_port}, debug=True)"'
            }
        
        # Dash detection
        if 'dash' in packages:
            return {
                'type': 'dash',
                'internal_port': internal_port,
                'start_command': f'cd /tmp && python -c "import sys; sys.path.insert(0, \\"/tmp\\"); from app import app; app.run(host=\\"0.0.0.0\\", port={internal_port}, debug=True)"'
            }
        
        return None
    
    def _build_image(self, packages: List[str]) -> str:
        """Build a Docker image with the specified packages."""
        # Ensure base image exists first
        self._ensure_base_image()
        
        package_hash = self._get_package_hash(packages)
        image_tag = f"{self.image_name}:{package_hash}"
        
        # Check if image already exists
        success, _, _ = self._run_docker_command(["docker", "image", "inspect", image_tag])
        if success:
            return image_tag
        
        print(f"Building image {image_tag} with packages {packages}")
        
        # If no packages to install, just use the base image
        if not packages:
            return f"{self.image_name}:base"
            
        # Create temporary Dockerfile with better error handling
        dockerfile_content = f"""
FROM {self.image_name}:base

# Switch to root for package installation
USER root

# Update pip to latest version and install packages with verbose output
RUN pip install --upgrade pip && \\
    pip install --no-cache-dir --verbose {' '.join(f'"{pkg}"' for pkg in packages)}

# Switch back to non-root user
USER codeuser
"""
        
        with open("Dockerfile.temp", "w") as f:
            f.write(dockerfile_content)
        
        try:
            # Build the image with more detailed output
            success, output, error = self._run_docker_command([
                "docker", "build",
                "--no-cache",  # Don't use cache to get fresh error messages
                "-t", image_tag,
                "-f", "Dockerfile.temp",
                "."
            ], timeout=300)  # Increase timeout for package installation
            
            if not success:
                # Parse the Docker build error to extract pip installation failures
                detailed_error = self._parse_docker_build_error(error, packages)
                raise Exception(detailed_error)
        finally:
            # Clean up
            if os.path.exists("Dockerfile.temp"):
                os.remove("Dockerfile.temp")
                
        return image_tag
    
    def _parse_docker_build_error(self, docker_error: str, packages: List[str]) -> str:
        """Parse Docker build error to extract meaningful package installation errors."""
        if not docker_error:
            return "Failed to build image: Unknown error occurred during package installation"
        
        # Check for common pip installation errors
        error_lower = docker_error.lower()
        
        # Extract package-specific errors
        if "could not find a version that satisfies the requirement" in error_lower:
            # Try to extract the specific package that failed
            for package in packages:
                if package.lower() in error_lower:
                    return f"Package installation failed: Package '{package}' not found or version not available. Please check the package name and try again."
            return f"Package installation failed: One or more packages could not be found. Packages: {', '.join(packages)}"
        
        if "no matching distribution found" in error_lower:
            for package in packages:
                if package.lower() in error_lower:
                    return f"Package installation failed: No distribution found for '{package}'. The package may not exist or may not be compatible with the Python version."
            return f"Package installation failed: No distribution found for one or more packages: {', '.join(packages)}"
        
        if "error: subprocess-exited-with-error" in error_lower or "error: microsoft visual c++" in error_lower:
            return f"Package installation failed: Compilation error occurred. One or more packages require compilation but failed to build. This may be due to missing system dependencies or incompatible packages: {', '.join(packages)}"
        
        if "connectionerror" in error_lower or "timeout" in error_lower or "network" in error_lower:
            return f"Package installation failed: Network error occurred while downloading packages. Please check your internet connection and try again. Packages: {', '.join(packages)}"
        
        if "permission denied" in error_lower:
            return f"Package installation failed: Permission denied during installation. This is an internal system error."
        
        if "disk space" in error_lower or "no space" in error_lower:
            return f"Package installation failed: Insufficient disk space to install packages: {', '.join(packages)}"
        
        # Extract the last few lines of the error for more context
        error_lines = docker_error.strip().split('\n')
        # Get the last 5 non-empty lines
        relevant_lines = [line.strip() for line in error_lines if line.strip()][-5:]
        
        if relevant_lines:
            detailed_msg = '\n'.join(relevant_lines)
            return f"Package installation failed for packages: {', '.join(packages)}\n\nError details:\n{detailed_msg}"
        
        return f"Failed to build image with packages: {', '.join(packages)}\n\nFull error: {docker_error}"

    # ------------------------------------------------------------------
    # Runtime + worker path (ad-hoc execution, multi-language)
    #
    # Each supported language has its own base image (e.g.
    # `supakiln-python:base`) with a long-running HTTP worker baked in as
    # CMD. Backend talks to the worker directly over the dind bridge
    # (via published ports), bypassing `docker exec` on the hot path.
    # ------------------------------------------------------------------

    def _ensure_runtime_base_image(self, runtime: Runtime) -> None:
        """Build the runtime's base image if it isn't already present."""
        if self._runtime_images_ready.get(runtime.name):
            return
        tag = runtime.base_image_tag
        success, _, _ = self._run_docker_command(["docker", "image", "inspect", tag])
        if not success:
            print(f"Building {tag} from {runtime.dockerfile_path}...")
            success, _, error = self._run_docker_command(
                ["docker", "build", "-t", tag, "-f", runtime.dockerfile_path, "."],
                timeout=600,
            )
            if not success:
                raise Exception(f"Failed to build {tag}: {error}")
        self._runtime_images_ready[runtime.name] = True

    def _build_runtime_image(self, runtime: Runtime, packages: List[str]) -> str:
        """Return an image tag for `runtime + packages`, building if needed."""
        self._ensure_runtime_base_image(runtime)
        if not packages:
            return runtime.base_image_tag

        package_hash = self._get_package_hash(packages)
        base_name = runtime.base_image_tag.split(":", 1)[0]
        image_tag = f"{base_name}:{package_hash}"

        success, _, _ = self._run_docker_command(["docker", "image", "inspect", image_tag])
        if success:
            return image_tag

        install_snippet = build_package_install_snippet(runtime, packages)
        if not install_snippet:
            # Runtime doesn't support package installation; callers should
            # not be passing packages, but fall back to base image rather
            # than erroring.
            return runtime.base_image_tag

        dockerfile_content = (
            f"FROM {runtime.base_image_tag}\n"
            f"{install_snippet}"
        )
        tmp_path = f"Dockerfile.{runtime.name}.{package_hash}.tmp"
        with open(tmp_path, "w") as f:
            f.write(dockerfile_content)
        try:
            success, _, error = self._run_docker_command(
                ["docker", "build", "-t", image_tag, "-f", tmp_path, "."],
                timeout=600,
            )
            if not success:
                raise Exception(self._parse_docker_build_error(error, packages))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        return image_tag

    def _read_worker_port(self, container_id: str, worker_port: int) -> int:
        """Read the published host-port for the worker container."""
        container = docker_client.containers.get(container_id)
        container.reload()
        port_info = (container.attrs.get("NetworkSettings", {})
                     .get("Ports", {})
                     .get(f"{worker_port}/tcp"))
        if not port_info:
            raise Exception(f"worker port {worker_port} not published on {container_id[:12]}")
        return int(port_info[0]["HostPort"])

    def _wait_for_worker_health(self, host: str, port: int, timeout_s: float = 15.0) -> None:
        """Poll GET /health until 200 or timeout."""
        deadline = perf_counter() + timeout_s
        url = f"http://{host}:{port}/health"
        last_err: Optional[str] = None
        while perf_counter() < deadline:
            try:
                r = self._http.get(url, timeout=1.0)
                if r.status_code == 200:
                    return
                last_err = f"status={r.status_code}"
            except requests.RequestException as e:
                last_err = str(e)
            time.sleep(0.05)
        raise Exception(f"worker at {host}:{port} not healthy after {timeout_s}s ({last_err})")

    def _get_cache_lock(self, cache_key: str) -> threading.Lock:
        """Return the lock for this cache_key, creating it lazily."""
        with self._cache_lock_guard:
            lock = self._cache_locks.get(cache_key)
            if lock is None:
                lock = threading.Lock()
                self._cache_locks[cache_key] = lock
            return lock

    def _evict_worker(self, cache_key: str, container_id: Optional[str]) -> None:
        """Forget a worker and force-remove its container (best effort).

        Called when we detect the worker is unreachable or we explicitly
        want to tear it down. Must be idempotent: the container may
        already be gone.
        """
        self.worker_containers.pop(cache_key, None)
        # Only pop endpoints if this container_id still owns it; a racing
        # recreation could have updated it already.
        if container_id is not None:
            cur = self.worker_endpoints.get(container_id)
            if cur is not None:
                self.worker_endpoints.pop(container_id, None)
            self.worker_meta.pop(container_id, None)
            if self.containers.get(cache_key) == container_id:
                self.containers.pop(cache_key, None)
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_id],
                    capture_output=True, env=os.environ.copy(),
                    timeout=15,
                )
            except Exception as e:
                logger.debug("best-effort rm failed for %s: %s", container_id, e)

    def _get_or_create_worker_container(
        self,
        runtime: Runtime,
        packages: List[str],
        timings: Dict[str, float],
    ) -> Tuple[str, str, int]:
        """Return (container_id, worker_host, worker_port), creating if needed.

        Cold-start is serialized per cache_key so parallel first-time
        requests don't each build+run, leaving one orphan.
        """
        package_hash = self._get_package_hash(packages)
        cache_key = f"{runtime.name}:{package_hash}"

        # Fast path: cache hit without acquiring the per-key lock.
        if cache_key in self.worker_containers:
            container_id = self.worker_containers[cache_key]
            host, port = self.worker_endpoints[container_id]
            timings['container_cache_hit'] = 1.0
            return container_id, host, port

        lock = self._get_cache_lock(cache_key)
        with lock:
            # Double-check: another thread may have populated the cache
            # while we were waiting for the lock.
            if cache_key in self.worker_containers:
                container_id = self.worker_containers[cache_key]
                host, port = self.worker_endpoints[container_id]
                timings['container_cache_hit'] = 1.0
                return container_id, host, port

            timings['container_cache_hit'] = 0.0
            t_build = perf_counter()
            image_tag = self._build_runtime_image(runtime, packages)
            timings['build_image_ms'] = (perf_counter() - t_build) * 1000

            t_run = perf_counter()
            success, output, error = self._run_docker_command([
                "docker", "run",
                "-d",
                "--label", APP_LABEL,
                "--memory", "512m",
                "--cpus", "0.5",
                "--network", "bridge",  # worker needs network; dind bridge only
                "--user", "1000:1000",
                "--cap-drop", "ALL",
                "--pids-limit", "100",
                # Tmpfs for /tmp so user code can't indefinitely grow the
                # container's writable layer. 128m is enough for realistic
                # scratch work; override with SUPAKILN_CONTAINER_TMPFS_SIZE.
                "--tmpfs", f"/tmp:size={DEFAULT_TMPFS_SIZE},mode=1777",
                "-p", str(runtime.worker_port),  # publish to random host port on dind
                image_tag,
            ])
            timings['docker_run_ms'] = (perf_counter() - t_run) * 1000
            if not success:
                raise Exception(f"Failed to create worker container: {error}")
            container_id = output.strip()

            try:
                t_port = perf_counter()
                host_port = self._read_worker_port(container_id, runtime.worker_port)
                timings['read_port_ms'] = (perf_counter() - t_port) * 1000

                host = self._worker_host
                t_health = perf_counter()
                self._wait_for_worker_health(host, host_port)
                timings['worker_health_ms'] = (perf_counter() - t_health) * 1000
            except Exception:
                # If we couldn't bring the worker up, don't leave the
                # container running as an orphan.
                try:
                    subprocess.run(
                        ["docker", "rm", "-f", container_id],
                        capture_output=True, env=os.environ.copy(), timeout=15,
                    )
                except Exception:
                    pass
                raise

            self.worker_containers[cache_key] = container_id
            self.worker_endpoints[container_id] = (host, host_port)
            now = time.time()
            self.worker_meta[container_id] = {
                "language": runtime.name,
                "package_hash": package_hash,
                "cache_key": cache_key,
                "created_at": now,
                "last_used": now,
            }
            # Also register in the legacy `containers` dict so existing code
            # (debug endpoints, container_id lookups) still works.
            self.containers[cache_key] = container_id
            return container_id, host, host_port

    def _exec_via_worker(
        self,
        host: str,
        port: int,
        code: str,
        env_vars: Dict[str, str],
        timeout_ms: int,
    ) -> Tuple[bool, Optional[str], Optional[str], bool]:
        """POST code to the worker; return (success, stdout, stderr, timed_out).

        Raises WorkerUnreachableError if the worker HTTP endpoint can't be
        reached at all — the caller should evict cache and retry. Does NOT
        raise for user-code failures (non-zero exit, stderr, timed_out);
        those come back as normal return values.
        """
        url = f"http://{host}:{port}/exec"
        # Worker enforces timeout on its side; we give the HTTP client a
        # small slack buffer so the server can surface a timed_out=True
        # response rather than us hanging up.
        http_timeout = max(1.0, timeout_ms / 1000.0 + 5.0)
        try:
            r = self._http.post(
                url,
                json={"code": code, "env": env_vars or {}, "timeout_ms": timeout_ms},
                timeout=http_timeout,
            )
        except requests.ConnectionError as e:
            # Worker is gone (container died, daemon restarted, TCP reset).
            raise WorkerUnreachableError(f"worker connection failed: {e}") from e
        except requests.Timeout:
            # User's code or the worker hung. This can be either "user
            # code took too long" or "worker stuck"; treat the latter as
            # a user-visible timeout rather than an unreachable marker,
            # because the container is usually still alive.
            return False, None, "worker HTTP request timed out", True
        except requests.RequestException as e:
            return False, None, f"worker request failed: {e}", False

        if r.status_code >= 500:
            # Server-side error from the worker; the process may be in a
            # bad state. Treat as unreachable so the caller recreates.
            raise WorkerUnreachableError(
                f"worker returned status {r.status_code}: {r.text[:200]}"
            )
        if r.status_code != 200:
            return False, None, f"worker returned status {r.status_code}: {r.text}", False
        try:
            body = r.json()
        except ValueError:
            return False, None, f"worker returned non-JSON: {r.text[:200]}", False
        success = body.get("exit_code") == 0 and not body.get("timed_out", False)
        return (
            success,
            body.get("stdout"),
            body.get("stderr"),
            bool(body.get("timed_out", False)),
        )

    def _execute_with_timeout(self, container_id: str, command: str, timeout: int) -> Tuple[bool, str, Optional[str]]:
        """Execute a command in a container with timeout."""
        try:
            # Make sure we pass the current environment including DOCKER_HOST
            env = os.environ.copy()
            result = subprocess.run(
                ["docker", "exec", container_id, "sh", "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
            if result.returncode == 0:
                return True, result.stdout, None
            return False, None, result.stderr
        except subprocess.TimeoutExpired:
            # Kill and remove the container
            env = os.environ.copy()
            subprocess.run(["docker", "kill", container_id], capture_output=True, env=env)
            subprocess.run(["docker", "rm", container_id], capture_output=True, env=env)
            # Remove from our tracking
            for package_hash, cid in list(self.containers.items()):
                if cid == container_id:
                    del self.containers[package_hash]
            return False, None, f"Execution timed out after {timeout} seconds"
        except Exception as e:
            return False, None, str(e)
    
    def _execute_with_streaming_timeout(self, container_id: str, command: str, timeout: int) -> Tuple[bool, str, Optional[str], bool]:
        """Execute a command in a container with streaming output and timeout handling."""
        import threading
        import docker
        
        output_buffer = []
        error_buffer = []
        success = False
        timed_out = False
        
        def collect_output():
            nonlocal success, timed_out
            try:
                container = docker_client.containers.get(container_id)
                # Execute without streaming to get proper exit code
                # Need to execute the command in a shell to handle pipes properly
                result = container.exec_run(
                    ["sh", "-c", command],
                    stream=False,  # Don't stream to get proper exit code
                    demux=True     # Separate stdout and stderr
                )
                
                # Process the output
                if result.output:
                    stdout_data, stderr_data = result.output
                    if stdout_data:
                        output_buffer.append(stdout_data.decode('utf-8', errors='replace'))
                    if stderr_data:
                        error_buffer.append(stderr_data.decode('utf-8', errors='replace'))
                
                # Now we can reliably check the exit code
                success = result.exit_code == 0
                
            except Exception as e:
                error_buffer.append(f"Execution error: {str(e)}")
                success = False
        
        # Start output collection in a separate thread
        output_thread = threading.Thread(target=collect_output)
        output_thread.daemon = True
        output_thread.start()
        
        # Wait for completion or timeout
        output_thread.join(timeout)
        
        if output_thread.is_alive():
            # Thread is still running, so we timed out
            timed_out = True
            # Try to stop the execution in the container
            try:
                container = docker_client.containers.get(container_id)
                # Kill the process in the container
                container.exec_run("pkill -f python", detach=True)
            except:
                pass
            
            # Give it a moment to clean up
            output_thread.join(1)
        
        # Combine output
        combined_output = ''.join(output_buffer) if output_buffer else None
        combined_error = ''.join(error_buffer) if error_buffer else None
        
        # If we timed out, add timeout message
        if timed_out:
            timeout_msg = f"\n--- Execution timed out after {timeout} seconds ---"
            if combined_output:
                combined_output += timeout_msg
            elif combined_error:
                combined_error += timeout_msg
            else:
                combined_error = f"Execution timed out after {timeout} seconds"
        
        return success and not timed_out, combined_output, combined_error, timed_out
    
    def _execute_with_streaming_timeout_and_env(self, container_id: str, encoded_code: str, timeout: int, env_vars: Dict[str, str], timings: Optional[Dict[str, float]] = None) -> Tuple[bool, str, Optional[str], bool]:
        """Execute code in a container with environment variables injected at execution time."""
        import threading
        import docker

        output_buffer = []
        error_buffer = []
        success = False
        timed_out = False
        # Shared timings dict so we can measure phases inside the worker thread
        t = timings if timings is not None else {}

        def collect_output():
            nonlocal success, timed_out
            try:
                t_get = perf_counter()
                container = docker_client.containers.get(container_id)
                t['containers_get_ms'] = (perf_counter() - t_get) * 1000
                # Execute with environment variables injected at execution time
                t_exec = perf_counter()
                result = container.exec_run(
                    f"python3 -c 'import base64; exec(base64.b64decode(\"{encoded_code}\").decode())'",
                    environment=env_vars,  # Inject environment variables here
                    stream=False,  # Don't stream to get proper exit code
                    demux=True     # Separate stdout and stderr
                )
                t['exec_run_ms'] = (perf_counter() - t_exec) * 1000
                
                # Process the output
                if result.output:
                    stdout_data, stderr_data = result.output
                    if stdout_data:
                        output_buffer.append(stdout_data.decode('utf-8', errors='replace'))
                    if stderr_data:
                        error_buffer.append(stderr_data.decode('utf-8', errors='replace'))
                
                # Check the exit code
                success = result.exit_code == 0
                
            except Exception as e:
                error_buffer.append(f"Execution error: {str(e)}")
                success = False
        
        # Start output collection in a separate thread
        output_thread = threading.Thread(target=collect_output)
        output_thread.daemon = True
        output_thread.start()
        
        # Wait for completion or timeout
        output_thread.join(timeout)
        
        if output_thread.is_alive():
            # Thread is still running, so we timed out
            timed_out = True
            # Try to stop the execution in the container
            try:
                container = docker_client.containers.get(container_id)
                # Kill the process in the container
                container.exec_run("pkill -f python", detach=True)
            except:
                pass
            
            # Give it a moment to clean up
            output_thread.join(1)
        
        # Combine output
        combined_output = ''.join(output_buffer) if output_buffer else None
        combined_error = ''.join(error_buffer) if error_buffer else None
        
        # If we timed out, add timeout message
        if timed_out:
            timeout_msg = f"\n--- Execution timed out after {timeout} seconds ---"
            if combined_output:
                combined_output += timeout_msg
            elif combined_error:
                combined_error += timeout_msg
            else:
                combined_error = f"Execution timed out after {timeout} seconds"
        
        return success and not timed_out, combined_output, combined_error, timed_out
    
    def execute_code(
        self,
        code: str,
        packages: List[str],
        timeout: int = 30,
        env_vars: Dict[str, str] = None,
        language: str = "python",
    ) -> Dict:
        """
        Execute code in a container with the specified packages.

        Args:
            code: Source code to execute
            packages: List of required packages (interpretation depends on language)
            timeout: Maximum execution time in seconds
            env_vars: Dictionary of environment variables to pass to the container
            language: Runtime to use (default "python"). Must be registered
                      in the `languages` module.

        Returns:
            Dict containing execution results
        """
        t_start = perf_counter()
        timings: Dict[str, float] = {}

        if env_vars is None:
            env_vars = {}

        t_hash = perf_counter()
        package_hash = self._get_package_hash(packages)
        timings['package_hash_ms'] = (perf_counter() - t_hash) * 1000

        # Web-service detection only applies to Python (Streamlit/FastAPI/
        # Flask/Dash/Gradio). Non-Python languages always take the ad-hoc
        # worker path.
        web_service = None
        if language == "python":
            t_detect = perf_counter()
            web_service = self._detect_web_service(code, packages)
            timings['detect_web_service_ms'] = (perf_counter() - t_detect) * 1000
        
        # For web services, always create a new container
        # For regular code, use package hash to potentially reuse containers
        if web_service:
            # Create a unique container for each web service
            image_tag = self._build_image(packages)
            
            # Allocate external port
            external_port = self._allocate_port()
            port_mapping = f"{external_port}:{web_service['internal_port']}"
            
            # Use bridge network since we're in Docker-in-Docker sidecar
            network_options = ["--network", "bridge"]
            print("✅ Using bridge network (Docker-in-Docker environment)")
            
            # Note: Web services will be accessible via Docker host port mapping
            
            # Build environment variable options for docker run
            env_options = []
            for key, value in env_vars.items():
                env_options.extend(["-e", f"{key}={value}"])
            
            success, output, error = self._run_docker_command([
                "docker", "run",
                "-d",
                "-p", port_mapping,
                "--label", APP_LABEL,
                "--memory", "512m",
                "--cpus", "0.5",
                "--user", "1000:1000",
                "--cap-drop", "ALL",
                "--pids-limit", "100"  # Limit number of processes (keep reasonable limit)
            ] + network_options + env_options + [
                image_tag,
                "tail", "-f", "/dev/null"
            ])
            
            if not success:
                return {
                    "success": False,
                    "output": None,
                    "error": f"Failed to create container: {error}"
                }
            
            container_id = output.strip()
            
            # Store web service info
            self.web_service_containers[container_id] = {
                'type': web_service['type'],
                'internal_port': web_service['internal_port'],
                'external_port': external_port,
                'start_command': web_service['start_command']
            }
            
            # For web services, save code to file and start the service
            encoded_code = base64.b64encode(code.encode()).decode()
            
            # Save code to app.py in container
            save_command = f"echo '{encoded_code}' | base64 -d > /tmp/app.py"
            success, output, error = self._execute_with_timeout(container_id, save_command, 10)
            
            if not success:
                return {
                    "success": False,
                    "output": None,
                    "error": f"Failed to save code: {error}"
                }
            
            # Start the web service (non-blocking)
            service_info = self.web_service_containers[container_id]
            
            print(f"🚀 Starting {service_info['type']} service in container {container_id[:8]}")
            print(f"📝 Command: {service_info['start_command']}")
            print(f"🌐 Internal port: {service_info['internal_port']} -> External port: {service_info['external_port']}")
            
            # First, validate the app.py file
            validate_command = "python -m py_compile /tmp/app.py"
            validate_success, validate_output, validate_error = self._execute_with_timeout(container_id, validate_command, 5)
            
            if not validate_success:
                print(f"❌ App validation failed: {validate_error}")
            else:
                print(f"✅ App validation passed")
            
            # Check if required packages are available
            if service_info['type'] == 'gradio':
                pkg_check = "python -c 'import gradio as gr; print(f\"Gradio version: {gr.__version__}\")'"
            elif service_info['type'] == 'flask':
                pkg_check = "python -c 'import flask; print(f\"Flask version: {flask.__version__}\")'"
            elif service_info['type'] == 'fastapi':
                pkg_check = "python -c 'import fastapi, uvicorn; print(f\"FastAPI: {fastapi.__version__}, Uvicorn: {uvicorn.__version__}\")'"
            elif service_info['type'] == 'dash':
                pkg_check = "python -c 'import dash; print(f\"Dash version: {dash.__version__}\")'"
            else:
                pkg_check = "echo 'Unknown service type'"
                
            pkg_success, pkg_output, pkg_error = self._execute_with_timeout(container_id, pkg_check, 5)
            print(f"📦 Package check: {pkg_output if pkg_success else pkg_error}")
            
            # Start the service in background using Docker exec -d (detached)
            if service_info['type'] == 'gradio':
                # Create wrapper script that forces Gradio to use allocated port
                gradio_wrapper = f'''#!/usr/bin/env python
import os
import sys

# Set environment variables before importing gradio
os.environ["GRADIO_SERVER_NAME"] = "0.0.0.0"
os.environ["GRADIO_SERVER_PORT"] = "{service_info['internal_port']}"

# Import gradio and patch launch methods
import gradio as gr

# Store original launch method
_original_launch = gr.blocks.Blocks.launch

def patched_launch(self, *args, **kwargs):
    # Override any user-specified server settings
    kwargs["server_name"] = "0.0.0.0"
    kwargs["server_port"] = {service_info['internal_port']}
    print(f"[GradioWrapper] Forcing launch on 0.0.0.0:{service_info['internal_port']}")
    return _original_launch(self, *args, **kwargs)

# Apply patch
gr.blocks.Blocks.launch = patched_launch
gr.Interface.launch = patched_launch

# Now run the user's app
sys.path.insert(0, '/tmp')
exec(open('/tmp/app.py').read())
'''
                
                service_start_script = f'''#!/bin/bash
cd /tmp
export PYTHONPATH=/tmp:$PYTHONPATH
export GRADIO_SERVER_NAME="0.0.0.0"
export GRADIO_SERVER_PORT="{service_info['internal_port']}"

# Create the wrapper script
cat > /tmp/gradio_wrapper.py << 'WRAPPER_EOF'
{gradio_wrapper}
WRAPPER_EOF

# Run the wrapper
python /tmp/gradio_wrapper.py > /tmp/service.log 2>&1
'''
            elif service_info['type'] == 'dash':
                # For Dash, we need to modify the app creation to include url_base_pathname
                container_short_id = container_id[:8]
                proxy_path = f"/proxy/{container_short_id}/"
                
                # Create a script that modifies the original app.py to include proxy configuration
                dash_patcher = '''#!/usr/bin/env python
import sys
import re

# Read the original app.py
with open('/tmp/app.py', 'r') as f:
    original_code = f.read()

proxy_path = "''' + proxy_path + '''"
proxy_params = 'url_base_pathname="' + proxy_path + '"'

# Simple replacement approach
modified_code = original_code

# Replace dash.Dash(...) patterns
patterns = [
    (r'app\\s*=\\s*dash\\.Dash\\s*\\(\\s*\\)', 'app = dash.Dash(' + proxy_params + ')'),
    (r'app\\s*=\\s*dash\\.Dash\\s*\\(([^)]+)\\)', lambda m: 'app = dash.Dash(' + m.group(1).rstrip(', ') + ', ' + proxy_params + ')'),
    (r'app\\s*=\\s*Dash\\s*\\(\\s*\\)', 'app = Dash(' + proxy_params + ')'),
    (r'app\\s*=\\s*Dash\\s*\\(([^)]+)\\)', lambda m: 'app = Dash(' + m.group(1).rstrip(', ') + ', ' + proxy_params + ')')
]

for pattern, replacement in patterns:
    if callable(replacement):
        modified_code = re.sub(pattern, replacement, modified_code)
    else:
        modified_code = re.sub(pattern, replacement, modified_code)

# Also fix the app.run() call to use the correct port
internal_port = ''' + str(service_info["internal_port"]) + '''

# First, check if there's already a port argument and replace it
if re.search(r'app\\.run\\s*\\([^)]*port\\s*=\\s*\\d+', modified_code):
    # Replace existing port argument
    modified_code = re.sub(r'(app\\.run\\s*\\([^)]*)port\\s*=\\s*\\d+([^)]*\\))', 
                          lambda m: m.group(1) + 'port=' + str(internal_port) + m.group(2), 
                          modified_code)
else:
    # Add port argument if it doesn't exist
    modified_code = re.sub(r'app\\.run\\s*\\(([^)]*)\\)', 
                          lambda m: 'app.run(' + (m.group(1).rstrip(', ') + ', ' if m.group(1).strip() else '') + 'port=' + str(internal_port) + ')', 
                          modified_code)

# Write the modified code
with open('/tmp/app_proxy.py', 'w') as f:
    f.write(modified_code)

print("✅ Modified Dash app for proxy usage")
print("✅ Proxy path: " + proxy_path)
'''
                
                patcher_script = f"echo '{base64.b64encode(dash_patcher.encode()).decode()}' | base64 -d > /tmp/patch_app.py"
                
                service_start_script = f'''#!/bin/bash
cd /tmp
export PYTHONPATH=/tmp:$PYTHONPATH
{patcher_script}
python /tmp/patch_app.py
if [ -f /tmp/app_proxy.py ]; then
    echo "🚀 Starting patched Dash app..."
    python -c "import sys; sys.path.insert(0, '/tmp'); exec(open('/tmp/app_proxy.py').read())" > /tmp/service.log 2>&1
else
    echo "❌ Failed to create patched app, using original..."
    python -c "import sys; sys.path.insert(0, '/tmp'); from app import app; app.run(host='0.0.0.0', port={service_info["internal_port"]}, debug=True)" > /tmp/service.log 2>&1
fi
'''
            else:
                service_start_script = f'''#!/bin/bash
cd /tmp
export PYTHONPATH=/tmp:$PYTHONPATH
{service_info['start_command']} > /tmp/service.log 2>&1
'''
            
            # Create the startup script
            script_command = f"echo '{base64.b64encode(service_start_script.encode()).decode()}' | base64 -d > /tmp/start_service.sh && chmod +x /tmp/start_service.sh"
            success, output, error = self._execute_with_timeout(container_id, script_command, 10)
            
            if not success:
                print(f"❌ Failed to create startup script: {error}")
            else:
                print(f"✅ Startup script created")
            
            # Start the service using Docker exec -d (detached mode)
            try:
                env = os.environ.copy()
                result = subprocess.run([
                    "docker", "exec", "-d", container_id, "/tmp/start_service.sh"
                ], capture_output=True, text=True, timeout=10, env=env)
                
                if result.returncode == 0:
                    print(f"✅ Service started in detached mode")
                    success = True
                else:
                    print(f"❌ Failed to start service: {result.stderr}")
                    success = False
                    error = result.stderr
            except Exception as e:
                print(f"❌ Exception starting service: {e}")
                success = False
                error = str(e)
            
            # Give the service more time to start fully
            print("⏳ Waiting for service to initialize...")
            time.sleep(8)
            
            # Check if service started successfully by looking at the log
            log_check_command = "tail -n 30 /tmp/service.log 2>/dev/null || echo 'Log not found'"
            log_success, log_output, _ = self._execute_with_timeout(container_id, log_check_command, 5)
            
            # Check if service is actually running by checking the process
            process_check_command = f"ps aux | grep -E '(gradio|uvicorn|flask|python.*start_service)' | grep -v grep || echo 'No service process found'"
            process_success, process_output, _ = self._execute_with_timeout(container_id, process_check_command, 5)
            
            # Check if the service port is listening
            port_check_command = f"netstat -tlnp | grep :{service_info['internal_port']} || ss -tlnp | grep :{service_info['internal_port']} || echo 'Port not listening'"
            port_success, port_output, _ = self._execute_with_timeout(container_id, port_check_command, 5)
            
            print(f"🔍 Service process check: {process_output}")
            print(f"🔍 Port check: {port_output}")
            print(f"🔍 Service logs: {log_output}")
            
            # Get backend URL for proxy
            backend_url = os.environ.get('VITE_API_URL', os.environ.get('BACKEND_URL', 'http://localhost:8000'))
            proxy_url = f"{backend_url}/proxy/{container_id[:8]}"
            
            # Check if service startup was successful
            if not success:
                return {
                    "success": False,
                    "output": None,
                    "error": f"Failed to start {service_info['type']} service: {error}",
                    "container_id": container_id
                }
            
            # Create success message with service logs
            output_message = f"🚀 {service_info['type'].title()} service started!\n\n📍 Access your app at: {proxy_url}\n\nService is running on port {service_info['external_port']} (internal: {service_info['internal_port']})"
            
            if log_success and log_output and 'Log not found' not in log_output:
                output_message += f"\n\n--- Service Startup Log ---\n{log_output}"
            
            return {
                "success": True,
                "output": output_message,
                "error": None,
                "container_id": container_id,
                "web_service": {
                    "type": service_info['type'],
                    "external_port": service_info['external_port'],
                    "proxy_url": proxy_url
                }
            }
        else:
            # Ad-hoc code execution via the per-language worker. Containers
            # are cached per (language, package_hash) so subsequent runs
            # against the same environment reuse the live worker.
            try:
                runtime = get_runtime(language)
            except KeyError as e:
                timings['total_ms'] = (perf_counter() - t_start) * 1000
                return {
                    "success": False,
                    "output": None,
                    "error": str(e),
                    "timings_ms": timings,
                }

            package_hash = self._get_package_hash(packages)
            cache_key = f"{runtime.name}:{package_hash}"

            # We allow one automatic retry if the cached worker turns out
            # to be dead — that's the self-heal path. A second consecutive
            # unreachable worker is reported to the caller.
            last_unreachable: Optional[WorkerUnreachableError] = None
            container_id: Optional[str] = None
            for attempt in range(2):
                try:
                    container_id, host, port = self._get_or_create_worker_container(
                        runtime, packages, timings,
                    )
                except Exception as e:
                    timings['total_ms'] = (perf_counter() - t_start) * 1000
                    return {
                        "success": False,
                        "output": None,
                        "error": f"Failed to prepare worker container: {e}",
                        "timings_ms": timings,
                    }

                t_exec = perf_counter()
                try:
                    success, stdout, stderr, timed_out = self._exec_via_worker(
                        host, port, code, env_vars, timeout_ms=int(timeout * 1000),
                    )
                    timings['worker_exec_ms'] = (perf_counter() - t_exec) * 1000
                    if attempt == 1:
                        timings['self_heal_recovered'] = 1.0
                    # Record liveness for lifecycle + idle reaper.
                    meta = self.worker_meta.get(container_id)
                    if meta is not None:
                        meta["last_used"] = time.time()
                    break
                except WorkerUnreachableError as e:
                    last_unreachable = e
                    timings['worker_exec_ms'] = (perf_counter() - t_exec) * 1000
                    timings[f'self_heal_attempt_{attempt}'] = 1.0
                    # Evict the dead worker. Next iteration rebuilds.
                    self._evict_worker(cache_key, container_id)
                    container_id = None
            else:
                # Both attempts failed — worker couldn't be reached even
                # after recreating. Surface a clear error.
                timings['total_ms'] = (perf_counter() - t_start) * 1000
                return {
                    "success": False,
                    "output": None,
                    "error": f"Worker unreachable after retry: {last_unreachable}",
                    "container_id": None,
                    "timed_out": False,
                    "timings_ms": timings,
                }

            timings['total_ms'] = (perf_counter() - t_start) * 1000
            output = stdout if stdout else None
            # Preserve existing contract: stderr is returned as `error` iff
            # the process actually failed (non-zero exit or timeout); a
            # successful run with stderr chatter still reports success.
            error = stderr if (not success or timed_out) and stderr else None
            return {
                "success": success,
                "output": output,
                "error": error,
                "container_id": container_id,
                "timed_out": timed_out,
                "timings_ms": timings,
            }
    
    def cleanup(self):
        """Clean up all tracked containers."""
        env = os.environ.copy()
        all_ids = (
            list(self.containers.values())
            + list(self.web_service_containers.keys())
            + list(self.worker_containers.values())
        )
        for container_id in set(all_ids):
            try:
                subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, env=env)
            except Exception:
                pass
        self.containers.clear()
        self.web_service_containers.clear()
        self.worker_containers.clear()
        self.worker_endpoints.clear()
        self.worker_meta.clear()

    # ------------------------------------------------------------------
    # Lifecycle API used by the /workers router and the idle reaper.
    # ------------------------------------------------------------------

    def list_workers(self) -> List[Dict]:
        """Return a snapshot of live ad-hoc workers."""
        out: List[Dict] = []
        for container_id, meta in list(self.worker_meta.items()):
            endpoint = self.worker_endpoints.get(container_id)
            out.append({
                "container_id": container_id,
                "language": meta["language"],
                "package_hash": meta["package_hash"],
                "cache_key": meta["cache_key"],
                "created_at": meta["created_at"],
                "last_used": meta["last_used"],
                "host": endpoint[0] if endpoint else None,
                "port": endpoint[1] if endpoint else None,
            })
        # Stable order for UIs.
        out.sort(key=lambda w: (w["language"], w["created_at"]))
        return out

    def stop_worker(self, container_id: str) -> bool:
        """Force-kill one worker. Returns True if it was tracked."""
        meta = self.worker_meta.get(container_id)
        if meta is None:
            # Still try to kill the container in case it's a stale one we
            # lost track of after a backend restart.
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_id],
                    capture_output=True, env=os.environ.copy(), timeout=15,
                )
            except Exception:
                pass
            return False
        self._evict_worker(meta["cache_key"], container_id)
        return True

    def reset_workers(self) -> int:
        """Stop and forget every tracked ad-hoc worker. Returns count killed."""
        killed = 0
        for container_id in list(self.worker_meta.keys()):
            meta = self.worker_meta.get(container_id)
            if meta is None:
                continue
            self._evict_worker(meta["cache_key"], container_id)
            killed += 1
        return killed

    def reap_idle_workers(self, idle_ttl_seconds: float) -> List[str]:
        """Stop workers whose last_used is older than idle_ttl_seconds.

        Returns the list of container_ids that were reaped. idle_ttl <= 0
        disables reaping (caller should skip invoking altogether in that
        case, but we also guard here).
        """
        if idle_ttl_seconds <= 0:
            return []
        now = time.time()
        cutoff = now - idle_ttl_seconds
        reaped: List[str] = []
        for container_id, meta in list(self.worker_meta.items()):
            if meta["last_used"] < cutoff:
                self._evict_worker(meta["cache_key"], container_id)
                reaped.append(container_id)
        return reaped

    def shutdown(self):
        """Graceful shutdown: stop and remove all tracked containers."""
        logger.info("Shutting down CodeExecutor, cleaning up %d containers...",
                     len(self.containers) + len(self.web_service_containers))
        self.cleanup()
        logger.info("CodeExecutor shutdown complete")

if __name__ == "__main__":
    # Example usage
    executor = CodeExecutor()
    
    # Example code execution
    code = """
import numpy as np
arr = np.array([1, 2, 3])
print(arr.mean())
    """
    
    result = executor.execute_code(
        code=code,
        packages=["numpy"]
    )
    
    print("Execution result:", json.dumps(result, indent=2))
    
    # Cleanup
    executor.cleanup() 