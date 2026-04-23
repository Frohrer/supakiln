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
from services.code_executor_service import get_code_executor
import os

router = APIRouter(tags=["execution"])

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

@router.post("/execute-web-service", summary="Start a Python web service")
async def execute_web_service(request: CodeExecutionRequest, db: Session = Depends(get_db)):
    """Execute Python code and detect if it's a web framework (Streamlit,
    FastAPI, Flask, Dash, or Gradio) — if so, spin up a long-running
    container, publish its port, and return a `proxy_url` under `/proxy/...`.

    Effectively the same as `POST /execute` with `language=python`, but
    with a 60s timeout and no language selection. Use `/execute` for
    snippets; use this endpoint (or `POST /services`) for web apps.
    """
    start_time = time.time()
    try:
        if not request.code:
            raise HTTPException(status_code=400, detail="Code is required")
        
        if not request.packages:
            request.packages = []
            
        # Get environment variables
        env_manager = get_env_manager()
        env_vars = env_manager.get_all_variables()
        
        # Use the CodeExecutor method which handles web service detection
        result = get_code_executor().execute_code(
            code=request.code,
            packages=request.packages,
            timeout=60,  # Longer timeout for web services
            env_vars=env_vars
        )
        
        # Log the execution
        container_id = result.get("container_id")
        log = ExecutionLog(
            job_id=request.job_id if hasattr(request, 'job_id') else None,
            code=request.code,
            output=result.get("output"),
            error=result.get("error"),
            container_id=container_id,
            execution_time=time.time() - start_time,
            started_at=datetime.utcnow(),
            status="success" if result.get("success") else "error"
        )
        db.add(log)
        db.commit()
        
        return result
        
    except Exception as e:
        error_msg = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
        
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
            print(f"Failed to log error: {log_error}")
            print(f"Original error: {error_msg}")
        
        raise HTTPException(status_code=500, detail=error_msg)

