from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import time
import base64
from datetime import datetime
import docker
from models.schemas import CodeExecutionRequest
from models import ScheduledJob, ExecutionLog
from database import get_db
from services.docker_client import docker_client
from code_executor import CodeExecutor
from env_manager import EnvironmentManager
import os

router = APIRouter(tags=["execution"])

# Initialize executor
executor = CodeExecutor()

# Container names (should be shared with containers router, but for now duplicated)
container_names = {}  # container_id -> name

def get_env_manager():
    """Get environment manager instance."""
    from models import SessionLocal
    db = SessionLocal()
    try:
        # Try to load existing key
        if os.path.exists('.env_key'):
            with open('.env_key', 'rb') as key_file:
                key = key_file.read()
        else:
            key = None
        env_manager = EnvironmentManager(db, key)
        return env_manager
    finally:
        db.close()

@router.post("/execute")
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