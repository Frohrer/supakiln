# Container Security Guide

This guide provides comprehensive information about container security testing and hardening for the code execution environment.

## Supakiln Hardening Posture

This section documents what the codebase **actually wires** when it creates user-code containers, plus the host-level knobs that aren't under the app's control.

### Always on (no configuration needed)

Every container holding untrusted code runs with the following flags, centralised in `CodeExecutor._hardening_run_flags()`:

- `--user 1000:1000` — non-root inside the container
- `--cap-drop ALL` — no Linux capabilities retained
- `--read-only` — root filesystem is read-only
- `--security-opt no-new-privileges` — blocks setuid escalation
- `--memory=<limit>` and `--memory-swap=<same>` — swap evasion of `memory.max` is blocked
- `--cpus=<limit>` — CPU quota
- `--pids-limit=<N>` — pid cgroup cap
- `--ulimit nofile=N:N` and `--ulimit nproc=N:N` — belt-and-suspenders ulimits next to the cgroup caps
- `--security-opt seccomp=/etc/supakiln/seccomp.json` — explicit allow-list profile, shipped in `security/seccomp.json`. Note: the path is resolved by the Docker *client* (the backend), not the daemon, so the profile is bind-mounted into the backend container at `/etc/supakiln/`. It's also mounted into the `docker-daemon` container at the same path for symmetry / future tooling.
- `/tmp` and `/home/codeuser` as size-capped tmpfs — user code cannot grow the writable layer indefinitely
- `/tmp` is `noexec` on the worker path; `/home/codeuser` is `exec` only because `go run` exec()s its own output

Tune via env vars in `docker-compose.yml`:
`SUPAKILN_MEMORY_LIMIT`, `SUPAKILN_MEMORY_SWAP`, `SUPAKILN_CPU_LIMIT`, `SUPAKILN_PIDS_LIMIT`, `SUPAKILN_NOFILE_LIMIT`, `SUPAKILN_NPROC_LIMIT`, `SUPAKILN_SECCOMP_PROFILE_PATH`.

### Opt-in (requires operator action)

**AppArmor profile**
Set `SUPAKILN_APPARMOR_PROFILE=<name>` to pin a loaded profile. Without this, Docker's default (`docker-default`) is used if AppArmor is installed on the host, otherwise containers are `unconfined`. See the AppArmor Profile section below for a starting template; load it on the host via `apparmor_parser -r` before setting the env var.

**User-namespace remapping**
Edit `./security/daemon.json` (mounted read-only into the dind container at `/etc/docker/daemon.json`) and set `"userns-remap": "default"`. See `./security/daemon.json.example` for a template. After editing, `docker compose restart docker-daemon`. This maps container UID 1000 to a subordinate host UID, so a kernel-bug sandbox escape lands the attacker as a non-real host user rather than host UID 1000. First-enable rebuilds all cached user images and resets all tmpfs contents — plan a maintenance window.

> **Note on `command:` in compose:** do not wrap `dockerd` in `sh -c` — the docker:dind image's entrypoint only does its critical setup (tini as pid 1, iptables modprobe, cgroup v2 prep) when arg 1 is literally `dockerd`. Wrap in a shell and cgroup controllers silently fail to propagate; any `--memory`/`--cpus` container fails to start with a cryptic "domain controllers -- it is in an invalid state" error.

### Host prerequisites (not set by this repo)

These live on the Docker host and can't be configured from inside the dind container. Set them in `/etc/sysctl.d/` and reboot:

```
# Disable unprivileged user namespaces — defense-in-depth even if a
# seccomp bypass lets `unshare` through.
kernel.unprivileged_userns_clone=0

# Disable unprivileged BPF — eliminates a historically fertile source
# of container-escape CVEs.
kernel.unprivileged_bpf_disabled=1

# Restrict ptrace to same-UID processes only (2) or disable entirely (3).
kernel.yama.ptrace_scope=2
```

### Exhausted-container eviction ("cooked" workers)

A pid bomb or memory bomb can leave a container in a half-alive state: the worker process is still listening, but every subsequent `Popen` fails with EAGAIN/ENOMEM. Supakiln detects this in two ways:

1. **Reactive (hot path):** the worker catches `OSError(EAGAIN|ENOMEM|ENOSPC)` around `Popen` and responds to `/exec` with HTTP 503 and `{"cooked": true}`. The backend's existing self-heal retry path evicts the container and rebuilds on the retry attempt.

2. **Proactive (background reaper):** `scheduler._schedule_cooked_reaper()` runs every `SUPAKILN_COOKED_REAPER_INTERVAL_SECONDS` (30s default). It probes `/health` on every idle worker; the worker returns cgroup pressure stats (`pids.current/max`, `memory.current/max`). Workers reporting ≥ `SUPAKILN_COOKED_THRESHOLD_PCT` (90 % default) or unreachable are evicted.

