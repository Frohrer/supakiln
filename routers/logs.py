from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from models.schemas import ExecutionLogResponse
from models import ExecutionLog
from database import get_db

router = APIRouter(prefix="/logs", tags=["logs"])

@router.get("", response_model=List[ExecutionLogResponse])
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

@router.get("/{log_id}", response_model=ExecutionLogResponse)
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