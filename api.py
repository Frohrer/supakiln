from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import uvicorn
from code_executor import CodeExecutor
import docker
import os
from models import SessionLocal, ScheduledJob, ExecutionLog
from scheduler import scheduler
from sqlalchemy.orm import Session
import time
from datetime import datetime
import base64
from env_manager import EnvironmentManager, EnvironmentVariable

app = FastAPI(title="Code Execution Engine API")

# Get all allowed origins from environment variables
allowed_origins = [
    origin.strip()
    for origin in os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
]

# Add CORS middleware with more permissive settings for Cloudflare Access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins temporarily for debugging
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,  # Cache preflight requests for 24 hours
)

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
    code: str
    output: Optional[str]
    error: Optional[str]
    container_id: Optional[str]
    execution_time: float
    started_at: str
    status: str

class EnvVarRequest(BaseModel):
    name: str
    value: str

class EnvVarResponse(BaseModel):
    name: str
    created_at: str
    updated_at: str

# Store container names
container_names = {}  # container_id -> name

# Initialize environment manager
env_manager = None

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
            result = container.exec_run("cat /tmp/code.py", timeout=5)
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
            container = docker_client.containers.get(request.container_id)
            
            # Get environment variables
            env_manager = get_env_manager()
            env_vars = env_manager.get_all_variables()
            
            # Encode the code in base64
            encoded_code = base64.b64encode(request.code.encode()).decode()
            
            # Execute with environment variables
            result = container.exec_run(
                f"python -c 'import base64; exec(base64.b64decode(\"{encoded_code}\").decode())'",
                environment=env_vars,
                timeout=request.timeout
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
            container = docker_client.containers.get(container_id)
            encoded_code = base64.b64encode(request.code.encode()).decode()
            
            result = container.exec_run(
                f"python -c 'import base64; exec(base64.b64decode(\"{encoded_code}\").decode())'",
                environment=env_vars,
                timeout=request.timeout
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
    except Exception as e:
        # Log the error
        log = ExecutionLog(
            job_id=request.job_id if hasattr(request, 'job_id') else None,
            code=request.code,
            error=str(e),
            execution_time=time.time() - start_time,
            started_at=datetime.utcnow(),
            status="error"
        )
        db.add(log)
        db.commit()
        
        raise HTTPException(status_code=500, detail=str(e))

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

@app.get("/logs", response_model=List[ExecutionLogResponse])
async def get_execution_logs(
    job_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get execution logs with optional filtering."""
    query = db.query(ExecutionLog)
    if job_id is not None:
        query = query.filter(ExecutionLog.job_id == job_id)
    logs = query.order_by(ExecutionLog.started_at.desc()).offset(offset).limit(limit).all()
    
    # Convert logs to response format with datetime as ISO string
    return [
        {
            **log.__dict__,
            'started_at': log.started_at.isoformat() if log.started_at else None
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
        **log.__dict__,
        'started_at': log.started_at.isoformat() if log.started_at else None
    }

@app.post("/env", response_model=EnvVarResponse)
async def set_environment_variable(request: EnvVarRequest, db: Session = Depends(get_db)):
    """Set an environment variable."""
    manager = get_env_manager()
    manager.set_variable(request.name, request.value)
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

if __name__ == "__main__":
    # Create static directory if it doesn't exist
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000) 