import subprocess
import os
import json
import time
import hashlib
import threading
import base64
import docker
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError

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

# Switch to root for package installation
USER root

# Install packages
RUN pip install {' '.join(packages)}

# Switch back to non-root user
USER codeuser
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
        
        # Encode the code in base64 and execute directly
        encoded_code = base64.b64encode(code.encode()).decode()
        exec_command = f"echo '{encoded_code}' | base64 -d | python3"
        success, output, error = self._execute_with_timeout(container_id, exec_command, timeout)
        
        return {
            "success": success,
            "output": output,
            "error": error,
            "container_id": container_id
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