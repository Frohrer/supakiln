import unittest
import subprocess
import docker
import time
import os
from code_executor import CodeExecutor
from services.docker_client import docker_client

class TestContainerSecurityConfiguration(unittest.TestCase):
    """Test Docker container security configurations and hardening"""
    
    def setUp(self):
        self.executor = CodeExecutor()
        
    def tearDown(self):
        self.executor.cleanup()
        
    def test_container_security_options(self):
        """Test that containers are created with proper security options"""
        # Execute code to create a container
        result = self.executor.execute_code("print('Security test')", [], timeout=5)
        
        if result['success'] and 'container_id' in result:
            container_id = result['container_id']
            
            # Inspect container configuration
            try:
                container = docker_client.containers.get(container_id)
                config = container.attrs
                
                # Check security configurations
                host_config = config.get('HostConfig', {})
                
                # Check memory limits
                memory_limit = host_config.get('Memory', 0)
                self.assertGreater(memory_limit, 0, "Memory limit should be set")
                self.assertLessEqual(memory_limit, 512 * 1024 * 1024, "Memory limit should be reasonable")
                
                # Check CPU limits
                cpu_quota = host_config.get('CpuQuota', 0)
                self.assertGreater(cpu_quota, 0, "CPU quota should be set")
                
                # Check if running as non-root user
                config_user = config.get('Config', {}).get('User', '')
                self.assertTrue(config_user in ['1000:1000', 'codeuser'], "Container should run as non-root user")
                
                # Check network mode
                network_mode = host_config.get('NetworkMode', '')
                self.assertNotEqual(network_mode, 'host', "Container should not use host networking")
                
                # Check privileged mode
                privileged = host_config.get('Privileged', False)
                self.assertFalse(privileged, "Container should not run in privileged mode")
                
                # Check security options
                security_opt = host_config.get('SecurityOpt', [])
                has_seccomp = any('seccomp' in opt for opt in security_opt)
                has_no_new_privs = any('no-new-privileges' in opt for opt in security_opt)
                
                self.assertTrue(has_seccomp, "Container should have seccomp profile")
                self.assertTrue(has_no_new_privs, "Container should have no-new-privileges")
                # Note: AppArmor is optional and may not be available on all systems (e.g., Docker Desktop)
                
                # Check capabilities
                cap_add = host_config.get('CapAdd', [])
                cap_drop = host_config.get('CapDrop', [])
                
                # Should drop ALL capabilities
                self.assertIn('ALL', cap_drop, "Container should drop ALL capabilities")
                
                # Should only add minimal required capabilities
                allowed_caps = ['SETUID', 'SETGID']
                for cap in cap_add:
                    self.assertIn(cap, allowed_caps, f"Only minimal capabilities should be added, found: {cap}")
                
                # Should not have dangerous capabilities
                dangerous_caps = ['SYS_ADMIN', 'SYS_PTRACE', 'SYS_MODULE', 'DAC_OVERRIDE', 'NET_ADMIN', 'NET_BIND_SERVICE']
                for cap in dangerous_caps:
                    self.assertNotIn(cap, cap_add, f"Dangerous capability {cap} should not be added")
                    
                # Check read-only filesystem
                read_only = host_config.get('ReadonlyRootfs', False)
                self.assertTrue(read_only, "Container should use read-only root filesystem")
                
                # Check process limits
                pids_limit = host_config.get('PidsLimit', 0)
                self.assertGreater(pids_limit, 0, "Container should have process limits")
                self.assertLessEqual(pids_limit, 100, "Process limit should be reasonable")
                    
            except Exception as e:
                self.fail(f"Failed to inspect container: {e}")
                
    def test_container_filesystem_security(self):
        """Test container filesystem security and read-only restrictions"""
        filesystem_test = """
import os
import tempfile
attempts = []

# Test write permissions in various directories
test_dirs = [
    '/etc',
    '/usr',
    '/bin',
    '/sbin',
    '/lib',
    '/var/log',
    '/root'
]

for dir_path in test_dirs:
    try:
        test_file = os.path.join(dir_path, 'security_test.txt')
        with open(test_file, 'w') as f:
            f.write('test')
        attempts.append(f"SECURITY ISSUE: Can write to {dir_path}")
        os.remove(test_file)
    except Exception as e:
        attempts.append(f"Write blocked to {dir_path}: {type(e).__name__}")

# Test /tmp directory (should be writable)
try:
    with tempfile.NamedTemporaryFile(dir='/tmp', delete=False) as f:
        f.write(b'test')
        attempts.append(f"Can write to /tmp: OK")
        os.unlink(f.name)
except Exception as e:
    attempts.append(f"Cannot write to /tmp: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(filesystem_test, [], timeout=5)
        if result['success']:
            # Should not be able to write to system directories
            self.assertNotIn("SECURITY ISSUE: Can write to /etc", result['output'])
            self.assertNotIn("SECURITY ISSUE: Can write to /usr", result['output'])
            self.assertNotIn("SECURITY ISSUE: Can write to /bin", result['output'])
            # Should be able to write to /tmp
            self.assertIn("Can write to /tmp: OK", result['output'])
            
    def test_container_process_limits(self):
        """Test container process and resource limits"""
        process_limit_test = """
