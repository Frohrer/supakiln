from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import time
from datetime import datetime
from typing import List, Dict, Any

from models.schemas import (
    CodeExecutionRequest, ExecutionResultResponse, LanguageSupportResponse, 
    SSHSessionResponse, SSHConnectionRequest, SSHConnectionResponse
)
from models import ExecutionLog
from database import get_db
from services.executors.multi_language_executor import get_multi_language_executor
from services.executors.base_executor import ExecutionContext
from env_manager import EnvironmentManager
import os

router = APIRouter(tags=["multi-language-execution"])

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

@router.get("/languages", response_model=LanguageSupportResponse)
async def get_supported_languages():
    """Get all supported programming languages and executor information."""
    executor = get_multi_language_executor()
    
    return LanguageSupportResponse(
        supported_languages=executor.get_supported_languages(),
        executors=executor.get_executor_info()
    )

@router.post("/execute", response_model=ExecutionResultResponse)
async def execute_multi_language_code(request: CodeExecutionRequest, db: Session = Depends(get_db)):
    """
    Execute code in multiple programming languages with support for containers and SSH connections.
    """
    start_time = time.time()
    
    try:
        if not request.code:
            raise HTTPException(status_code=400, detail="Code is required")
        
        if not request.language:
            request.language = "python"  # Default to Python
        
        # Get environment variables
        try:
            env_manager = get_env_manager()
            env_vars = env_manager.get_all_variables()
        except Exception as e:
            print(f"Warning: Could not load environment variables: {e}")
            env_vars = {}
        
        # Create execution context
        context = ExecutionContext(
            code=request.code,
            language=request.language,
            timeout=request.timeout or 30,
            env_vars=env_vars,
            packages=request.packages or [],
            ssh_host=request.ssh_host,
            ssh_port=request.ssh_port or 22,
            ssh_username=request.ssh_username,
            ssh_password=request.ssh_password,
            ssh_key_path=request.ssh_key_path,
            ssh_session_id=request.ssh_session_id,
            container_id=request.container_id,
            use_container=request.use_container if request.use_container is not None else True,
            additional_params=request.additional_params or {}
        )
        
        # Validate context
        executor = get_multi_language_executor()
        is_valid, error_msg = executor.validate_execution_context(context)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Execute code
        result = executor.execute_code(context)
        
        # Calculate execution time
        execution_time = time.time() - start_time
        result.execution_time = execution_time
        
        # Log the execution
        log = ExecutionLog(
            code=request.code,
            output=result.output,
            error=result.error,
            container_id=result.container_id,
            execution_time=execution_time,
            started_at=datetime.utcnow(),
            status="success" if result.success else "error"
        )
        db.add(log)
        db.commit()
        
        # Return standardized response
        return ExecutionResultResponse(
            success=result.success,
            output=result.output,
            error=result.error,
            execution_time=result.execution_time,
            container_id=result.container_id,
            connection_id=result.connection_id,
            timed_out=result.timed_out,
            metadata=result.metadata or {},
            language=request.language,
            execution_mode=result.metadata.get("execution_mode", "unknown") if result.metadata else "unknown"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Log the error
        execution_time = time.time() - start_time
        try:
            log = ExecutionLog(
                code=request.code if hasattr(request, 'code') else None,
                error=str(e),
                execution_time=execution_time,
                started_at=datetime.utcnow(),
                status="error"
            )
            db.add(log)
            db.commit()
        except Exception as log_error:
            print(f"Failed to log execution error: {log_error}")
        
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")

@router.get("/sessions", response_model=List[SSHSessionResponse])
async def get_active_sessions(language: str = None):
    """Get all active SSH sessions, optionally filtered by language."""
    executor = get_multi_language_executor()
    sessions = executor.get_active_sessions(language)
    
    return [
        SSHSessionResponse(
            session_id=session["session_id"],
            host=session["host"],
            username=session["username"],
            working_directory=session.get("working_directory", "~"),
            is_active=True,
            last_used=session["last_used"],
            age=session["age"]
        )
        for session in sessions
    ]

@router.delete("/sessions/{session_id}")
async def cleanup_session(session_id: str, language: str = None):
    """Cleanup a specific SSH session."""
    executor = get_multi_language_executor()
    success = executor.cleanup_connection(session_id, language)
    
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or could not be cleaned up")
    
    return {"message": f"Session {session_id} cleaned up successfully"}

@router.post("/sessions/cleanup-stale")
async def cleanup_stale_sessions(max_age_seconds: int = 3600):
    """Cleanup sessions that haven't been used recently."""
    executor = get_multi_language_executor()
    cleanup_counts = executor.cleanup_stale_sessions(max_age_seconds)
    
    total_cleaned = sum(cleanup_counts.values())
    
    return {
        "message": f"Cleaned up {total_cleaned} stale sessions",
        "cleanup_counts": cleanup_counts
    }

@router.get("/sessions/{session_id}/status")
async def get_session_status(session_id: str, language: str = None):
    """Get status information about a specific session."""
    executor = get_multi_language_executor()
    status = executor.get_connection_status(session_id, language)
    
    if not status or status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    
    return status

@router.post("/test-ssh-connection")
async def test_ssh_connection(request: SSHConnectionRequest):
    """Test an SSH connection without creating a persistent session."""
    try:
        try:
            import paramiko
        except ImportError:
            raise HTTPException(status_code=500, detail="paramiko library not installed. Install with: pip install paramiko")
        
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Test connection
        if request.key_path:
            ssh_client.connect(
                hostname=request.host,
                port=request.port,
                username=request.username,
                key_filename=request.key_path,
                timeout=10
            )
        else:
            ssh_client.connect(
                hostname=request.host,
                port=request.port,
                username=request.username,
                password=request.password,
                timeout=10
            )
        
        # Test command execution
        stdin, stdout, stderr = ssh_client.exec_command("echo 'Connection test successful'", timeout=5)
        output = stdout.read().decode('utf-8').strip()
        error = stderr.read().decode('utf-8').strip()
        
        ssh_client.close()
        
        return {
            "success": True,
            "message": "SSH connection successful",
            "test_output": output,
            "error": error if error else None
        }
        
    except ImportError:
        raise HTTPException(status_code=500, detail="paramiko library not installed")
    except Exception as e:
        return {
            "success": False,
            "message": f"SSH connection failed: {str(e)}"
        }

@router.get("/health")
async def health_check():
    """Health check endpoint for the multi-language execution service."""
    executor = get_multi_language_executor()
    
    try:
        # Get basic executor info
        executor_info = executor.get_executor_info()
        
        # Get active sessions count
        active_sessions = executor.get_active_sessions()
        
        return {
            "status": "healthy",
            "executors": executor_info,
            "active_sessions_count": len(active_sessions),
            "supported_languages": executor.get_supported_languages()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

# Server maintenance specific endpoints for bash/SSH
@router.post("/server-maintenance/execute")
async def execute_server_maintenance(request: CodeExecutionRequest, db: Session = Depends(get_db)):
    """
    Special endpoint for server maintenance tasks using persistent SSH sessions.
    Automatically sets language to bash and uses SSH connections.
    """
    if not request.ssh_host:
        raise HTTPException(status_code=400, detail="SSH host is required for server maintenance")
    
    # Override settings for server maintenance
    request.language = "bash"
    request.use_container = False
    
    # Use the regular execute endpoint
    return await execute_multi_language_code(request, db)

@router.get("/server-maintenance/sessions")
async def get_server_maintenance_sessions():
    """Get all active bash SSH sessions for server maintenance."""
    return await get_active_sessions(language="bash") 