from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
import time
import base64
import json
from datetime import datetime
from models import WebhookJob, ExecutionLog
from database import get_db
from services.code_executor_service import get_code_executor
from env_manager import EnvironmentManager
import os

router = APIRouter(prefix="/webhook", tags=["webhook-execution"])

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
        
        # Resolve language (backfill to python for rows predating the
        # `language` column).
        language = (getattr(job, "language", None) or "python")

        # Build the code that will run in the worker. For Python we keep
        # the historical contract: user code sees a `request_data` local
        # and writes back into `response_data`. For other languages, we
        # pass request data as SUPAKILN_REQUEST_DATA (JSON) and the user
        # code is responsible for parsing it + printing a JSON response
        # to stdout.
        request_data_json = json.dumps(request_data)
        if language == "python":
            request_data_b64 = base64.b64encode(request_data_json.encode()).decode()
            wrapper_code = (
                "import json\n"
                "import sys\n"
                "import base64\n"
                "from datetime import datetime\n"
                "\n"
                f'request_data = json.loads(base64.b64decode("{request_data_b64}").decode())\n'
                'response_data = {"message": "Webhook executed successfully", '
                '"timestamp": datetime.now().isoformat()}\n'
                "\n"
                "try:\n"
                + "\n".join("    " + line for line in job.code.split("\n"))
                + "\n"
                "except Exception as e:\n"
                '    response_data = {"error": str(e), "timestamp": datetime.now().isoformat()}\n'
                '    print(f"Error in webhook code: {e}", file=sys.stderr)\n'
                "\n"
                "print(json.dumps(response_data))\n"
            )
            code_to_run = wrapper_code
        else:
            # No auto-wrapping for non-Python; user emits JSON to stdout.
            code_to_run = job.code

        # Packages from the stored comma-separated string.
        packages: list = []
        if job.packages and job.packages.strip():
            packages = [pkg.strip() for pkg in job.packages.split(",") if pkg.strip()]

        # Environment variables: user's encrypted secrets + request data
        # for non-Python languages.
        env_manager = get_env_manager()
        env_vars = dict(env_manager.get_all_variables())
        if language != "python":
            env_vars["SUPAKILN_REQUEST_DATA"] = request_data_json

        # -1 means "no timeout"; treat as a very large number of seconds.
        timeout_s = 60 * 60 * 24 if job.timeout == -1 else int(job.timeout)

        exec_result = get_code_executor().execute_code(
            code=code_to_run,
            packages=packages,
            timeout=timeout_s,
            env_vars=env_vars,
            language=language,
        )

        success = bool(exec_result.get("success"))
        output = (exec_result.get("output") or "")
        error_output = exec_result.get("error") or ""
        container_id = exec_result.get("container_id")

        # Parse the last JSON-shaped line of stdout as the response body.
        response_data = None
        if output.strip():
            for line in reversed(output.strip().splitlines()):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        response_data = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
        if response_data is None:
            response_data = {
                "success": success,
                "output": output or None,
                "error": error_output or None,
            }

        # Update job last triggered time
        job.last_triggered = datetime.utcnow()
        db.commit()

        # Log the execution
        log = ExecutionLog(
            webhook_job_id=job.id,
            code=job.code,
            output=json.dumps(response_data) if success else None,
            error=error_output if not success else None,
            container_id=container_id,
            execution_time=time.time() - start_time,
            started_at=datetime.utcnow(),
            status="success" if success else "error",
            request_data=request_data_json,
            response_data=json.dumps(response_data) if success else None,
        )
        db.add(log)
        db.commit()

        if success:
            return response_data
        raise HTTPException(
            status_code=500,
            detail=response_data.get("error") or error_output or "Webhook execution failed",
        )
            
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