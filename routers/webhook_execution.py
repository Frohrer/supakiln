from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
import time
import base64
import json
from datetime import datetime
from models import WebhookJob, ExecutionLog
from database import get_db
from services.docker_client import docker_client
from code_executor import CodeExecutor
from env_manager import EnvironmentManager
import os

router = APIRouter(prefix="/webhook", tags=["webhook-execution"])

# Initialize executor
executor = CodeExecutor()

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

# Dynamic webhook execution endpoint
@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
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