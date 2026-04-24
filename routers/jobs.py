from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from models.schemas import ScheduledJobRequest, ScheduledJobResponse
from models import ScheduledJob, User
from database import get_db
from scheduler import scheduler
from auth import current_user
import languages as lang_registry

router = APIRouter(prefix="/jobs", tags=["scheduled-jobs"])


def _validate_language(name: str) -> str:
    """Return the validated language name or raise 400."""
    if name is None:
        return "python"
    try:
        return lang_registry.get(name).name
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"unknown language {name!r}; known: {lang_registry.names()}",
        )


def _job_to_response(job: ScheduledJob) -> dict:
    return {
        "id": job.id,
        "name": job.name,
        "code": job.code,
        "cron_expression": job.cron_expression,
        "packages": job.packages,
        "container_id": job.container_id,
        "created_at": job.created_at.isoformat(),
        "last_run": job.last_run.isoformat() if job.last_run else None,
        "is_active": bool(job.is_active),
        "timeout": job.timeout,
        "language": getattr(job, "language", None) or "python",
    }


def _scoped(db: Session, user: User):
    """Return a query filtered to rows the user can see.

    Admins see every job; non-admins only see their own.
    """
    q = db.query(ScheduledJob)
    if not user.is_admin:
        q = q.filter(ScheduledJob.owner_user_id == user.id)
    return q


@router.post("", response_model=ScheduledJobResponse)
async def create_scheduled_job(
    request: ScheduledJobRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Create a new scheduled job."""
    language = _validate_language(request.language)
    try:
        db_job = ScheduledJob(
            name=request.name,
            code=request.code,
            cron_expression=request.cron_expression,
            packages=','.join(request.packages) if request.packages else None,
            container_id=request.container_id,
            timeout=request.timeout,
            language=language,
            created_at=datetime.now(),
            is_active=True,
            owner_user_id=user.id,
        )
        db.add(db_job)
        db.commit()
        db.refresh(db_job)

        # The scheduler will pick up the new job through load_existing_jobs
        scheduler.load_existing_jobs()

        return _job_to_response(db_job)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[ScheduledJobResponse])
async def list_scheduled_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """List scheduled jobs owned by the caller (admins see all)."""
    jobs = _scoped(db, user).all()
    return [_job_to_response(job) for job in jobs]


@router.get("/{job_id}", response_model=ScheduledJobResponse)
async def get_scheduled_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Get a specific scheduled job."""
    job = _scoped(db, user).filter(ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.put("/{job_id}", response_model=ScheduledJobResponse)
async def update_scheduled_job(
    job_id: int,
    request: ScheduledJobRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Update a scheduled job."""
    language = _validate_language(request.language)
    # Verify ownership before letting the scheduler update anything.
    existing = _scoped(db, user).filter(ScheduledJob.id == job_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        job = scheduler.update_job(
            job_id,
            name=request.name,
            code=request.code,
            cron_expression=request.cron_expression,
            container_id=request.container_id,
            packages=','.join(request.packages) if request.packages else None,
            timeout=request.timeout,
            language=language,
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_to_response(job)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{job_id}")
async def delete_scheduled_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Delete a scheduled job."""
    existing = _scoped(db, user).filter(ScheduledJob.id == job_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        scheduler.delete_job(job_id)
        return {"message": "Job deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