The reaper skips workers with `busy_count > 0` — evicting mid-call tears the connection out from under the caller. Busy cooked workers catch up on the next sweep once their `/exec` returns (or 503s, which the hot path already handles).

### Single-use vs. reuse invariant

Worker containers are **cached per `(user_id, language, package_hash)`**. The cache key includes `user_id`, so one user's container is never reused for another user — the tenant boundary is the container. Within one user's (language, packages) bucket, a container is reused across `/exec` calls until the idle TTL fires or the cooked reaper evicts it. This is an intentional tradeoff: one-container-per-execution would push the cold-start cost (build + run + health-wait, typically 1-3s) onto every call.

Known gap — concurrent `/exec` on a reused worker: `workers/worker.py` uses `ThreadingHTTPServer`, and its `_reap_leftover_state` broadcasts SIGKILL to every UID-1000 process at the end of a call. If one user has two concurrent `/exec` calls on the same worker, one call's cleanup will kill the other's subprocess. A per-worker mutex would fix this. It's a correctness issue (one call aborts early), not a cross-tenant security issue.

### Network posture

User-code containers connect to the dind bridge network (`--network=bridge`) because the worker needs to accept HTTP from the backend. User code running in that same container therefore shares the bridge. Egress filtering (block `169.254.169.254/32`, RFC1918, everything but explicitly allowed registries) must be done at the bridge level — not in this repo. Confirm with the network team before treating workloads as hostile-capable.

### Base-image minimisation

Runtime Dockerfiles intentionally keep the toolchain (Go compiler, Node, Ruby, Python stdlib) present because user code needs it. There is no standalone `ip`/`iproute2` installed on the worker path; `bash.Dockerfile` adds `curl`, `jq`, and `ca-certificates` because bash workflows actually use them. Audit `ls /usr/bin /bin` inside a running worker if you want to shrink further — each tool is an exploitation gadget.



## Security Test Suite

The security test suite includes comprehensive tests for container breakout vulnerabilities and security misconfigurations.

### Running Security Tests

```bash
# Run basic security tests
python tests/test_security.py

# Run container security configuration tests
python tests/test_container_security.py

# Run comprehensive security benchmark
python tests/run_security_tests.py --benchmark
```

## Security Test Categories

### 1. Container Breakout Tests

- **File System Attacks**: Tests for `/proc`, `/sys`, and host filesystem access
- **Docker Socket Access**: Attempts to access Docker daemon from inside container
- **Privilege Escalation**: Tests for root access, sudo, and privileged operations
- **Namespace Escapes**: Tests for PID, network, mount, and user namespace isolation
- **Device Access**: Tests for raw device and memory access
- **Cgroup Manipulation**: Tests for resource limit bypass attempts

### 2. Network Security Tests

- **Network Isolation**: Tests for host network access
- **Port Binding**: Tests for privileged port access
- **Raw Socket Creation**: Tests for packet manipulation capabilities
- **Host Service Access**: Tests for accessing host services

### 3. Process Security Tests

- **Process Injection**: Tests for accessing host processes
- **Signal Handling**: Tests for sending signals to host processes
- **Process Memory Access**: Tests for reading other process memory
- **Resource Exhaustion**: Tests for resource limit enforcement

### 4. Container Configuration Tests

- **Security Options**: Validates container security settings
- **User Namespaces**: Tests for proper user isolation
- **Capabilities**: Tests for minimal capability sets
- **Seccomp Profiles**: Tests for syscall filtering
- **AppArmor/SELinux**: Tests for mandatory access controls

## Security Hardening Recommendations

### Enhanced Docker Run Command

```bash
docker run \
  --security-opt=no-new-privileges \
  --user=1000:1000 \
  --network=none \
  --cap-drop=ALL \
  --cap-add=SETUID \
  --cap-add=SETGID \
  --read-only \
  --tmpfs /tmp \
  --tmpfs /var/tmp \
  --memory=512m \
  --cpus=0.5 \
  --pids-limit=100 \
  --ulimit nofile=1024:1024 \
  --ulimit nproc=50:50 \
  --security-opt=seccomp=seccomp-profile.json \
  --security-opt=apparmor=docker-default \
  python-executor:latest
```

### Security Option Explanations

| Option | Purpose |
|--------|---------|
| `--security-opt=no-new-privileges` | Prevents privilege escalation |
| `--user=1000:1000` | Run as non-root user |
| `--network=none` | Complete network isolation |
| `--cap-drop=ALL` | Remove all capabilities |
| `--cap-add=SETUID/SETGID` | Add only required capabilities |
| `--read-only` | Read-only root filesystem |
| `--tmpfs /tmp` | Temporary filesystem for /tmp |
| `--memory=512m` | Memory limit |
| `--cpus=0.5` | CPU limit |
| `--pids-limit=100` | Process limit |
| `--ulimit nofile=1024:1024` | File descriptor limit |
| `--ulimit nproc=50:50` | Process creation limit |
| `--security-opt=seccomp=...` | Custom seccomp profile |
| `--security-opt=apparmor=...` | AppArmor profile |

