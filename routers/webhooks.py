from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from typing import List
import time
import base64
import json
from datetime import datetime
from models.schemas import WebhookJobRequest, WebhookJobResponse
from models import WebhookJob, ExecutionLog
from database import get_db
from services.docker_client import docker_client
from code_executor import CodeExecutor
from env_manager import EnvironmentManager
import os

router = APIRouter(prefix="/webhook-jobs", tags=["webhook-jobs"])

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

@router.post("", response_model=WebhookJobResponse)
async def create_webhook_job(request: WebhookJobRequest, db: Session = Depends(get_db)):
    """Create a new webhook job."""
    try:
        # Validate endpoint format
        if not request.endpoint.startswith('/'):
            request.endpoint = '/' + request.endpoint
        
        # Check if endpoint already exists
        existing = db.query(WebhookJob).filter(WebhookJob.endpoint == request.endpoint).first()
        if existing:
            raise HTTPException(status_code=400, detail="Endpoint already exists")
        
        # Create job in database
        db_job = WebhookJob(
            name=request.name,
            endpoint=request.endpoint,
            code=request.code,
            packages=','.join(request.packages) if request.packages else None,
            container_id=request.container_id,
            timeout=request.timeout,
            description=request.description,
            created_at=datetime.now(),
            is_active=True
        )
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        
        return {
            "id": db_job.id,
            "name": db_job.name,
            "endpoint": db_job.endpoint,
            "code": db_job.code,
            "packages": db_job.packages,
            "container_id": db_job.container_id,
            "created_at": db_job.created_at.isoformat(),
            "last_triggered": db_job.last_triggered.isoformat() if db_job.last_triggered else None,
            "is_active": db_job.is_active,
            "timeout": db_job.timeout,
            "description": db_job.description
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=List[WebhookJobResponse])
async def list_webhook_jobs(db: Session = Depends(get_db)):
    """List all webhook jobs."""
    jobs = db.query(WebhookJob).all()
    return [
        {
            "id": job.id,
            "name": job.name,
            "endpoint": job.endpoint,
            "code": job.code,
            "packages": job.packages,
            "container_id": job.container_id,
            "created_at": job.created_at.isoformat(),
            "last_triggered": job.last_triggered.isoformat() if job.last_triggered else None,
            "is_active": job.is_active,
            "timeout": job.timeout,
            "description": job.description
        }
        for job in jobs
    ]

@router.get("/{job_id}", response_model=WebhookJobResponse)
async def get_webhook_job(job_id: int, db: Session = Depends(get_db)):
    """Get a specific webhook job."""
    job = db.query(WebhookJob).filter(WebhookJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Webhook job not found")
    return {
        "id": job.id,
        "name": job.name,
        "endpoint": job.endpoint,
        "code": job.code,
        "packages": job.packages,
        "container_id": job.container_id,
        "created_at": job.created_at.isoformat(),
        "last_triggered": job.last_triggered.isoformat() if job.last_triggered else None,
        "is_active": job.is_active,
        "timeout": job.timeout,
        "description": job.description
    }

@router.put("/{job_id}", response_model=WebhookJobResponse)
async def update_webhook_job(job_id: int, request: WebhookJobRequest, db: Session = Depends(get_db)):
    """Update a webhook job."""
    try:
        job = db.query(WebhookJob).filter(WebhookJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Webhook job not found")
        
        # Validate endpoint format
        if not request.endpoint.startswith('/'):
            request.endpoint = '/' + request.endpoint
        
        # Check if endpoint already exists (excluding current job)
        existing = db.query(WebhookJob).filter(
            WebhookJob.endpoint == request.endpoint,
            WebhookJob.id != job_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Endpoint already exists")
        
        # Update job
        job.name = request.name
        job.endpoint = request.endpoint
        job.code = request.code
        job.packages = ','.join(request.packages) if request.packages else None
        job.container_id = request.container_id
        job.timeout = request.timeout
        job.description = request.description
        
        db.commit()
        db.refresh(job)
        
        return {
            "id": job.id,
            "name": job.name,
            "endpoint": job.endpoint,
            "code": job.code,
            "packages": job.packages,
            "container_id": job.container_id,
            "created_at": job.created_at.isoformat(),
            "last_triggered": job.last_triggered.isoformat() if job.last_triggered else None,
            "is_active": job.is_active,
            "timeout": job.timeout,
            "description": job.description
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{job_id}")
async def delete_webhook_job(job_id: int, db: Session = Depends(get_db)):
    """Delete a webhook job."""
    try:
        job = db.query(WebhookJob).filter(WebhookJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Webhook job not found")
        
        db.delete(job)
        db.commit()
        return {"message": "Webhook job deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

 