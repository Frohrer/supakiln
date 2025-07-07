import threading
import subprocess
import time
import base64
from datetime import datetime
# Database imports handled through models module
from models import PersistentService
from services.docker_client import docker_client
from code_executor import CodeExecutor
from env_manager import EnvironmentManager
import os

class ServiceManager:
    def __init__(self):
        self.running_services = {}  # service_id -> process info
        self.service_threads = {}  # service_id -> thread
        
    def start_service(self, service_id: int, db) -> bool:
        """Start a persistent service."""
        try:
            service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
            if not service:
                return False
                
            if service_id in self.running_services:
                # Already running
                return True
                
            # Update status to starting
            service.status = "starting"
            db.commit()
            
            # Start service in background thread
            thread = threading.Thread(target=self._run_service, args=(service_id, db.bind.url))
            thread.daemon = True
            thread.start()
            
            self.service_threads[service_id] = thread
            return True
            
        except Exception as e:
            print(f"Error starting service {service_id}: {e}")
            return False
    
    def stop_service(self, service_id: int, db) -> bool:
        """Stop a persistent service."""
        try:
            service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
            if not service:
                return False
                
            # Update status
            service.status = "stopped"
            service.process_id = None
            db.commit()
            
            # Stop the running process
            if service_id in self.running_services:
                process_info = self.running_services[service_id]
                container_id = process_info.get('container_id')
                exec_id = process_info.get('exec_id')
                
                if container_id and exec_id:
                    try:
                        # Kill the exec process
                        subprocess.run([
                            "docker", "exec", container_id, "pkill", "-f", f"exec-{exec_id}"
                        ], capture_output=True, env=os.environ.copy())
                    except Exception as e:
                        print(f"Error killing process in container: {e}")
                
                del self.running_services[service_id]
            
            # Remove thread
            if service_id in self.service_threads:
                del self.service_threads[service_id]
                
            return True
            
        except Exception as e:
            print(f"Error stopping service {service_id}: {e}")
            return False
    
    def restart_service(self, service_id: int, db) -> bool:
        """Restart a persistent service."""
        self.stop_service(service_id, db)
        time.sleep(1)  # Brief pause
        return self.start_service(service_id, db)
    
    def _run_service(self, service_id: int, db_url: str):
        """Run a service in the background (called from thread)."""
        # Use the centralized database configuration instead of creating a new engine
        from models import SessionLocal
        db = SessionLocal()
        
        try:
            service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
            if not service:
                return
                
            # Get or create container
            container_id = service.container_id
            executor = CodeExecutor()
            
            if not container_id or container_id not in executor.containers.values():
                # Create container with packages
                packages = []
                if service.packages and service.packages.strip():
                    packages = [pkg.strip() for pkg in service.packages.split(',') if pkg.strip()]
                
                package_hash = executor._get_package_hash(packages)
                image_tag = executor._build_image(packages)
                
                if package_hash not in executor.containers:
                    container = docker_client.containers.run(
                        image_tag,
                        detach=True,
                        tty=True,
                        mem_limit="256m",
                        cpu_period=100000,
                        cpu_quota=25000,  # 0.25 CPU
                        pids_limit=50,
                        ulimits=[
                            docker.types.Ulimit(name='nofile', soft=512, hard=512),
                            docker.types.Ulimit(name='nproc', soft=25, hard=25)
                        ],
                        security_opt=[
                            'seccomp=./security/seccomp-profile.json',
                            'no-new-privileges=true'
                        ],
                        cap_drop=['ALL'],
                        cap_add=['SETUID', 'SETGID'],
                        read_only=True,
                        tmpfs={
                            '/tmp': 'rw,noexec,nosuid,size=100m',
                            '/var/tmp': 'rw,noexec,nosuid,size=50m'
                        },
                        user='1000:1000'
                    )
                    executor.containers[package_hash] = container.id
                
                container_id = executor.containers[package_hash]
                service.container_id = container_id
            
            # Get environment variables
            from models import SessionLocal
            env_db = SessionLocal()
            try:
                # Try to load existing key
                if os.path.exists('.env_key'):
                    with open('.env_key', 'rb') as key_file:
                        key = key_file.read()
                else:
                    key = None
                env_manager = EnvironmentManager(env_db, key)
                env_vars = env_manager.get_all_variables()
            finally:
                env_db.close()
            
            # Prepare the code
            encoded_code = base64.b64encode(service.code.encode()).decode()
            
            # Update service status
            service.status = "running"
            service.started_at = datetime.utcnow()
            db.commit()
            
            # Execute the service (no timeout - runs indefinitely)
            container = docker_client.containers.get(container_id)
            result = container.exec_run(
                f"python -c 'import base64; exec(base64.b64decode(\"{encoded_code}\").decode())'",
                environment=env_vars,
                detach=True
            )
            
            # Store process info
            self.running_services[service_id] = {
                'container_id': container_id,
                'exec_id': result.id,
                'started_at': datetime.utcnow()
            }
            
            service.process_id = result.id
            db.commit()
            
            # Wait for the process to complete (or run indefinitely)
            try:
                # This will block until the process exits
                exit_code = result.exit_code
                if exit_code is None:
                    # Process is still running, we need to wait
                    # For now, we'll just monitor it
                    while service_id in self.running_services:
                        time.sleep(5)  # Check every 5 seconds
                        # Check if container is still running
                        try:
                            container.reload()
                            if container.status != 'running':
                                break
                        except Exception:
                            break
                            
            except Exception as e:
                print(f"Service {service_id} execution error: {e}")
                
            # Service stopped or errored
            if service_id in self.running_services:
                del self.running_services[service_id]
                
            # Update service status
            service.status = "stopped" if exit_code == 0 else "error"
            service.process_id = None
            db.commit()
            
            # Handle restart policy
            if service.restart_policy == "always" and service.is_active:
                print(f"Restarting service {service_id} due to restart policy")
                service.last_restart = datetime.utcnow()
                db.commit()
                time.sleep(5)  # Brief pause before restart
                self.start_service(service_id, db)
                
        except Exception as e:
            print(f"Error running service {service_id}: {e}")
            # Update service status to error
            try:
                service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
                if service:
                    service.status = "error"
                    service.process_id = None
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()

# Global service manager instance
service_manager = ServiceManager() 