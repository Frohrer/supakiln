import subprocess
import os
import json
import time
import hashlib
import threading
import base64
import docker
import random
import resource
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError

class CodeExecutor:
    def __init__(self, image_name: str = "python-executor"):
        self.image_name = image_name
        self.containers: Dict[str, str] = {}  # package_hash -> container_id
        self.web_service_containers: Dict[str, Dict] = {}  # container_id -> service_info
        self._base_image_ready = False
        
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
        
        # Streamlit detection
        if 'streamlit' in packages or 'streamlit' in code_lower or 'st.' in code:
            return {
                'type': 'streamlit',
                'internal_port': internal_port,
                'start_command': f'cd /tmp && streamlit run app.py --server.address=0.0.0.0 --server.port={internal_port}',
                'needs_proxy_path': True  # Flag to indicate this service needs proxy path configuration
            }
        
        # FastAPI detection
        if 'fastapi' in packages or 'uvicorn' in packages or ('fastapi' in code_lower and 'uvicorn' in code_lower):
            return {
                'type': 'fastapi', 
                'internal_port': internal_port,
                'start_command': f'cd /tmp && python -c "import sys; sys.path.insert(0, \\"/tmp\\"); from app import app; import uvicorn; uvicorn.run(app, host=\\"0.0.0.0\\", port={internal_port})"'
            }
        
        # Flask detection
        if 'flask' in packages or 'flask' in code_lower:
            return {
                'type': 'flask',
                'internal_port': internal_port, 
                'start_command': f'cd /tmp && python -c "import sys; sys.path.insert(0, \\"/tmp\\"); from app import app; app.run(host=\\"0.0.0.0\\", port={internal_port}, debug=True)"'
            }
        
        # Dash detection
        if 'dash' in packages or ('dash' in code_lower and 'plotly' in packages):
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
    
    def _collect_container_metrics(self, container_id: str) -> Dict:
        """Collect detailed resource metrics from a container."""
        metrics = {}
        
        try:
            # Get container stats using Docker stats API
            env = os.environ.copy()
            stats_result = subprocess.run(
                ["docker", "stats", container_id, "--no-stream", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            if stats_result.returncode == 0 and stats_result.stdout.strip():
                stats_data = json.loads(stats_result.stdout.strip())
                
                # Parse CPU percentage
                cpu_percent_str = stats_data.get("CPUPerc", "0%").rstrip('%')
                metrics["cpu_percent"] = float(cpu_percent_str) if cpu_percent_str != "0" else 0.0
                
                # Parse memory usage
                mem_usage_str = stats_data.get("MemUsage", "0B / 0B")
                if "/" in mem_usage_str:
                    usage_str, limit_str = mem_usage_str.split(" / ")
                    metrics["memory_usage"] = self._parse_memory_string(usage_str)
                    metrics["memory_limit"] = self._parse_memory_string(limit_str)
                    
                    # Calculate memory percentage
                    if metrics["memory_limit"] > 0:
                        metrics["memory_percent"] = (metrics["memory_usage"] / metrics["memory_limit"]) * 100
                    else:
                        metrics["memory_percent"] = 0.0
                
                # Parse Block I/O
                block_io_str = stats_data.get("BlockIO", "0B / 0B")
                if "/" in block_io_str:
                    read_str, write_str = block_io_str.split(" / ")
                    metrics["block_io_read"] = self._parse_memory_string(read_str)
                    metrics["block_io_write"] = self._parse_memory_string(write_str)
                
                # Parse Network I/O
                net_io_str = stats_data.get("NetIO", "0B / 0B")
                if "/" in net_io_str:
                    rx_str, tx_str = net_io_str.split(" / ")
                    metrics["network_io_rx"] = self._parse_memory_string(rx_str)
                    metrics["network_io_tx"] = self._parse_memory_string(tx_str)
                
                # Parse PIDs
                pids_str = stats_data.get("PIDs", "0")
                metrics["pids_count"] = int(pids_str) if pids_str.isdigit() else 0
                
        except Exception as e:
            print(f"Warning: Could not collect container stats: {e}")
        
        # Try to get CPU time from cgroup files
        try:
            # Get CPU time from cgroup
            cpu_time_result = subprocess.run(
                ["docker", "exec", container_id, "cat", "/sys/fs/cgroup/cpu.stat"],
                capture_output=True,
                text=True,
                timeout=5,
                env=os.environ.copy()
            )
            
            if cpu_time_result.returncode == 0:
                cpu_stats = cpu_time_result.stdout.strip()
                for line in cpu_stats.split('\n'):
                    if line.startswith('usage_usec'):
                        total_cpu_time = int(line.split()[1]) / 1000000.0  # Convert microseconds to seconds
                        metrics["cpu_total_time"] = total_cpu_time
                    elif line.startswith('user_usec'):
                        user_time = int(line.split()[1]) / 1000000.0
                        metrics["cpu_user_time"] = user_time
                    elif line.startswith('system_usec'):
                        system_time = int(line.split()[1]) / 1000000.0
                        metrics["cpu_system_time"] = system_time
        except Exception as e:
            print(f"Warning: Could not collect CPU time from cgroup: {e}")
            
        # Try to get memory peak from cgroup
        try:
            memory_peak_result = subprocess.run(
                ["docker", "exec", container_id, "cat", "/sys/fs/cgroup/memory.peak"],
                capture_output=True,
                text=True,
                timeout=5,
                env=os.environ.copy()
            )
            
            if memory_peak_result.returncode == 0:
                memory_peak = int(memory_peak_result.stdout.strip())
                metrics["memory_peak"] = memory_peak
        except Exception as e:
            # Try alternative path for cgroup v1
            try:
                memory_peak_result = subprocess.run(
                    ["docker", "exec", container_id, "cat", "/sys/fs/cgroup/memory/memory.max_usage_in_bytes"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=os.environ.copy()
                )
                
                if memory_peak_result.returncode == 0:
                    memory_peak = int(memory_peak_result.stdout.strip())
                    metrics["memory_peak"] = memory_peak
            except Exception:
                print(f"Warning: Could not collect peak memory usage: {e}")
        
        return metrics
    
    def _parse_memory_string(self, mem_str: str) -> int:
        """Parse memory string like '1.5MiB' to bytes."""
        if not mem_str or mem_str == "0B":
            return 0
            
        # Remove whitespace
        mem_str = mem_str.strip()
        
        # Handle different units
        units = {
            'B': 1,
            'KiB': 1024,
            'MiB': 1024 * 1024,
            'GiB': 1024 * 1024 * 1024,
            'KB': 1000,
            'MB': 1000 * 1000,
            'GB': 1000 * 1000 * 1000,
            'kB': 1000,
            'mB': 1000 * 1000,
            'gB': 1000 * 1000 * 1000,
        }
        
        for unit, multiplier in units.items():
            if mem_str.endswith(unit):
                value_str = mem_str[:-len(unit)]
                try:
                    value = float(value_str)
                    return int(value * multiplier)
                except ValueError:
                    break
        
        # If no unit found, assume bytes
        try:
            return int(float(mem_str))
        except ValueError:
            return 0
    
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
        
        # Detect if this is a web service
        web_service = self._detect_web_service(code, packages)
        
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
            
            success, output, error = self._run_docker_command([
                "docker", "run",
                "-d",
                "-p", port_mapping,
                "--memory", "512m",
                "--cpus", "0.5"
            ] + network_options + [
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
            if service_info['type'] == 'streamlit':
                container_short_id = container_id[:8]
                proxy_path = f"/proxy/{container_short_id}"
                enhanced_command = f'streamlit run app.py --server.address=0.0.0.0 --server.port={service_info["internal_port"]} --server.baseUrlPath="{proxy_path}"'
                print(f"📝 Enhanced Command: {enhanced_command}")
                print(f"🛣️  Proxy Path: {proxy_path}")
            else:
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
            if service_info['type'] == 'streamlit':
                pkg_check = "python -c 'import streamlit; print(f\"Streamlit version: {streamlit.__version__}\")'"
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
            if service_info['type'] == 'streamlit':
                # Create Streamlit config without baseUrlPath - let it serve at root level
                # We'll handle all path rewriting in the proxy layer
                container_short_id = container_id[:8]
                
                streamlit_config = f'''
[server]
enableCORS = false
enableXsrfProtection = false
maxUploadSize = 200
headless = true
enableStaticServing = true
enableWebsocketCompression = false
port = {service_info["internal_port"]}
address = "0.0.0.0"

[browser]
gatherUsageStats = false

[global]
unitTest = false

[client]
toolbarMode = "minimal"

[logger]
level = "info"
'''
                config_script = f"echo '{base64.b64encode(streamlit_config.encode()).decode()}' | base64 -d > /tmp/.streamlit/config.toml"
                
                # Run Streamlit without baseUrlPath - serve at root level
                basic_streamlit_command = f'cd /tmp && streamlit run app.py --server.address=0.0.0.0 --server.port={service_info["internal_port"]}'
                
                service_start_script = f'''#!/bin/bash
cd /tmp
mkdir -p .streamlit
{config_script}
export PYTHONPATH=/tmp:$PYTHONPATH
export STREAMLIT_SERVER_ENABLE_STATIC_SERVING=true
export STREAMLIT_SERVER_ENABLE_WEBSOCKET_COMPRESSION=false
{basic_streamlit_command} > /tmp/service.log 2>&1
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
            process_check_command = f"ps aux | grep -E '(streamlit|uvicorn|flask|python.*start_service)' | grep -v grep || echo 'No service process found'"
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
            # Regular code execution - use package hash to potentially reuse containers
            if package_hash not in self.containers:
                image_tag = self._build_image(packages)
                
                # Regular container for non-web services
                success, output, error = self._run_docker_command([
                    "docker", "run",
                    "-d",
                    "--memory", "512m",
                    "--cpus", "0.5",
                    "--network", "bridge",  # Use bridge network for regular containers
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
            
            # Regular code execution with metrics collection
            encoded_code = base64.b64encode(code.encode()).decode()
            exec_command = f"echo '{encoded_code}' | base64 -d | python3"
            
            # Get initial metrics before execution
            initial_metrics = self._collect_container_metrics(container_id)
            
            # Execute the code
            execution_start_time = time.time()
            success, output, error = self._execute_with_timeout(container_id, exec_command, timeout)
            execution_time = time.time() - execution_start_time
            
            # Get final metrics after execution
            final_metrics = self._collect_container_metrics(container_id)
            
            # Calculate differential metrics (execution-specific)
            execution_metrics = {}
            for key in ["cpu_user_time", "cpu_system_time", "block_io_read", "block_io_write", "network_io_rx", "network_io_tx"]:
                if key in final_metrics and key in initial_metrics:
                    execution_metrics[key] = final_metrics[key] - initial_metrics[key]
                elif key in final_metrics:
                    execution_metrics[key] = final_metrics[key]
            
            # Use final metrics for current values
            for key in ["cpu_percent", "memory_usage", "memory_peak", "memory_percent", "memory_limit", "pids_count"]:
                if key in final_metrics:
                    execution_metrics[key] = final_metrics[key]
            
            # Try to get the exit code from the last command
            exit_code = None
            try:
                exit_code_result = subprocess.run(
                    ["docker", "exec", container_id, "echo", "$?"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=os.environ.copy()
                )
                if exit_code_result.returncode == 0:
                    try:
                        exit_code = int(exit_code_result.stdout.strip())
                    except ValueError:
                        pass
            except Exception:
                pass
            
            # If we couldn't get the exit code, infer it from success
            if exit_code is None:
                exit_code = 0 if success else 1
            
            result = {
                "success": success,
                "output": output,
                "error": error,
                "container_id": container_id,
                "execution_time": execution_time,
                "exit_code": exit_code
            }
            
            # Add execution metrics
            result.update(execution_metrics)
            
            return result
    
    def cleanup(self):
        """Clean up all containers."""
        env = os.environ.copy()
        for container_id in self.containers.values():
            try:
                subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, env=env)
            except Exception:
                pass
        self.containers.clear()
        self.web_service_containers.clear()

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