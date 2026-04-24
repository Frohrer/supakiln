from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from models.schemas import WebhookJobRequest, WebhookJobResponse
from models import WebhookJob, User
from database import get_db
from auth import current_user
import languages as lang_registry

router = APIRouter(prefix="/webhook-jobs", tags=["webhook-jobs"])


def _validate_language(name):
    if name is None:
        return "python"
    try:
        return lang_registry.get(name).name
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"unknown language {name!r}; known: {lang_registry.names()}",
        )


def _job_to_response(job: WebhookJob) -> dict:
    return {
        "id": job.id,
        "name": job.name,
        "endpoint": job.endpoint,
        "code": job.code,
        "packages": job.packages,
        "container_id": job.container_id,
        "created_at": job.created_at.isoformat(),
        "last_triggered": job.last_triggered.isoformat() if job.last_triggered else None,
        "is_active": bool(job.is_active),
        "timeout": job.timeout,
        "description": job.description,
        "language": getattr(job, "language", None) or "python",
    }


def _scoped(db: Session, user: User):
    q = db.query(WebhookJob)
    if not user.is_admin:
        q = q.filter(WebhookJob.owner_user_id == user.id)
    return q


@router.post("", response_model=WebhookJobResponse)
async def create_webhook_job(
    request: WebhookJobRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Create a new webhook job."""
    language = _validate_language(request.language)
    try:
        if not request.endpoint.startswith('/'):
            request.endpoint = '/' + request.endpoint

        # endpoint is GLOBAL-unique by design — URL routing needs it.
        existing = db.query(WebhookJob).filter(WebhookJob.endpoint == request.endpoint).first()
        if existing:
            raise HTTPException(status_code=400, detail="Endpoint already exists")

        db_job = WebhookJob(
            name=request.name,
            endpoint=request.endpoint,
            code=request.code,
            packages=','.join(request.packages) if request.packages else None,
            container_id=request.container_id,
            timeout=request.timeout,
            description=request.description,
            language=language,
            created_at=datetime.now(),
            is_active=True,
            owner_user_id=user.id,
        )
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        return _job_to_response(db_job)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[WebhookJobResponse])
async def list_webhook_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """List webhook jobs owned by the caller (admins see all)."""
    jobs = _scoped(db, user).all()
    return [_job_to_response(job) for job in jobs]


@router.get("/{job_id}", response_model=WebhookJobResponse)
async def get_webhook_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Get a specific webhook job."""
    job = _scoped(db, user).filter(WebhookJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Webhook job not found")
    return _job_to_response(job)


@router.put("/{job_id}", response_model=WebhookJobResponse)
async def update_webhook_job(
    job_id: int,
    request: WebhookJobRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Update a webhook job."""
    language = _validate_language(request.language)
    try:
        job = _scoped(db, user).filter(WebhookJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Webhook job not found")

        if not request.endpoint.startswith('/'):
            request.endpoint = '/' + request.endpoint

        existing = db.query(WebhookJob).filter(
            WebhookJob.endpoint == request.endpoint,
            WebhookJob.id != job_id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Endpoint already exists")

        job.name = request.name
        job.endpoint = request.endpoint
        job.code = request.code
        job.packages = ','.join(request.packages) if request.packages else None
        job.container_id = request.container_id
        job.timeout = request.timeout
        job.description = request.description
        job.language = language

        db.commit()
        db.refresh(job)
        return _job_to_response(job)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{job_id}")
async def delete_webhook_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Delete a webhook job."""
    try:
        job = _scoped(db, user).filter(WebhookJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Webhook job not found")

        db.delete(job)
        db.commit()
        return {"message": "Webhook job deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
