from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import uvicorn
from code_executor import CodeExecutor
import docker
import os
from models import SessionLocal, ScheduledJob, ExecutionLog, WebhookJob, PersistentService
from scheduler import scheduler
from sqlalchemy.orm import Session
import time
from datetime import datetime
import base64
import json
from env_manager import EnvironmentManager, EnvironmentVariable
import threading
import subprocess


app = FastAPI(title="Code Execution Engine API")

# Add CORS middleware with permissive settings since Cloudflare bypasses OPTIONS to origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins since Cloudflare handles the actual filtering
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
    max_age=86400,  # Cache preflight requests for 24 hours
)


# Add a health check endpoint that bypasses Cloudflare Access
@app.get("/health")
async def health_check():
    """
    Health check endpoint that should bypass Cloudflare Access.
    Configure this endpoint to be public in your Cloudflare Access rules.
    """
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Mount static files - update the path to be relative to the current file
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize executor
executor = CodeExecutor()

# Initialize Docker client separately with proper error handling
def get_docker_client():
    """Get Docker client with proper error handling for DinD sidecar."""
    try:
        # Check if DOCKER_HOST is set (for sidecar approach)
        docker_host = os.environ.get('DOCKER_HOST')
        
        if docker_host:
            print(f"Using DOCKER_HOST: {docker_host}")
            # Connect directly to the specified host
            client = docker.DockerClient(base_url=docker_host)
            client.ping()
            print("Successfully connected to Docker sidecar")
            return client
        
        # Fallback: try to connect to sidecar on default port
        sidecar_hosts = [
            'tcp://docker-daemon:2376',  # Default sidecar name
            'tcp://localhost:2376',      # If running locally
        ]
        
        for host in sidecar_hosts:
            try:
                print(f"Trying Docker sidecar: {host}")
                client = docker.DockerClient(base_url=host)
                client.ping()
                print(f"Successfully connected to Docker via {host}")
                return client
            except Exception as e:
                print(f"Failed to connect via {host}: {e}")
                continue
            
        # Final fallback to from_env()
        print("Trying Docker connection via from_env()")
        client = docker.from_env()
        client.ping()
        print("Successfully connected to Docker via from_env()")
        return client
        
    except Exception as e:
        raise docker.errors.DockerException(
            f"Could not connect to Docker daemon. "
            f"For Docker sidecar: ensure docker-daemon service is running. "
            f"For native Linux: ensure Docker daemon is running (sudo systemctl start docker). "
            f"Original error: {e}"
        )

# Initialize Docker client once
try:
    docker_client = get_docker_client()
    print("Docker client initialized successfully")
except docker.errors.DockerException as e:
    print(f"Error initializing Docker: {str(e)}")
    print("Please ensure Docker is running and you have the necessary permissions.")
    raise



class CodeExecutionRequest(BaseModel):
    code: Optional[str] = None
    job_id: Optional[int] = None
    packages: Optional[List[str]] = None
    timeout: Optional[int] = 30
    container_id: Optional[str] = None

class PackageInstallRequest(BaseModel):
    name: str
    packages: List[str]

class ContainerResponse(BaseModel):
    container_id: str
    name: str
    packages: List[str]
    created_at: str
    code: Optional[str] = None

class ScheduledJobRequest(BaseModel):
    name: str
    code: str
    cron_expression: str
    container_id: Optional[str] = None
    packages: Optional[List[str]] = None

class ScheduledJobResponse(BaseModel):
    id: int
    name: str
    cron_expression: str
    container_id: Optional[str]
    packages: Optional[str]
    created_at: str
    last_run: Optional[str]
    is_active: bool

class ExecutionLogResponse(BaseModel):
    id: int
    job_id: Optional[int]
    webhook_job_id: Optional[int]
    code: str
    output: Optional[str]
    error: Optional[str]
    container_id: Optional[str]
    execution_time: float
    started_at: str
    status: str
    request_data: Optional[str]
    response_data: Optional[str]

class EnvVarRequest(BaseModel):
    name: str
    value: str
    description: Optional[str] = None

class EnvVarResponse(BaseModel):
    name: str
    created_at: str
    updated_at: str

class EnvVarMetadata(BaseModel):
    name: str
    description: Optional[str]
    created_at: str
    updated_at: str

class WebhookJobRequest(BaseModel):
    name: str
    endpoint: str  # URL path like /webhook/my-job
    code: str
    container_id: Optional[str] = None
    packages: Optional[List[str]] = None
    timeout: Optional[int] = 30
    description: Optional[str] = None

class WebhookJobResponse(BaseModel):
    id: int
    name: str
    endpoint: str
    code: str
    container_id: Optional[str]
    packages: Optional[str]
    created_at: str
    last_triggered: Optional[str]
    is_active: bool
    timeout: int
    description: Optional[str]

