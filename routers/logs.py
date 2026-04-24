from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from models.schemas import ExecutionLogResponse
from models import ExecutionLog, User
from database import get_db
from auth import current_user

router = APIRouter(prefix="/logs", tags=["logs"])


def _scoped(db: Session, user: User):
    q = db.query(ExecutionLog)
    if not user.is_admin:
        q = q.filter(ExecutionLog.owner_user_id == user.id)
    return q


@router.get("", response_model=List[ExecutionLogResponse])
async def get_execution_logs(
    job_id: Optional[int] = None,
    webhook_job_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Get execution logs the caller owns (admins see all)."""
    query = _scoped(db, user)
    if job_id is not None:
        query = query.filter(ExecutionLog.job_id == job_id)
    if webhook_job_id is not None:
        query = query.filter(ExecutionLog.webhook_job_id == webhook_job_id)
    logs = query.order_by(ExecutionLog.started_at.desc()).offset(offset).limit(limit).all()

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
            "response_data": log.response_data,
        }
        for log in logs
    ]


@router.get("/{log_id}", response_model=ExecutionLogResponse)
async def get_execution_log(
    log_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Get a specific execution log."""
    log = _scoped(db, user).filter(ExecutionLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

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
        "response_data": log.response_data,
    }
