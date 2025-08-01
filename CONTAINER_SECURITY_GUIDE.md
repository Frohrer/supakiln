# Container Security Guide

This guide provides comprehensive information about container security testing and hardening for the code execution environment.

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