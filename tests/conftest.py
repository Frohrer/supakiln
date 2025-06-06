import pytest
import os
import subprocess
from code_executor import CodeExecutor

@pytest.fixture(scope="session")
def docker_setup():
    """Ensure Docker is running and base image exists"""
    # Check if Docker is running
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        pytest.skip("Docker is not running")
        
    # Create executor instance to ensure base image exists
    executor = CodeExecutor()
    executor._ensure_base_image()
    return executor

@pytest.fixture(scope="function")
def code_executor(docker_setup):
    """Create a fresh CodeExecutor instance for each test"""
    executor = CodeExecutor()
    yield executor
    executor.cleanup()

@pytest.fixture(scope="session")
def test_packages():
    """Common test packages used across tests"""
    return ["numpy", "pandas", "requests"]

@pytest.fixture(scope="session")
def malicious_code():
    """Common malicious code patterns for security testing"""
    return {
        "file_access": """
import os
try:
    with open('/etc/passwd', 'r') as f:
        print(f.read())
except Exception as e:
    print(f"Access denied: {str(e)}")
""",
        "network_access": """
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('google.com', 80))
    print("Network access successful")
except Exception as e:
    print(f"Network access denied: {str(e)}")
""",
        "system_command": """
import os
os.system('rm -rf /')
""",
        "memory_exhaustion": """
import numpy as np
arr = np.zeros((10000, 10000), dtype=np.float64)
"""
    } 