class PersistentServiceRequest(BaseModel):
    name: str
    code: str
    container_id: Optional[str] = None
    packages: Optional[List[str]] = None
    restart_policy: Optional[str] = "always"  # always, never, on-failure
    description: Optional[str] = None
    auto_start: Optional[bool] = True

class PersistentServiceResponse(BaseModel):
    id: int
    name: str
    code: str
    container_id: Optional[str]
    packages: Optional[str]
    created_at: str
    started_at: Optional[str]
    last_restart: Optional[str]
    is_active: bool
    status: str  # stopped, starting, running, error, restarting
    restart_policy: str
    description: Optional[str]
    process_id: Optional[str]
    auto_start: bool

# Store container names
container_names = {}  # container_id -> name

# Initialize environment manager
env_manager = None

# Service manager for persistent services
class ServiceManager:
    def __init__(self):
        self.running_services = {}  # service_id -> process info
        self.service_threads = {}  # service_id -> thread
        
    def start_service(self, service_id: int, db: Session) -> bool:
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
    
    def stop_service(self, service_id: int, db: Session) -> bool:
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
    
    def restart_service(self, service_id: int, db: Session) -> bool:
        """Restart a persistent service."""
        self.stop_service(service_id, db)
        time.sleep(1)  # Brief pause
        return self.start_service(service_id, db)
    
    def _run_service(self, service_id: int, db_url: str):
        """Run a service in the background (called from thread)."""
        # Create new database session for this thread
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        engine = create_engine(str(db_url))
        ThreadSessionLocal = sessionmaker(bind=engine)
        db = ThreadSessionLocal()
        
        try:
            service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
            if not service:
                return
                
            # Get or create container
            container_id = service.container_id
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
                        mem_limit="512m",
                        cpu_period=100000,
                        cpu_quota=50000
                    )
                    executor.containers[package_hash] = container.id
                
                container_id = executor.containers[package_hash]
                service.container_id = container_id
            
            # Get environment variables
            env_manager = get_env_manager()
            env_vars = env_manager.get_all_variables()
            
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

service_manager = ServiceManager()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_env_manager():
    global env_manager
    if env_manager is None:
        db = SessionLocal()
        try:
            # Try to load existing key
            if os.path.exists('.env_key'):
                with open('.env_key', 'rb') as key_file:
                    key = key_file.read()
            else:
                key = None
            env_manager = EnvironmentManager(db, key)
        finally:
            db.close()
    return env_manager

@app.get("/")
async def read_root():
    """Serve the main page."""
    return FileResponse("static/index.html")