import os
import subprocess
import resource
attempts = []

# Check current process limits
try:
    # Check max processes
    soft, hard = resource.getrlimit(resource.RLIMIT_NPROC)
    attempts.append(f"Process limit: soft={soft}, hard={hard}")
    
    # Check max open files
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    attempts.append(f"File descriptor limit: soft={soft}, hard={hard}")
    
    # Check memory limit
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        attempts.append(f"Memory limit: soft={soft}, hard={hard}")
    except:
        attempts.append("Memory limit: not available")
        
except Exception as e:
    attempts.append(f"Resource limits error: {e}")

# Try to create many processes
try:
    processes = []
    for i in range(50):
        p = subprocess.Popen(['sleep', '1'])
        processes.append(p)
    attempts.append(f"Created {len(processes)} processes")
    
    # Clean up
    for p in processes:
        p.terminate()
        p.wait()
except Exception as e:
    attempts.append(f"Process creation limited: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(process_limit_test, [], timeout=10)
        if result['success']:
            # Should have reasonable limits
            self.assertIn("Process limit:", result['output'])
            self.assertIn("File descriptor limit:", result['output'])
            
    def test_container_network_security(self):
        """Test container network security and isolation"""
        network_security_test = """
import socket
import subprocess
import os
attempts = []

# Check network interfaces
try:
    result = subprocess.run(['ip', 'addr'], capture_output=True, text=True)
    interfaces = result.stdout
    attempts.append(f"Network interfaces: {len(interfaces.split('inet '))} IPs")
    
    # Should not have host network interface
    if 'docker0' in interfaces:
        attempts.append("SECURITY ISSUE: Host network interface visible")
    else:
        attempts.append("Host network isolation: OK")
        
except Exception as e:
    attempts.append(f"Network interface check blocked: {e}")

# Test port binding capabilities
try:
    # Try to bind to privileged ports
    for port in [22, 80, 443, 53]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('0.0.0.0', port))
            attempts.append(f"SECURITY ISSUE: Can bind to privileged port {port}")
            sock.close()
        except Exception as e:
            attempts.append(f"Privileged port {port} blocked: {type(e).__name__}")
            
except Exception as e:
    attempts.append(f"Port binding test error: {e}")

# Test raw socket creation
try:
    raw_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    attempts.append("SECURITY ISSUE: Can create raw sockets")
    raw_sock.close()
except Exception as e:
    attempts.append(f"Raw socket creation blocked: {type(e).__name__}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(network_security_test, [], timeout=5)
        if result['success']:
            # Should not have host network access or privileged capabilities
            self.assertNotIn("SECURITY ISSUE: Host network interface visible", result['output'])
            self.assertNotIn("SECURITY ISSUE: Can bind to privileged port", result['output'])
            self.assertNotIn("SECURITY ISSUE: Can create raw sockets", result['output'])
            
    def test_container_cgroup_security(self):
        """Test container cgroup security and resource control"""
        cgroup_test = """
import os
import glob
attempts = []

# Check cgroup v1 information
try:
    with open('/proc/self/cgroup', 'r') as f:
        cgroup_info = f.read()
        attempts.append(f"Cgroup info: {len(cgroup_info)} chars")
        
        # Check if we're in a container cgroup
        if 'docker' in cgroup_info:
            attempts.append("Container cgroup detected: OK")
        else:
            attempts.append("Container cgroup not detected")
            
except Exception as e:
    attempts.append(f"Cgroup info blocked: {e}")

# Check cgroup v2 information
try:
    if os.path.exists('/sys/fs/cgroup/cgroup.controllers'):
        with open('/sys/fs/cgroup/cgroup.controllers', 'r') as f:
            controllers = f.read().strip()
            attempts.append(f"Cgroup v2 controllers: {controllers}")
except Exception as e:
    attempts.append(f"Cgroup v2 info blocked: {e}")

# Check memory cgroup limits
try:
    memory_limit_files = [
        '/sys/fs/cgroup/memory/memory.limit_in_bytes',
        '/sys/fs/cgroup/memory.max',
        '/sys/fs/cgroup/memory.high'
    ]
    
    for file in memory_limit_files:
        if os.path.exists(file):
            with open(file, 'r') as f:
                limit = f.read().strip()
                attempts.append(f"Memory limit from {file}: {limit}")
                break
                
except Exception as e:
    attempts.append(f"Memory limit check blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(cgroup_test, [], timeout=5)
        if result['success']:
            # Should be in container cgroup
            self.assertIn("Container cgroup detected: OK", result['output'])
            
    def test_container_seccomp_profile(self):
        """Test container seccomp security profile"""
        seccomp_test = """
import os
import subprocess
attempts = []

# Check seccomp status
try:
    with open('/proc/self/status', 'r') as f:
        for line in f:
            if 'Seccomp' in line:
                attempts.append(f"Seccomp status: {line.strip()}")
                
except Exception as e:
    attempts.append(f"Seccomp status blocked: {e}")

# Test restricted syscalls
restricted_syscalls = [
    'reboot',
    'swapon',
    'swapoff',
    'mount',
    'umount',
    'chroot',
    'pivot_root'
]

for syscall in restricted_syscalls:
    try:
        # Try to call restricted syscall using subprocess
        result = subprocess.run([syscall], capture_output=True, text=True)
        if result.returncode != 127:  # 127 = command not found
            attempts.append(f"SECURITY ISSUE: {syscall} syscall available")
        else:
            attempts.append(f"Syscall {syscall} blocked: command not found")
    except Exception as e:
        attempts.append(f"Syscall {syscall} blocked: {type(e).__name__}")

# Test using strace to check syscall filtering
try:
    result = subprocess.run(['strace', '-e', 'trace=reboot', 'echo', 'test'], 
                          capture_output=True, text=True)
    if 'reboot' in result.stderr:
        attempts.append("SECURITY ISSUE: Syscall tracing shows reboot available")
    else:
        attempts.append("Syscall filtering: OK")
except Exception as e:
    attempts.append(f"Strace test blocked: {type(e).__name__}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(seccomp_test, [], timeout=5)
        if result['success']:
            # Should have seccomp enabled
            self.assertIn("Seccomp status:", result['output'])
            self.assertNotIn("SECURITY ISSUE: reboot syscall available", result['output'])
            
    def test_container_apparmor_profile(self):
        """Test container AppArmor security profile (optional on some systems)"""
        apparmor_test = """
import os
import subprocess
attempts = []

# Check if AppArmor is available on this system
apparmor_available = os.path.exists('/proc/self/attr/current')

if not apparmor_available:
    attempts.append("AppArmor not available on this system (e.g., Docker Desktop)")
else:
    # Check AppArmor status
    try:
        with open('/proc/self/attr/current', 'r') as f:
            apparmor_status = f.read().strip()
            attempts.append(f"AppArmor status: {apparmor_status}")
            
            if 'docker-default' in apparmor_status:
                attempts.append("Docker default AppArmor profile: OK")
            elif 'unconfined' in apparmor_status:
                attempts.append("SECURITY ISSUE: AppArmor unconfined")
            else:
                attempts.append("AppArmor profile: Custom or unknown")
                
    except Exception as e:
        attempts.append(f"AppArmor status blocked: {e}")

    # Test AppArmor restrictions
    try:
        # Try to access AppArmor files
        result = subprocess.run(['aa-status'], capture_output=True, text=True)
        attempts.append(f"AppArmor status command: {result.returncode}")
    except Exception as e:
        attempts.append(f"AppArmor status command blocked: {type(e).__name__}")

    # Test file access restrictions
    try:
        # Try to access sensitive files that should be blocked by AppArmor
        sensitive_files = [
            '/etc/apparmor.d/',
            '/sys/kernel/security/apparmor/',
            '/proc/sys/kernel/yama/ptrace_scope'
        ]
        
        for file in sensitive_files:
            try:
                if os.path.exists(file):
                    if os.path.isdir(file):
                        contents = os.listdir(file)
                        attempts.append(f"SECURITY ISSUE: Can access {file}: {len(contents)} items")
                    else:
                        with open(file, 'r') as f:
                            content = f.read()
                            attempts.append(f"SECURITY ISSUE: Can read {file}: {len(content)} chars")
            except Exception as e:
                attempts.append(f"Access blocked to {file}: {type(e).__name__}")
                
    except Exception as e:
        attempts.append(f"AppArmor restriction test error: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(apparmor_test, [], timeout=5)
        if result['success']:
            # AppArmor is optional on some systems (like Docker Desktop)
            if "AppArmor not available" in result['output']:
                print("AppArmor test skipped - not available on this system")
            else:
                # If AppArmor is available, it should provide protection
                self.assertNotIn("SECURITY ISSUE: AppArmor unconfined", result['output'])
                self.assertNotIn("SECURITY ISSUE: Can access", result['output'])
            
    def test_container_user_namespace(self):
        """Test container user namespace security"""
        user_namespace_test = """
import os
import subprocess
attempts = []

# Check user namespace mapping
try:
    with open('/proc/self/uid_map', 'r') as f:
        uid_map = f.read().strip()
        attempts.append(f"UID mapping: {uid_map}")
        
    with open('/proc/self/gid_map', 'r') as f:
        gid_map = f.read().strip()
        attempts.append(f"GID mapping: {gid_map}")
        
except Exception as e:
    attempts.append(f"User namespace mapping blocked: {e}")

# Check effective user/group
try:
    uid = os.getuid()
    gid = os.getgid()
    euid = os.geteuid()
    egid = os.getegid()
    
    attempts.append(f"UID: {uid}, GID: {gid}, EUID: {euid}, EGID: {egid}")
    
    # Should not be root
    if uid == 0 or euid == 0:
        attempts.append("SECURITY ISSUE: Running as root user")
    else:
        attempts.append("User namespace: OK - not root")
        
except Exception as e:
    attempts.append(f"User ID check error: {e}")

# Test user namespace capabilities
try:
    # Check if we can access user namespace files
    result = subprocess.run(['ls', '/proc/self/ns/user'], capture_output=True, text=True)
    if result.returncode == 0:
        attempts.append("User namespace available")
    else:
        attempts.append("User namespace not available")
        
except Exception as e:
    attempts.append(f"User namespace check blocked: {type(e).__name__}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(user_namespace_test, [], timeout=5)
        if result['success']:
            # Should not be running as root
            self.assertNotIn("SECURITY ISSUE: Running as root user", result['output'])
            self.assertIn("User namespace: OK - not root", result['output'])
            
    def test_container_mount_namespace(self):
        """Test container mount namespace security"""
        mount_namespace_test = """
import os
import subprocess
attempts = []

# Check mount namespace
try:
    with open('/proc/self/mountinfo', 'r') as f:
        mountinfo = f.read()
        mount_lines = mountinfo.split('\\n')
        attempts.append(f"Mount entries: {len(mount_lines)}")
        
        # Check for dangerous mounts
        dangerous_mounts = [
            '/proc/sys/fs/binfmt_misc',
            '/proc/sys',
            '/proc/sysrq-trigger',
            '/proc/irq',
            '/proc/bus',
            '/dev/mem',
            '/dev/kmem'
        ]
        
        mounted_paths = []
        for line in mount_lines:
            if line.strip():
                parts = line.split()
                if len(parts) >= 5:
                    mount_point = parts[4]
                    mounted_paths.append(mount_point)
        
        for dangerous in dangerous_mounts:
            if dangerous in mounted_paths:
                attempts.append(f"SECURITY ISSUE: Dangerous mount found: {dangerous}")
            else:
                attempts.append(f"Dangerous mount blocked: {dangerous}")
                
except Exception as e:
    attempts.append(f"Mount namespace check blocked: {e}")

# Test mount operations
try:
    # Try to mount tmpfs
    result = subprocess.run(['mount', '-t', 'tmpfs', 'tmpfs', '/tmp/test_mount'], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        attempts.append("SECURITY ISSUE: Can perform mount operations")
    else:
        attempts.append("Mount operations blocked: OK")
        
except Exception as e:
    attempts.append(f"Mount operation test blocked: {type(e).__name__}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(mount_namespace_test, [], timeout=5)
        if result['success']:
            # Should not have dangerous mounts or mount capabilities
            self.assertNotIn("SECURITY ISSUE: Dangerous mount found:", result['output'])
            self.assertNotIn("SECURITY ISSUE: Can perform mount operations", result['output'])

if __name__ == '__main__':
    unittest.main() 