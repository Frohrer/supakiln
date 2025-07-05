from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from models.schemas import ScheduledJobRequest, ScheduledJobResponse
from models import ScheduledJob
from database import get_db
from scheduler import scheduler

router = APIRouter(prefix="/jobs", tags=["scheduled-jobs"])

@router.post("", response_model=ScheduledJobResponse)
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
            timeout=request.timeout,
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
            "is_active": db_job.is_active,
            "timeout": db_job.timeout
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=List[ScheduledJobResponse])
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
            "is_active": job.is_active,
            "timeout": job.timeout
        }
        for job in jobs
    ]

@router.get("/{job_id}", response_model=ScheduledJobResponse)
async def get_scheduled_job(job_id: int, db: Session = Depends(get_db)):
    """Get a specific scheduled job."""
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.put("/{job_id}", response_model=ScheduledJobResponse)
async def update_scheduled_job(job_id: int, request: ScheduledJobRequest, db: Session = Depends(get_db)):
    """Update a scheduled job."""
    try:
        job = scheduler.update_job(
            job_id,
            name=request.name,
            code=request.code,
            cron_expression=request.cron_expression,
            container_id=request.container_id,
            packages=','.join(request.packages) if request.packages else None,
            timeout=request.timeout
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{job_id}")
async def delete_scheduled_job(job_id: int):
    """Delete a scheduled job."""
    try:
        scheduler.delete_job(job_id)
        return {"message": "Job deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 