@router.post("/execute", summary="Run code in the selected runtime")
async def execute_code(request: CodeExecutionRequest, db: Session = Depends(get_db)):
    """Execute a snippet in an isolated Docker container.

    Picks a runtime from `request.language` (default `python`; call
    `GET /languages` for the full list). The executor caches one worker
    container per `(language, package_hash)` so repeat calls against the
    same environment reuse a live HTTP worker — warm-path latency is
    typically 10–30ms for interpreted languages.

    **Body**
    - `code` *(required)* — the source to execute
    - `language` — `python` | `node` | `ruby` | `bash` | `go` (default `python`)
    - `packages` — list of package specifiers for the runtime's package
      manager (pip / npm / gem). Ignored for `bash` and `go`.
    - `timeout` — seconds (default 30)
    - `container_id` — if set, execute against an already-named container
      via the legacy docker-exec path (bypasses the worker cache)

    **Response**
    - `success`: `bool`
    - `output`: stdout as a string (or `null`)
    - `error`: stderr or failure reason (or `null`)
    - `container_id`: the worker container that ran this call
    - `timed_out`: `bool`
    - `timings_ms`: per-phase timing breakdown (cold vs. warm)
    - `web_service`: present only when Python web-framework detection
      fires; contains `type`, `external_port`, `proxy_url`

    Returns `400` if the language isn't registered; `500` on other failures.
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
            if request.container_id not in get_code_executor().containers.values():
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
            
            # Execute with streaming output and timeout handling
            output_buffer = []
            error_buffer = []
            success = False
            timed_out = False
            
            import threading
            import signal
            
            def collect_output():
                nonlocal success, timed_out
                try:
                    # Execute without streaming first to get exit code properly
                    result = container.exec_run(
                        f"python -c 'import base64; exec(base64.b64decode(\"{encoded_code}\").decode())'",
                        environment=env_vars,
                        stream=False,  # Don't stream to get proper exit code
                        demux=True    # Separate stdout and stderr
                    )
                    
                    # Process the output
                    if result.output:
                        stdout_data, stderr_data = result.output
                        if stdout_data:
                            output_buffer.append(stdout_data.decode('utf-8', errors='replace'))
                        if stderr_data:
                            error_buffer.append(stderr_data.decode('utf-8', errors='replace'))
                    
                    # Now we can reliably check the exit code
                    success = result.exit_code == 0
                    
                except Exception as e:
                    error_buffer.append(f"Execution error: {str(e)}")
                    success = False
            
            # Start output collection in a separate thread
            output_thread = threading.Thread(target=collect_output)
            output_thread.daemon = True
            output_thread.start()
            
            # Wait for completion or timeout
            timeout_seconds = request.timeout or 30
            output_thread.join(timeout_seconds)
            
            if output_thread.is_alive():
                # Thread is still running, so we timed out
                timed_out = True
                # Try to stop the execution in the container
                try:
                    # Kill the process in the container
                    container.exec_run("pkill -f python", detach=True)
                except:
                    pass
                
                # Give it a moment to clean up
                output_thread.join(1)
            
            # Combine output
            combined_output = ''.join(output_buffer) if output_buffer else None
            combined_error = ''.join(error_buffer) if error_buffer else None
            
            # If we timed out, add timeout message
            if timed_out:
                timeout_msg = f"\n--- Execution timed out after {timeout_seconds} seconds ---"
                if combined_output:
                    combined_output += timeout_msg
                elif combined_error:
                    combined_error += timeout_msg
                else:
                    combined_error = f"Execution timed out after {timeout_seconds} seconds"
                success = False
            
            # Log the execution
            log = ExecutionLog(
                job_id=request.job_id if hasattr(request, 'job_id') else None,
                code=request.code,
                output=combined_output,
                error=combined_error,
                container_id=request.container_id,
                execution_time=time.time() - start_time,
                started_at=datetime.utcnow(),
                status="success" if success and not timed_out else "error"
            )
            db.add(log)
            db.commit()
            
            return {
                "success": success and not timed_out,
                "output": combined_output,
                "error": combined_error,
                "container_id": request.container_id,
                "container_name": container_names.get(request.container_id, "Unnamed"),
                "timed_out": timed_out
            }
        else:
            # Use the CodeExecutor.execute_code method which handles web service detection
            if not request.packages:
                request.packages = []

            # Validate language up front so we can 400 instead of
            # bubbling up the KeyError as a 500.
            import languages as lang_registry
            language = request.language or "python"
            try:
                lang_registry.get(language)
            except KeyError:
                raise HTTPException(
                    status_code=400,
                    detail=f"unknown language {language!r}; known: {lang_registry.names()}",
                )

            # Get environment variables
            env_manager = get_env_manager()
            env_vars = env_manager.get_all_variables()

            # Use the proper executor method
            result = get_code_executor().execute_code(
                code=request.code,
                packages=request.packages,
                timeout=request.timeout or 30,
                env_vars=env_vars,
                language=language,
            )
            
            # Log the execution
            container_id = result.get("container_id")
            log = ExecutionLog(
                job_id=request.job_id if hasattr(request, 'job_id') else None,
                code=request.code,
                output=result.get("output"),
                error=result.get("error"),
                container_id=container_id,
                execution_time=time.time() - start_time,
                started_at=datetime.utcnow(),
                status="success" if result.get("success") else "error"
            )
            db.add(log)
            db.commit()
            
            # Return the result from CodeExecutor with additional info
            response = {
                "success": result.get("success"),
                "output": result.get("output"),
                "error": result.get("error"),
                "container_id": container_id,
                "container_name": container_names.get(container_id, "Unnamed")
            }

            # Include web service info if available
            if "web_service" in result:
                response["web_service"] = result["web_service"]

            # Pass through timing breakdown for benchmarks/profiling
            if "timings_ms" in result:
                response["timings_ms"] = result["timings_ms"]

            return response
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

@router.get("/languages", summary="List registered runtimes")
async def list_languages():
    """Return the runtimes the server can execute code in.

    **Response**
    - `languages`: array of runtime names — the authoritative list, kept
      for back-compat with older clients.
    - `runtimes`: array of `{name, display_name, file_extension,
      supports_packages, package_manager}`. `supports_packages=false`
      means the runtime has no package manager wired in (bash, go).
    """
    import languages as lang_registry
    names = lang_registry.names()
    runtimes = []
    for n in names:
        rt = lang_registry.get(n)
        runtimes.append({
            "name": rt.name,
            "display_name": rt.display_name or rt.name.title(),
            "file_extension": rt.file_extension,
            "supports_packages": rt.supports_packages,
            "package_manager": rt.package_manager,
        })
    return {"languages": names, "runtimes": runtimes}


@router.get("/debug/containers")
async def debug_containers():
    """
    Debug endpoint to list all containers and web services.
    """
    try:
        containers_info = []
        for package_hash, container_id in get_code_executor().containers.items():
            try:
                container = docker_client.containers.get(container_id)
                containers_info.append({
                    "package_hash": package_hash,
                    "container_id": container_id,
                    "container_short_id": container_id[:8],
                    "status": container.status,
                    "image": container.image.tags[0] if container.image.tags else "unknown",
                    "ports": container.ports,
                    "is_web_service": container_id in get_code_executor().web_service_containers
                })
            except Exception as e:
                containers_info.append({
                    "package_hash": package_hash,
                    "container_id": container_id,
                    "error": str(e)
                })
        
        web_services_info = []
        for container_id, service_info in get_code_executor().web_service_containers.items():
            web_services_info.append({
                "container_id": container_id,
                "container_short_id": container_id[:8],
                "service_type": service_info["type"],
                "internal_port": service_info["internal_port"],
                "external_port": service_info["external_port"],
                "start_command": service_info["start_command"]
            })
        
        return {
            "containers": containers_info,
            "web_services": web_services_info,
            "total_containers": len(get_code_executor().containers),
            "total_web_services": len(get_code_executor().web_service_containers)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug error: {str(e)}")

@router.get("/debug/container/{container_id}/logs")
async def get_container_logs(container_id: str):
    """
    Get logs from a specific container to debug service issues.
    """
    try:
        # Find the full container ID
        full_container_id = None
        for stored_id in get_code_executor().containers.values():
            if stored_id.startswith(container_id) or stored_id == container_id:
                full_container_id = stored_id
                break
        
        if not full_container_id:
            raise HTTPException(status_code=404, detail="Container not found")
        
        container = docker_client.containers.get(full_container_id)
        
        # Get container logs
        logs = container.logs(tail=50).decode('utf-8', errors='replace')
        
        # If it's a web service, also try to get the service log
        service_log = ""
        if full_container_id in get_code_executor().web_service_containers:
            try:
                result = container.exec_run("cat /tmp/service.log", demux=False)
                if result.exit_code == 0:
                    service_log = result.output.decode('utf-8', errors='replace')
            except Exception as e:
                service_log = f"Error reading service log: {e}"
        
        return {
            "container_id": full_container_id,
            "container_short_id": full_container_id[:8],
            "container_logs": logs,
            "service_log": service_log,
            "is_web_service": full_container_id in get_code_executor().web_service_containers
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting logs: {str(e)}") 