@app.post("/containers", response_model=ContainerResponse)
async def create_container(request: PackageInstallRequest):
    """
    Create a new container with specified packages installed.
    Returns the container ID for future use.
    """
    try:
        # Check if name is already in use
        if request.name in container_names.values():
            raise HTTPException(status_code=400, detail="Container name already exists")
        
        package_hash = executor._get_package_hash(request.packages)
        image_tag = executor._build_image(request.packages)
        
        # Create container if it doesn't exist
        if package_hash not in executor.containers:
            container = docker_client.containers.run(
                image_tag,
                detach=True,
                tty=True,
                mem_limit="512m",
                cpu_period=100000,
                cpu_quota=50000
            )
            executor.containers[package_hash] = container.id
        
        container_id = executor.containers[package_hash]
        container_names[container_id] = request.name
        
        return ContainerResponse(
            container_id=container_id,
            name=request.name,
            packages=request.packages,
            created_at=container.attrs['Created']
        )
    except docker.errors.ImageNotFound:
        raise HTTPException(
            status_code=500,
            detail="Failed to build container image. Please ensure Docker is running and you have the necessary permissions."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/containers", response_model=List[ContainerResponse])
async def list_containers():
    """
    List all active containers and their installed packages.
    """
    containers = []
    for package_hash, container_id in executor.containers.items():
        try:
            container = docker_client.containers.get(container_id)
            # Extract packages from image tag
            image_tag = container.image.tags[0]
            packages = image_tag.split(":")[-1].split(",")
            containers.append(ContainerResponse(
                container_id=container_id,
                name=container_names.get(container_id, "Unnamed"),
                packages=packages,
                created_at=container.attrs['Created']
            ))
        except Exception:
            continue
    return containers

@app.get("/containers/{container_id}", response_model=ContainerResponse)
async def get_container(container_id: str):
    """
    Get details of a specific container including its code.
    """
    try:
        if container_id not in executor.containers.values():
            raise HTTPException(status_code=404, detail="Container not found")
        
        container = docker_client.containers.get(container_id)
        image_tag = container.image.tags[0]
        packages = image_tag.split(":")[-1].split(",")
        
        # Try to get the code from the container
        code = None
        try:
            result = container.exec_run("cat /tmp/code.py")
            if result.exit_code == 0:
                code = result.output.decode()
        except Exception:
            pass
        
        return ContainerResponse(
            container_id=container_id,
            name=container_names.get(container_id, "Unnamed"),
            packages=packages,
            created_at=container.attrs['Created'],
            code=code
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/containers/{container_id}")
async def delete_container(container_id: str):
    """
    Delete a specific container.
    """
    try:
        if container_id in executor.containers.values():
            container = docker_client.containers.get(container_id)
            container.stop()
            container.remove()
            # Remove from our tracking
            for package_hash, cid in list(executor.containers.items()):
                if cid == container_id:
                    del executor.containers[package_hash]
            # Remove from names
            if container_id in container_names:
                del container_names[container_id]
            return {"message": f"Container {container_id} deleted successfully"}
        raise HTTPException(status_code=404, detail="Container not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/execute")
async def execute_code(request: CodeExecutionRequest, db: Session = Depends(get_db)):
    """
    Execute Python code in a container.
    If container_id is provided, use that container.
    Otherwise, create a new container with the specified packages.
    """
    start_time = time.time()
    try:
        # If code is not provided in request but we have a job_id, get code from the job
        if not request.code and hasattr(request, 'job_id'):
            job = db.query(ScheduledJob).filter(ScheduledJob.id == request.job_id).first()
            if job:
                request.code = job.code
            else:
                raise HTTPException(status_code=404, detail="Job not found")
        
        if not request.code:
            raise HTTPException(status_code=400, detail="Code is required")

        if request.container_id:
            # Verify container exists
            if request.container_id not in executor.containers.values():
                raise HTTPException(status_code=404, detail="Container not found")
            
            # Execute in existing container
            try:
                container = docker_client.containers.get(request.container_id)
            except docker.errors.NotFound:
                raise HTTPException(status_code=404, detail="Container not found in Docker")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error accessing container: {str(e)}")
            
            # Get environment variables
            env_manager = get_env_manager()
            env_vars = env_manager.get_all_variables()
            
            # Encode the code in base64
            encoded_code = base64.b64encode(request.code.encode()).decode()
            
            # Execute with environment variables
            result = container.exec_run(
                f"python -c 'import base64; exec(base64.b64decode(\"{encoded_code}\").decode())'",
                environment=env_vars
            )
            
            output = result.output.decode() if result.exit_code == 0 else None
            error = result.output.decode() if result.exit_code != 0 else None
            
            # Log the execution
            log = ExecutionLog(
                job_id=request.job_id if hasattr(request, 'job_id') else None,
                code=request.code,
                output=output,
                error=error,
                container_id=request.container_id,
                execution_time=time.time() - start_time,
                started_at=datetime.utcnow(),
                status="success" if result.exit_code == 0 else "error"
            )
            db.add(log)
            db.commit()
            
            return {
                "success": result.exit_code == 0,
                "output": output,
                "error": error,
                "container_id": request.container_id,
                "container_name": container_names.get(request.container_id, "Unnamed")
            }
        else:
            # Create a new container with packages
            if not request.packages:
                request.packages = []
            
            package_hash = executor._get_package_hash(request.packages)
            image_tag = executor._build_image(request.packages)
            
            # Create container if it doesn't exist
            if package_hash not in executor.containers:
                container = docker_client.containers.run(
                    image_tag,
                    detach=True,
                    tty=True,
                    mem_limit="512m",
                    cpu_period=100000,
                    cpu_quota=50000
                )
                executor.containers[package_hash] = container.id
            
            container_id = executor.containers[package_hash]
            
            # Get environment variables
            env_manager = get_env_manager()
            env_vars = env_manager.get_all_variables()
            
            # Execute with environment variables
            try:
                container = docker_client.containers.get(container_id)
            except docker.errors.NotFound:
                raise HTTPException(status_code=500, detail="Container was created but not found in Docker")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error accessing container: {str(e)}")
            encoded_code = base64.b64encode(request.code.encode()).decode()
            
            result = container.exec_run(
                f"python -c 'import base64; exec(base64.b64decode(\"{encoded_code}\").decode())'",
                environment=env_vars
            )
            
            output = result.output.decode() if result.exit_code == 0 else None
            error = result.output.decode() if result.exit_code != 0 else None
            
            # Log the execution
            log = ExecutionLog(
                job_id=request.job_id if hasattr(request, 'job_id') else None,
                code=request.code,
                output=output,
                error=error,
                container_id=container_id,
                execution_time=time.time() - start_time,
                started_at=datetime.utcnow(),
                status="success" if result.exit_code == 0 else "error"
            )
            db.add(log)
            db.commit()
            
            return {
                "success": result.exit_code == 0,
                "output": output,
                "error": error,
                "container_id": container_id,
                "container_name": container_names.get(container_id, "Unnamed")
            }
    except HTTPException:
        # Re-raise HTTPExceptions (like 404, 400, etc.) without catching them
        raise
    except Exception as e:
        # Create a more descriptive error message
        error_msg = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
        
        # Log the error with safe attribute access
        try:
            log = ExecutionLog(
                job_id=getattr(request, 'job_id', None) if 'request' in locals() else None,
                code=getattr(request, 'code', None) if 'request' in locals() else None,
                error=error_msg,
                execution_time=time.time() - start_time,
                started_at=datetime.utcnow(),
                status="error"
            )
            db.add(log)
            db.commit()
        except Exception as log_error:
            # If logging fails, at least print the error
            print(f"Failed to log error: {log_error}")
            print(f"Original error: {error_msg}")
        
        raise HTTPException(status_code=500, detail=error_msg)

@app.delete("/containers")
async def cleanup_all():
    """
    Clean up all containers.
    """
    try:
        executor.cleanup()
        container_names.clear()
        return {"message": "All containers cleaned up successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/jobs", response_model=ScheduledJobResponse)
async def create_scheduled_job(request: ScheduledJobRequest, db: Session = Depends(get_db)):
    """Create a new scheduled job."""
    try:
        # Create job in database
        db_job = ScheduledJob(
            name=request.name,
            code=request.code,
            cron_expression=request.cron_expression,
            packages=','.join(request.packages) if request.packages else None,
            container_id=request.container_id,
            created_at=datetime.now(),
            is_active=True
        )
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        
        # The scheduler will pick up the new job through load_existing_jobs
        scheduler.load_existing_jobs()
        
        # Convert datetime fields to ISO format strings for response
        return {
            "id": db_job.id,
            "name": db_job.name,
            "code": db_job.code,
            "cron_expression": db_job.cron_expression,
            "packages": db_job.packages,
            "container_id": db_job.container_id,
            "created_at": db_job.created_at.isoformat(),
            "last_run": db_job.last_run.isoformat() if db_job.last_run else None,
            "is_active": db_job.is_active
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jobs", response_model=List[ScheduledJobResponse])
async def list_scheduled_jobs(db: Session = Depends(get_db)):
    """List all scheduled jobs."""
    jobs = db.query(ScheduledJob).all()
    # Convert datetime fields to ISO format strings
    return [
        {
            "id": job.id,
            "name": job.name,
            "code": job.code,
            "cron_expression": job.cron_expression,
            "packages": job.packages,
            "container_id": job.container_id,
            "created_at": job.created_at.isoformat(),
            "last_run": job.last_run.isoformat() if job.last_run else None,
            "is_active": job.is_active
        }
        for job in jobs
    ]

@app.get("/jobs/{job_id}", response_model=ScheduledJobResponse)
async def get_scheduled_job(job_id: int, db: Session = Depends(get_db)):
    """Get a specific scheduled job."""
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.put("/jobs/{job_id}", response_model=ScheduledJobResponse)
async def update_scheduled_job(job_id: int, request: ScheduledJobRequest, db: Session = Depends(get_db)):
    """Update a scheduled job."""
    try:
        job = scheduler.update_job(
            job_id,
            name=request.name,
            code=request.code,
            cron_expression=request.cron_expression,
            container_id=request.container_id,
            packages=','.join(request.packages) if request.packages else None
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/jobs/{job_id}")
async def delete_scheduled_job(job_id: int):
    """Delete a scheduled job."""
    try:
        scheduler.delete_job(job_id)
        return {"message": "Job deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Webhook Jobs endpoints
@app.post("/webhook-jobs", response_model=WebhookJobResponse)
async def create_webhook_job(request: WebhookJobRequest, db: Session = Depends(get_db)):
    """Create a new webhook job."""
    try:
        # Validate endpoint format
        if not request.endpoint.startswith('/'):
            request.endpoint = '/' + request.endpoint
        
        # Check if endpoint already exists
        existing = db.query(WebhookJob).filter(WebhookJob.endpoint == request.endpoint).first()
        if existing:
            raise HTTPException(status_code=400, detail="Endpoint already exists")
        
        # Create job in database
        db_job = WebhookJob(
            name=request.name,
            endpoint=request.endpoint,
            code=request.code,
            packages=','.join(request.packages) if request.packages else None,
            container_id=request.container_id,
            timeout=request.timeout,
            description=request.description,
            created_at=datetime.now(),
            is_active=True
        )
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        
        return {
            "id": db_job.id,
            "name": db_job.name,
            "endpoint": db_job.endpoint,
            "code": db_job.code,
            "packages": db_job.packages,
            "container_id": db_job.container_id,
            "created_at": db_job.created_at.isoformat(),
            "last_triggered": db_job.last_triggered.isoformat() if db_job.last_triggered else None,
            "is_active": db_job.is_active,
            "timeout": db_job.timeout,
            "description": db_job.description
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/webhook-jobs", response_model=List[WebhookJobResponse])
async def list_webhook_jobs(db: Session = Depends(get_db)):
    """List all webhook jobs."""
    jobs = db.query(WebhookJob).all()
    return [
        {
            "id": job.id,
            "name": job.name,
            "endpoint": job.endpoint,
            "code": job.code,
            "packages": job.packages,
            "container_id": job.container_id,
            "created_at": job.created_at.isoformat(),
            "last_triggered": job.last_triggered.isoformat() if job.last_triggered else None,
            "is_active": job.is_active,
            "timeout": job.timeout,
            "description": job.description
        }
        for job in jobs
    ]

@app.get("/webhook-jobs/{job_id}", response_model=WebhookJobResponse)
async def get_webhook_job(job_id: int, db: Session = Depends(get_db)):
    """Get a specific webhook job."""
    job = db.query(WebhookJob).filter(WebhookJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Webhook job not found")
    return {
        "id": job.id,
        "name": job.name,
        "endpoint": job.endpoint,
        "code": job.code,
        "packages": job.packages,
        "container_id": job.container_id,
        "created_at": job.created_at.isoformat(),
        "last_triggered": job.last_triggered.isoformat() if job.last_triggered else None,
        "is_active": job.is_active,
        "timeout": job.timeout,
        "description": job.description
    }

@app.put("/webhook-jobs/{job_id}", response_model=WebhookJobResponse)
async def update_webhook_job(job_id: int, request: WebhookJobRequest, db: Session = Depends(get_db)):
    """Update a webhook job."""
    try:
        job = db.query(WebhookJob).filter(WebhookJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Webhook job not found")
        
        # Validate endpoint format
        if not request.endpoint.startswith('/'):
            request.endpoint = '/' + request.endpoint
        
        # Check if endpoint already exists (excluding current job)
        existing = db.query(WebhookJob).filter(
            WebhookJob.endpoint == request.endpoint,
            WebhookJob.id != job_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Endpoint already exists")
        
        # Update job
        job.name = request.name
        job.endpoint = request.endpoint
        job.code = request.code
        job.packages = ','.join(request.packages) if request.packages else None
        job.container_id = request.container_id
        job.timeout = request.timeout
        job.description = request.description
        
        db.commit()
        db.refresh(job)
        
        return {
            "id": job.id,
            "name": job.name,
            "endpoint": job.endpoint,
            "code": job.code,
            "packages": job.packages,
            "container_id": job.container_id,
            "created_at": job.created_at.isoformat(),
            "last_triggered": job.last_triggered.isoformat() if job.last_triggered else None,
            "is_active": job.is_active,
            "timeout": job.timeout,
            "description": job.description
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/webhook-jobs/{job_id}")
async def delete_webhook_job(job_id: int, db: Session = Depends(get_db)):
    """Delete a webhook job."""
    try:
        job = db.query(WebhookJob).filter(WebhookJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Webhook job not found")
        
        db.delete(job)
        db.commit()
        return {"message": "Webhook job deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Dynamic webhook execution endpoint
@app.api_route("/webhook/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def execute_webhook(path: str, request: Request, db: Session = Depends(get_db)):
    """
    Dynamic endpoint that executes webhook jobs based on the path.
    Supports all HTTP methods and passes request data to the code.
    """
    start_time = time.time()
    endpoint = f"/{path}"
    
    try:
        # Find the webhook job
        job = db.query(WebhookJob).filter(
            WebhookJob.endpoint == endpoint,
            WebhookJob.is_active == 1
        ).first()
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Webhook endpoint '{endpoint}' not found")
        
        # Get request data
        request_method = request.method
        request_headers = dict(request.headers)
        request_query_params = dict(request.query_params)
        
        # Get request body
        request_body = None
        try:
            if request_method in ["POST", "PUT", "PATCH"]:
                content_type = request_headers.get("content-type", "")
                if "application/json" in content_type:
                    request_body = await request.json()
                elif "application/x-www-form-urlencoded" in content_type:
                    form_data = await request.form()
                    request_body = dict(form_data)
                else:
                    request_body = (await request.body()).decode()
        except Exception as e:
            print(f"Error parsing request body: {e}")
            request_body = None
        
        # Prepare the execution context
        request_data = {
            "method": request_method,
            "headers": request_headers,
            "query_params": request_query_params,
            "body": request_body,
            "endpoint": endpoint
        }
        
        # Prepare the code with request context
        # Encode the request data safely using base64
        request_data_encoded = base64.b64encode(json.dumps(request_data).encode()).decode()
        
        # The webhook code will have access to 'request_data' and should set 'response_data'
        wrapper_code = f"""
import json
import sys
import base64
from datetime import datetime

# Request data available to the webhook code (safely decoded from base64)
request_data = json.loads(base64.b64decode("{request_data_encoded}").decode())

# Default response
response_data = {{"message": "Webhook executed successfully", "timestamp": datetime.now().isoformat()}}

# User's webhook code
try:
{chr(10).join("    " + line for line in job.code.split(chr(10)))}
except Exception as e:
    response_data = {{"error": str(e), "timestamp": datetime.now().isoformat()}}
    print(f"Error in webhook code: {{e}}", file=sys.stderr)

# Output the response (this will be captured and returned)
print(json.dumps(response_data))
"""
        
        # Execute the webhook code
        if job.container_id:
            # Use existing container
            if job.container_id not in executor.containers.values():
                raise HTTPException(status_code=500, detail="Webhook job container not found")
            
            container = docker_client.containers.get(job.container_id)
        else:
            # Create/get container with packages
            packages = []
            if job.packages and job.packages.strip():
                packages = [pkg.strip() for pkg in job.packages.split(',') if pkg.strip()]
            
            package_hash = executor._get_package_hash(packages)
            image_tag = executor._build_image(packages)
            
            if package_hash not in executor.containers:
                container = docker_client.containers.run(
                    image_tag,
                    detach=True,
                    tty=True,
                    mem_limit="512m",
                    cpu_period=100000,
                    cpu_quota=50000
                )
                executor.containers[package_hash] = container.id
            
            container_id = executor.containers[package_hash]
            container = docker_client.containers.get(container_id)
        
        # Get environment variables
        env_manager = get_env_manager()
        env_vars = env_manager.get_all_variables()
        
        # Execute with timeout (support infinite timeout with -1)
        encoded_code = base64.b64encode(wrapper_code.encode()).decode()
        
        if job.timeout == -1:
            # Infinite timeout - no timeout command
            exec_command = f"python -c 'import base64; exec(base64.b64decode(\"{encoded_code}\").decode())'"
        else:
            # Normal timeout
            exec_command = f"timeout {job.timeout} python -c 'import base64; exec(base64.b64decode(\"{encoded_code}\").decode())'"
        
        result = container.exec_run(
            exec_command,
            environment=env_vars
        )
        
        # Parse the output
        success = result.exit_code == 0
        output = result.output.decode() if result.output else ""
        
        # Try to parse the response data from output
        response_data = None
        if success and output.strip():
            try:
                # The last line should be the JSON response
                lines = output.strip().split('\n')
                for line in reversed(lines):
                    line = line.strip()
                    if line.startswith('{') and line.endswith('}'):
                        response_data = json.loads(line)
                        break
            except Exception as e:
                print(f"Error parsing webhook response: {e}")
                response_data = {"output": output}
        
        if not response_data:
            response_data = {
                "success": success,
                "output": output if success else None,
                "error": output if not success else None
            }
        
        # Update job last triggered time
        job.last_triggered = datetime.utcnow()
        db.commit()
        
        # Log the execution
        log = ExecutionLog(
            webhook_job_id=job.id,
            code=job.code,
            output=json.dumps(response_data) if success else None,
            error=output if not success else None,
            container_id=container.id,
            execution_time=time.time() - start_time,
            started_at=datetime.utcnow(),
            status="success" if success else "error",
            request_data=json.dumps(request_data),
            response_data=json.dumps(response_data) if success else None
        )
        db.add(log)
        db.commit()
        
        # Return the response
        if success:
            return response_data
        else:
            raise HTTPException(status_code=500, detail=response_data.get("error", "Webhook execution failed"))
            
    except HTTPException:
        raise
    except Exception as e:
        # Log the error
        log = ExecutionLog(
            webhook_job_id=job.id if 'job' in locals() else None,
            code=job.code if 'job' in locals() else "",
            error=str(e),
            execution_time=time.time() - start_time,
            started_at=datetime.utcnow(),
            status="error",
            request_data=json.dumps(request_data) if 'request_data' in locals() else None
        )
        db.add(log)
        db.commit()
        
        raise HTTPException(status_code=500, detail=str(e))

# Persistent Services endpoints
@app.post("/services", response_model=PersistentServiceResponse)
async def create_persistent_service(request: PersistentServiceRequest, db: Session = Depends(get_db)):
    """Create a new persistent service."""
    try:
        # Check if name already exists
        existing = db.query(PersistentService).filter(PersistentService.name == request.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Service name already exists")
        
        # Create service in database
        db_service = PersistentService(
            name=request.name,
            code=request.code,
            packages=','.join(request.packages) if request.packages else None,
            container_id=request.container_id,
            restart_policy=request.restart_policy,
            description=request.description,
            auto_start=1 if request.auto_start else 0,
            created_at=datetime.now(),
            is_active=True,
            status="stopped"
        )
        db.add(db_service)
        db.commit()
        db.refresh(db_service)
        
        return {
            "id": db_service.id,
            "name": db_service.name,
            "code": db_service.code,
            "packages": db_service.packages,
            "container_id": db_service.container_id,
            "created_at": db_service.created_at.isoformat(),
            "started_at": db_service.started_at.isoformat() if db_service.started_at else None,
            "last_restart": db_service.last_restart.isoformat() if db_service.last_restart else None,
            "is_active": db_service.is_active,
            "status": db_service.status,
            "restart_policy": db_service.restart_policy,
            "description": db_service.description,
            "process_id": db_service.process_id,
            "auto_start": bool(db_service.auto_start)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/services", response_model=List[PersistentServiceResponse])
async def list_persistent_services(db: Session = Depends(get_db)):
    """List all persistent services."""
    services = db.query(PersistentService).all()
    return [
        {
            "id": service.id,
            "name": service.name,
            "code": service.code,
            "packages": service.packages,
            "container_id": service.container_id,
            "created_at": service.created_at.isoformat(),
            "started_at": service.started_at.isoformat() if service.started_at else None,
            "last_restart": service.last_restart.isoformat() if service.last_restart else None,
            "is_active": service.is_active,
            "status": service.status,
            "restart_policy": service.restart_policy,
            "description": service.description,
            "process_id": service.process_id,
            "auto_start": bool(service.auto_start)
        }
        for service in services
    ]

@app.get("/services/{service_id}", response_model=PersistentServiceResponse)
async def get_persistent_service(service_id: int, db: Session = Depends(get_db)):
    """Get a specific persistent service."""
    service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return {
        "id": service.id,
        "name": service.name,
        "code": service.code,
        "packages": service.packages,
        "container_id": service.container_id,
        "created_at": service.created_at.isoformat(),
        "started_at": service.started_at.isoformat() if service.started_at else None,
        "last_restart": service.last_restart.isoformat() if service.last_restart else None,
        "is_active": service.is_active,
        "status": service.status,
        "restart_policy": service.restart_policy,
        "description": service.description,
        "process_id": service.process_id,
        "auto_start": bool(service.auto_start)
    }

@app.put("/services/{service_id}", response_model=PersistentServiceResponse)
async def update_persistent_service(service_id: int, request: PersistentServiceRequest, db: Session = Depends(get_db)):
    """Update a persistent service."""
    try:
        service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        
        # Check if name already exists (excluding current service)
        existing = db.query(PersistentService).filter(
            PersistentService.name == request.name,
            PersistentService.id != service_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Service name already exists")
        
        # Update service
        service.name = request.name
        service.code = request.code
        service.packages = ','.join(request.packages) if request.packages else None
        service.container_id = request.container_id
        service.restart_policy = request.restart_policy
        service.description = request.description
        service.auto_start = 1 if request.auto_start else 0
        
        db.commit()
        db.refresh(service)
        
        return {
            "id": service.id,
            "name": service.name,
            "code": service.code,
            "packages": service.packages,
            "container_id": service.container_id,
            "created_at": service.created_at.isoformat(),
            "started_at": service.started_at.isoformat() if service.started_at else None,
            "last_restart": service.last_restart.isoformat() if service.last_restart else None,
            "is_active": service.is_active,
            "status": service.status,
            "restart_policy": service.restart_policy,
            "description": service.description,
            "process_id": service.process_id,
            "auto_start": bool(service.auto_start)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/services/{service_id}")
async def delete_persistent_service(service_id: int, db: Session = Depends(get_db)):
    """Delete a persistent service."""
    try:
        service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        
        # Stop the service first
        service_manager.stop_service(service_id, db)
        
        # Delete from database
        db.delete(service)
        db.commit()
        return {"message": "Service deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Service control endpoints
@app.post("/services/{service_id}/start")
async def start_persistent_service(service_id: int, db: Session = Depends(get_db)):
    """Start a persistent service."""
    try:
        success = service_manager.start_service(service_id, db)
        if success:
            return {"message": "Service start initiated"}
        else:
            raise HTTPException(status_code=404, detail="Service not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/services/{service_id}/stop")
async def stop_persistent_service(service_id: int, db: Session = Depends(get_db)):
    """Stop a persistent service."""
    try:
        success = service_manager.stop_service(service_id, db)
        if success:
            return {"message": "Service stopped"}
        else:
            raise HTTPException(status_code=404, detail="Service not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/services/{service_id}/restart")
async def restart_persistent_service(service_id: int, db: Session = Depends(get_db)):
    """Restart a persistent service."""
    try:
        success = service_manager.restart_service(service_id, db)
        if success:
            return {"message": "Service restart initiated"}
        else:
            raise HTTPException(status_code=404, detail="Service not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/services/{service_id}/logs")
async def get_service_logs(service_id: int, limit: int = 100, db: Session = Depends(get_db)):
    """Get logs for a specific service."""
    try:
        service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        
        # If service is running, get live logs from container
        if service.status == "running" and service.container_id:
            try:
                container = docker_client.containers.get(service.container_id)
                logs = container.logs(tail=limit, timestamps=True).decode()
                return {"logs": logs, "service_id": service_id, "status": "live"}
            except Exception as e:
                return {"logs": f"Error fetching live logs: {e}", "service_id": service_id, "status": "error"}
        
        return {"logs": "Service not running", "service_id": service_id, "status": "stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs", response_model=List[ExecutionLogResponse])
async def get_execution_logs(
    job_id: Optional[int] = None,
    webhook_job_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get execution logs with optional filtering."""
    query = db.query(ExecutionLog)
    if job_id is not None:
        query = query.filter(ExecutionLog.job_id == job_id)
    if webhook_job_id is not None:
        query = query.filter(ExecutionLog.webhook_job_id == webhook_job_id)
    logs = query.order_by(ExecutionLog.started_at.desc()).offset(offset).limit(limit).all()
    
    # Convert logs to response format with datetime as ISO string
    return [
        {
            "id": log.id,
            "job_id": log.job_id,
            "webhook_job_id": log.webhook_job_id,
            "code": log.code,
            "output": log.output,
            "error": log.error,
            "container_id": log.container_id,
            "execution_time": log.execution_time,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "status": log.status,
            "request_data": log.request_data,
            "response_data": log.response_data
        }
        for log in logs
    ]

@app.get("/logs/{log_id}", response_model=ExecutionLogResponse)
async def get_execution_log(log_id: int, db: Session = Depends(get_db)):
    """Get a specific execution log."""
    log = db.query(ExecutionLog).filter(ExecutionLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    
    # Convert log to response format with datetime as ISO string
    return {
        "id": log.id,
        "job_id": log.job_id,
        "webhook_job_id": log.webhook_job_id,
        "code": log.code,
        "output": log.output,
        "error": log.error,
        "container_id": log.container_id,
        "execution_time": log.execution_time,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "status": log.status,
        "request_data": log.request_data,
        "response_data": log.response_data
    }

@app.post("/env", response_model=EnvVarResponse)
async def set_environment_variable(request: EnvVarRequest, db: Session = Depends(get_db)):
    """Set an environment variable."""
    manager = get_env_manager()
    manager.set_variable(request.name, request.value, request.description)
    var = db.query(EnvironmentVariable).filter_by(name=request.name).first()
    return EnvVarResponse(
        name=var.name,
        created_at=var.created_at.isoformat(),
        updated_at=var.updated_at.isoformat()
    )

@app.get("/env", response_model=List[str])
async def list_environment_variables():
    """List all environment variable names."""
    manager = get_env_manager()
    return manager.list_variables()

@app.get("/env/{name}")
async def get_environment_variable(name: str):
    """Get an environment variable value."""
    manager = get_env_manager()
    value = manager.get_variable(name)
    if value is None:
        raise HTTPException(status_code=404, detail="Environment variable not found")
    return {"name": name, "value": value}

@app.delete("/env/{name}")
async def delete_environment_variable(name: str):
    """Delete an environment variable."""
    manager = get_env_manager()
    if not manager.delete_variable(name):
        raise HTTPException(status_code=404, detail="Environment variable not found")
    return {"message": f"Environment variable {name} deleted successfully"}

@app.get("/env-metadata", response_model=List[EnvVarMetadata])
async def list_environment_variable_metadata():
    """List all environment variable metadata without values."""
    manager = get_env_manager()
    return manager.list_variables_with_metadata()

@app.get("/env-metadata/{name}", response_model=EnvVarMetadata)
async def get_environment_variable_metadata(name: str):
    """Get an environment variable metadata without value."""
    manager = get_env_manager()
    metadata = manager.get_variable_metadata(name)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Environment variable not found")
    return metadata

async def startup_event():
    """Initialize services on startup."""
    try:
        # Run database migration
        from migrate_database import migrate_database
        migrate_database()
        print("Database migration completed")
        
        # Auto-start services marked for auto-start
        db = SessionLocal()
        try:
            auto_start_services = db.query(PersistentService).filter(
                PersistentService.auto_start == 1,
                PersistentService.is_active == 1
            ).all()
            
            for service in auto_start_services:
                print(f"Auto-starting service: {service.name}")
                service_manager.start_service(service.id, db)
        finally:
            db.close()
            
    except Exception as e:
        print(f"Startup error: {e}")

# Add startup event
@app.on_event("startup")
async def on_startup():
    await startup_event()

if __name__ == "__main__":
    # Create static directory if it doesn't exist
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000) 