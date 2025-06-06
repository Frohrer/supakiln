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
            container = executor.client.containers.get(container_id)
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
        
        container = executor.client.containers.get(container_id)
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
            container = executor.client.containers.get(request.container_id)
            
            # Encode the code in base64
            encoded_code = base64.b64encode(request.code.encode()).decode()
            
            try:
                # Execute the code directly by piping base64 decoded content to python
                exec_result = container.exec_run(
                    f"echo '{encoded_code}' | base64 -d | python3",
                    timeout=request.timeout
                )
                
                # Save the original code for future reference
                escaped_code = base64.b64encode(request.code.encode()).decode()
                container.exec_run(f"echo '{escaped_code}' | base64 -d > /tmp/code.py", timeout=5)
                
                success = exec_result.exit_code == 0
                output = exec_result.output.decode()
                error = None if success else output
                
                # Log the execution
                log = ExecutionLog(
                    code=request.code,  # Always include the code
                    output=output if success else None,
                    error=error,
                    container_id=request.container_id,
                    execution_time=time.time() - start_time,
                    status='success' if success else 'error'
                )
                db.add(log)
                db.commit()
                
                return {
                    "success": success,
                    "output": output,
                    "error": error,
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
                
                error_msg = str(e)
                # Log the error
                log = ExecutionLog(
                    code=request.code,  # Always include the code
                    error=error_msg,
                    container_id=request.container_id,
                    execution_time=time.time() - start_time,
                    status='error'
                )
                db.add(log)
                db.commit()
                
                return {
                    "success": False,
                    "output": None,
                    "error": error_msg,
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
            
            # Log the execution
            log = ExecutionLog(
                code=request.code,  # Always include the code
                output=result.get('output'),
                error=result.get('error'),
                container_id=result.get('container_id'),
                execution_time=time.time() - start_time,
                status='success' if result.get('success') else 'error'
            )
            db.add(log)
            db.commit()
            
            return result
    except HTTPException as e:
        # Don't log HTTP exceptions as they're expected errors
        raise e
    except Exception as e:
        error_msg = str(e)
        # Log the error
        log = ExecutionLog(
            code=request.code if request.code else "Error occurred before code execution",  # Provide a default message
            error=error_msg,
            execution_time=time.time() - start_time,
            status='error'
        )
        db.add(log)
        db.commit()
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

if __name__ == "__main__":
    # Create static directory if it doesn't exist
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000) 