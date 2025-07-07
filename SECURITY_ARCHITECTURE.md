# Security Architecture

## Overview

This system implements a **two-layer security architecture** that separates infrastructure management from user code execution. This is the same security model used by production container orchestration platforms like Kubernetes.

## Security Layers

### Layer 1: Infrastructure Layer (Docker Daemon)
- **Container**: `docker-daemon`
- **Privilege Level**: Privileged mode
- **Purpose**: Container orchestration and management
- **Runs User Code**: ❌ **NO**
- **Security Impact**: ✅ **Safe** - Isolated infrastructure component

The Docker daemon container requires privileged mode to:
- Mount filesystems (`/sys/kernel/security`, `/sys/fs/cgroup`)
- Manage kernel security features
- Create and manage user containers
- Set up container networking and isolation

**CRITICAL**: This container never executes user-provided code. It only manages containers.

### Layer 2: User Execution Layer
- **Containers**: All user code execution containers
- **Privilege Level**: Heavily restricted
- **Purpose**: Execute user-provided code safely
- **Runs User Code**: ✅ **YES**
- **Security Impact**: 🔒 **Secure** - All hardening measures applied

User execution containers are created with comprehensive security hardening:

#### Seccomp Profile
Blocks dangerous syscalls:
- `mount`, `umount`, `reboot`
- `swapon`, `swapoff`
- `chroot`, `pivot_root`
- `ptrace`, `process_vm_readv`
- And 30+ other dangerous syscalls

#### Capability Restrictions
- **Drops**: ALL capabilities
- **Adds**: Only minimal required (`SETUID`, `SETGID`)
- **Blocks**: `SYS_ADMIN`, `NET_ADMIN`, `NET_BIND_SERVICE`, etc.

#### Filesystem Security
- **Read-only root filesystem**
- **Limited tmpfs mounts** (`/tmp`, `/var/tmp`)
- **No access to host filesystem**
- **No access to dangerous `/proc` paths**

#### Resource Limits
- **Memory**: 256MB limit
- **CPU**: 0.25 cores (25% of one CPU)
- **Processes**: 50 process limit
- **File descriptors**: 512 limit

#### User Security
- **Non-root execution**: User 1000:1000
- **No privilege escalation**: `no-new-privileges` flag
- **User namespace isolation**

## Security Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                    Host System                              │
│  ┌─────────────────────────────────────────────────────────┤
│  │              Docker Daemon Container                    │
│  │              (Privileged - Infrastructure)              │
│  │                                                         │
│  │  ┌─────────────────┐  ┌─────────────────┐              │
│  │  │ User Container  │  │ User Container  │  ...         │
│  │  │ (Restricted)    │  │ (Restricted)    │              │
│  │  │                 │  │                 │              │
│  │  │ USER CODE RUNS  │  │ USER CODE RUNS  │              │
│  │  │ HERE SECURELY   │  │ HERE SECURELY   │              │
│  │  └─────────────────┘  └─────────────────┘              │
│  └─────────────────────────────────────────────────────────┤
└─────────────────────────────────────────────────────────────┘
```

## Why This Is Secure

### 1. **Isolation Principle**
- Infrastructure and user code are completely separated
- Docker daemon never executes user code
- User code never accesses infrastructure

### 2. **Defense in Depth**
- Multiple security layers protect user execution
- Even if one layer fails, others provide protection
- Comprehensive syscall, capability, and resource restrictions

### 3. **Industry Standard Model**
This architecture follows the same pattern as:
- **Kubernetes**: Privileged kubelet manages restricted pods
- **AWS Fargate**: Privileged orchestrator, restricted tasks
- **Google Cloud Run**: Infrastructure separation from workloads

### 4. **Threat Model Coverage**
✅ **Container Escape**: Blocked by seccomp + capabilities + filesystem restrictions  
✅ **Privilege Escalation**: Prevented by no-new-privileges + user restrictions  
✅ **Resource Exhaustion**: Limited by memory/CPU/process limits  
✅ **Network Attacks**: No privileged port access, limited capabilities  
✅ **Host Access**: Read-only filesystem, user namespace isolation  

## Vulnerability Analysis

### Original Issues (Fixed)
| Vulnerability | Status | Mitigation |
|---------------|--------|------------|
| `/proc/1/root` access | ✅ **FIXED** | Read-only filesystem + user restrictions |
| Privileged port binding | ✅ **FIXED** | Dropped `NET_BIND_SERVICE` capability |
| Dangerous syscalls | ✅ **FIXED** | Custom seccomp profile blocks 40+ syscalls |
| Resource exhaustion | ✅ **FIXED** | Memory, CPU, and process limits |
| Kernel access | ✅ **FIXED** | Seccomp blocks kernel manipulation |

### Security Verification
All user execution containers enforce:
- Non-root execution (UID/GID 1000)
- Seccomp filtering active
- Capability restrictions applied
- Resource limits enforced
- Read-only root filesystem
- Limited network access

## Production Readiness

This security architecture is suitable for production use because:
1. **Proven Model**: Used by major cloud platforms
2. **Comprehensive Protection**: Multiple security layers
3. **Isolation**: Clear separation of concerns
4. **Auditable**: All security measures are explicit and testable
5. **Maintainable**: Standard Docker security features

## Monitoring and Alerting

### Security Metrics to Monitor
- Container creation with proper restrictions
- Seccomp violations
- Capability usage
- Resource limit breaches
- Failed privilege escalations

### Security Tests
Run `python tests/test_container_security.py` to verify:
- All security configurations are applied
- User containers cannot escape restrictions
- Resource limits are enforced
- Network isolation is maintained

## Compliance

This architecture helps meet:
- **CIS Docker Benchmark** requirements
- **NIST Cybersecurity Framework** controls
- **SOC 2 Type II** security requirements
- **PCI DSS** container security standards 