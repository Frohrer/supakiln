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

app = FastAPI(title="Code Execution Engine API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files - update the path to be relative to the current file
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize executor with error handling
try:
    executor = CodeExecutor()
except docker.errors.DockerException as e:
    print(f"Error initializing Docker: {str(e)}")
    print("Please ensure Docker is running and you have the necessary permissions.")
    raise

class CodeExecutionRequest(BaseModel):
    code: str
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

# Store container names
container_names = {}  # container_id -> name

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
            container = executor.client.containers.run(
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
            packages=request.packages
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
            container = executor.client.containers.get(container_id)
            # Extract packages from image tag
            image_tag = container.image.tags[0]
            packages = image_tag.split(":")[-1].split(",")
            containers.append(ContainerResponse(
                container_id=container_id,
                name=container_names.get(container_id, "Unnamed"),
                packages=packages
            ))
        except Exception:
            continue
    return containers

@app.delete("/containers/{container_id}")
async def delete_container(container_id: str):
    """
    Delete a specific container.
    """
    try:
        if container_id in executor.containers.values():
            container = executor.client.containers.get(container_id)
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
async def execute_code(request: CodeExecutionRequest):
    """
    Execute Python code in a container.
    If container_id is provided, use that container.
    Otherwise, create a new container with the specified packages.
    """
    try:
        if request.container_id:
            # Verify container exists
            if request.container_id not in executor.containers.values():
                raise HTTPException(status_code=404, detail="Container not found")
            
            # Execute in existing container
            container = executor.client.containers.get(request.container_id)
            
            # Create a temporary file with the code
            temp_file = f"/tmp/code_{int(time.time())}.py"
            write_command = f"echo '{request.code.replace("'", "'\\''")}' > {temp_file}"
            try:
                write_result = container.exec_run(write_command, timeout=request.timeout)
                if write_result.exit_code != 0:
                    return {
                        "success": False,
                        "output": None,
                        "error": f"Failed to write code to file: {write_result.output.decode()}",
                        "container_id": request.container_id,
                        "container_name": container_names.get(request.container_id, "Unnamed")
                    }
                
                # Execute the code file
                exec_result = container.exec_run(
                    f"python3 {temp_file}",
                    timeout=request.timeout
                )
                
                # Clean up the temporary file
                container.exec_run(f"rm {temp_file}", timeout=5)
                
                return {
                    "success": exec_result.exit_code == 0,
                    "output": exec_result.output.decode(),
                    "error": None if exec_result.exit_code == 0 else exec_result.output.decode(),
                    "container_id": request.container_id,
                    "container_name": container_names.get(request.container_id, "Unnamed")
                }
            except Exception as e:
                # Clean up container on error
                try:
                    container.stop()
                    container.remove()
                    # Remove from our tracking
                    for package_hash, cid in list(executor.containers.items()):
                        if cid == request.container_id:
                            del executor.containers[package_hash]
                    if request.container_id in container_names:
                        del container_names[request.container_id]
                except Exception:
                    pass
                
                return {
                    "success": False,
                    "output": None,
                    "error": str(e),
                    "container_id": request.container_id,
                    "container_name": container_names.get(request.container_id, "Unnamed")
                }
        else:
            # Create new container and execute
            result = executor.execute_code(
                code=request.code,
                packages=request.packages or [],
                timeout=request.timeout
            )
            
            # If execution failed or timed out, clean up the container
            if not result.get("success"):
                container_id = result.get("container_id")
                if container_id:
                    try:
                        container = executor.client.containers.get(container_id)
                        container.stop()
                        container.remove()
                        # Remove from our tracking
                        for package_hash, cid in list(executor.containers.items()):
                            if cid == container_id:
                                del executor.containers[package_hash]
                        if container_id in container_names:
                            del container_names[container_id]
                    except Exception:
                        pass
            
            return result
    except docker.errors.ImageNotFound:
        raise HTTPException(
            status_code=500,
            detail="Failed to build container image. Please ensure Docker is running and you have the necessary permissions."
        )
    except Exception as e:
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
        job = scheduler.add_job(
            name=request.name,
            code=request.code,
            cron_expression=request.cron_expression,
            container_id=request.container_id,
            packages=request.packages
        )
        return job
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jobs", response_model=List[ScheduledJobResponse])
async def list_scheduled_jobs(db: Session = Depends(get_db)):
    """List all scheduled jobs."""
    jobs = db.query(ScheduledJob).all()
    return jobs

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
    return logs

@app.get("/logs/{log_id}", response_model=ExecutionLogResponse)
async def get_execution_log(log_id: int, db: Session = Depends(get_db)):
    """Get a specific execution log."""
    log = db.query(ExecutionLog).filter(ExecutionLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    return log

if __name__ == "__main__":
    # Create static directory if it doesn't exist
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000) 