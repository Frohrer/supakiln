import subprocess
import os
import json
import time
import hashlib
import threading
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import base64

class CodeExecutor:
    def __init__(self, image_name: str = "python-executor"):
        self.image_name = image_name
        self.containers: Dict[str, str] = {}  # package_hash -> container_id
        self._ensure_base_image()
        
    def _run_docker_command(self, command: List[str], timeout: int = 30) -> Tuple[bool, str, Optional[str]]:
        """Run a Docker command and return (success, output, error)."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout
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
        try:
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
        except Exception as e:
            print(f"Error ensuring base image: {e}")
            raise
        
    def _get_package_hash(self, packages: List[str]) -> str:
        """Generate a valid Docker tag for a list of packages."""
        sorted_packages = sorted(packages)
        package_str = "-".join(sorted_packages)
        hash_obj = hashlib.md5(package_str.encode())
        return hash_obj.hexdigest()[:12]
    
    def _build_image(self, packages: List[str]) -> str:
        """Build a Docker image with the specified packages."""
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
            
        # Create temporary Dockerfile
        dockerfile_content = f"""
FROM {self.image_name}:base

# Create non-root user
RUN useradd -m -u 1000 codeuser

# Set up Python environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/home/codeuser/.local/bin:${PATH}"

# Create and set up app directory
WORKDIR /app
RUN mkdir -p /app/code && \
    chown -R codeuser:codeuser /app

# Switch to non-root user
USER codeuser

# Install packages as non-root user
RUN pip install --no-cache-dir --user {' '.join(packages)}

# Set up secure environment
ENV PYTHONPATH=/app

# Create a restricted environment
RUN mkdir -p /app/code && \
    chmod 755 /app/code && \
    chown -R codeuser:codeuser /app/code

# Set up secure Python environment
ENV PYTHONPATH=/app/code
ENV PYTHONHOME=/usr/local
ENV PYTHONSTARTUP=/app/code/.pythonrc

# Create a restricted .pythonrc
RUN echo "import sys; sys.path = ['/app/code']" > /app/code/.pythonrc && \
    chown codeuser:codeuser /app/code/.pythonrc && \
    chmod 644 /app/code/.pythonrc

# Set up secure environment variables
ENV HOME=/home/codeuser
ENV PATH=/home/codeuser/.local/bin:/usr/local/bin:/usr/bin:/bin
ENV PYTHONIOENCODING=utf-8
"""
        
        with open("Dockerfile.temp", "w") as f:
            f.write(dockerfile_content)
        
        try:
            # Build the image
            success, output, error = self._run_docker_command([
                "docker", "build",
                "-t", image_tag,
                "-f", "Dockerfile.temp",
                "."
            ])
            if not success:
                raise Exception(f"Failed to build image: {error}")
        finally:
            # Clean up
            if os.path.exists("Dockerfile.temp"):
                os.remove("Dockerfile.temp")
                
        return image_tag

    def _execute_with_timeout(self, container_id: str, command: str, timeout: int) -> Tuple[bool, str, Optional[str]]:
        """Execute a command in a container with timeout."""
        try:
            result = subprocess.run(
                ["docker", "exec", container_id, "sh", "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode == 0:
                return True, result.stdout, None
            return False, None, result.stderr
        except subprocess.TimeoutExpired:
            # Kill and remove the container
            subprocess.run(["docker", "kill", container_id], capture_output=True)
            subprocess.run(["docker", "rm", container_id], capture_output=True)
            # Remove from our tracking
            for package_hash, cid in list(self.containers.items()):
                if cid == container_id:
                    del self.containers[package_hash]
            return False, None, f"Execution timed out after {timeout} seconds"
        except Exception as e:
            return False, None, str(e)
    
    def execute_code(self, code: str, packages: List[str], timeout: int = 30) -> Dict:
        """
        Execute Python code in a container with the specified packages.
        
        Args:
            code: Python code to execute
            packages: List of required Python packages
            timeout: Maximum execution time in seconds
            
        Returns:
            Dict containing execution results
        """
        package_hash = self._get_package_hash(packages)
        
        # Get or create container
        if package_hash not in self.containers:
            image_tag = self._build_image(packages)
            success, output, error = self._run_docker_command([
                "docker", "run",
                "-d",
                "--memory", "512m",
                "--cpus", "0.5",
                "--network", "none",  # Disable network access
                "--cap-drop", "ALL",  # Drop all capabilities
                "--security-opt", "no-new-privileges",  # Prevent privilege escalation
                "--security-opt", "seccomp=unconfined",  # Use default seccomp profile
                "--pids-limit", "50",  # Limit number of processes
                "--ulimit", "nofile=64:64",  # Limit file descriptors
                "--ulimit", "nproc=50:50",  # Limit number of processes
                "--read-only",  # Make container filesystem read-only
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=50m",  # Mount tmpfs for temporary files
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
            self.containers[package_hash] = container_id
        
        container_id = self.containers[package_hash]
        
        # Create a temporary file with the code using base64 encoding
        temp_file = f"/tmp/code_{int(time.time())}.py"
        encoded_code = base64.b64encode(code.encode()).decode()
        write_command = f"echo '{encoded_code}' | base64 -d > {temp_file}"
        success, _, error = self._execute_with_timeout(container_id, write_command, timeout)
        if not success:
            return {
                "success": False,
                "output": None,
                "error": f"Failed to write code to file: {error}"
            }
        
        # Execute the code file with restricted Python environment
        exec_command = f"PYTHONPATH=/app/code python3 {temp_file}"
        success, output, error = self._execute_with_timeout(container_id, exec_command, timeout)
        
        # Clean up the temporary file
        cleanup_command = f"rm {temp_file}"
        self._execute_with_timeout(container_id, cleanup_command, timeout)
        
        return {
            "success": success,
            "output": output,
            "error": error
        }
    
    def cleanup(self):
        """Clean up all containers."""
        for container_id in self.containers.values():
            try:
                subprocess.run(["docker", "rm", "-f", container_id], capture_output=True)
            except Exception:
                pass
        self.containers.clear()

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