## Custom Seccomp Profile

Create a custom seccomp profile to block dangerous syscalls:

```json
{
  "defaultAction": "SCMP_ACT_ALLOW",
  "syscalls": [
    {
      "names": [
        "reboot",
        "mount",
        "umount",
        "umount2",
        "swapon",
        "swapoff",
        "chroot",
        "pivot_root",
        "acct",
        "settimeofday",
        "stime",
        "clock_settime",
        "adjtimex",
        "nfsservctl",
        "quotactl",
        "lookup_dcookie",
        "perf_event_open",
        "fanotify_init",
        "kcmp",
        "add_key",
        "request_key",
        "keyctl",
        "uselib",
        "create_module",
        "init_module",
        "delete_module",
        "get_kernel_syms",
        "query_module",
        "ptrace",
        "process_vm_readv",
        "process_vm_writev",
        "iopl",
        "ioperm",
        "syslog",
        "kexec_load",
        "kexec_file_load"
      ],
      "action": "SCMP_ACT_ERRNO"
    }
  ]
}
```

## AppArmor Profile

Create a custom AppArmor profile for additional security:

```bash
#include <tunables/global>

profile docker-security flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>

  # Deny dangerous capabilities
  deny capability sys_admin,
  deny capability sys_ptrace,
  deny capability sys_module,
  deny capability dac_override,
  deny capability dac_read_search,

  # Allow basic file access
  /tmp/** rw,
  /var/tmp/** rw,
  /usr/bin/** ix,
  /usr/lib/** mr,
  /lib/** mr,
  /etc/passwd r,
  /etc/group r,

  # Deny sensitive file access
  deny /etc/shadow r,
  deny /etc/sudoers r,
  deny /root/** rw,
  deny /proc/sys/** rw,
  deny /sys/** rw,
  deny /dev/mem rw,
  deny /dev/kmem rw,
  deny /var/run/docker.sock rw,

  # Network restrictions
  deny network inet,
  deny network inet6,
  deny network packet,
  deny network raw,
}
```

## Security Test Results Interpretation

### Success Criteria

- **Excellent (95%+)**: All security tests pass, minimal vulnerabilities
- **Good (85-94%)**: Most tests pass, minor security issues
- **Moderate (70-84%)**: Several vulnerabilities present
- **Poor (<70%)**: Critical security issues present

### Critical Issues

- Container running as root user
- Docker socket access available
- Host network access possible
- Privileged mode enabled
- Dangerous capabilities present

### High Severity Issues

- Host filesystem access
- Network isolation bypass
- Process injection possible
- Resource limits not enforced
- Syscall filtering disabled

## Monitoring and Alerting

### Runtime Security Monitoring

```bash
# Monitor container behavior
docker stats --no-stream

# Check for suspicious network activity
netstat -tlnp | grep docker

# Monitor process creation
ps auxf | grep docker

# Check for privilege escalation attempts
journalctl -u docker.service | grep -i privilege
```

### Security Alerts

Set up alerts for:
- Containers running as root
- Unusual network activity
- High resource usage
- Failed privilege escalation attempts
- Syscall violations

## Best Practices Checklist

- [ ] Run containers as non-root user
- [ ] Use minimal base images
- [ ] Enable read-only root filesystem
- [ ] Implement network isolation
- [ ] Drop unnecessary capabilities
- [ ] Use custom seccomp profiles
- [ ] Enable AppArmor/SELinux
- [ ] Set resource limits
- [ ] Monitor container behavior
- [ ] Regularly update images
- [ ] Run security tests in CI/CD
- [ ] Implement log monitoring
- [ ] Use image scanning tools
- [ ] Enable container runtime security

## Compliance Standards

This security configuration helps meet:
- **CIS Docker Benchmark**
- **NIST Cybersecurity Framework**
- **PCI DSS Requirements**
- **SOC 2 Type II**
- **ISO 27001**

## Incident Response

In case of security breach:
1. Immediately stop affected containers
2. Collect logs and forensic data
3. Analyze attack vectors
4. Implement additional security measures
5. Update security policies
6. Notify stakeholders

## Additional Resources

- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)
- [OWASP Container Security](https://owasp.org/www-project-container-security/)
- [Linux Container Security](https://www.kernel.org/doc/Documentation/security/)

## Testing Schedule

- **Daily**: Basic security tests in CI/CD
- **Weekly**: Comprehensive security scan
- **Monthly**: Full security audit
- **Quarterly**: Penetration testing
- **Annually**: Security architecture review 