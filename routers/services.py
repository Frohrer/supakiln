from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from models.schemas import PersistentServiceRequest, PersistentServiceResponse
from models import PersistentService, User
from database import get_db
from services.service_manager import service_manager
from services.docker_client import docker_client
from auth import current_user

router = APIRouter(prefix="/services", tags=["persistent-services"])


def _scoped(db: Session, user: User):
    q = db.query(PersistentService)
    if not user.is_admin:
        q = q.filter(PersistentService.owner_user_id == user.id)
    return q


@router.post("", response_model=PersistentServiceResponse)
async def create_persistent_service(
    request: PersistentServiceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Create a new persistent service."""
    try:
        # Service name is unique per-user (not globally); the caller's
        # own services must not collide, but alice and bob can both
        # have one named "worker".
        existing = db.query(PersistentService).filter(
            PersistentService.name == request.name,
            PersistentService.owner_user_id == user.id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Service name already exists")

        # Create service in database
        db_service = PersistentService(
            name=request.name,
            code=request.code,
            packages=','.join(request.packages) if request.packages else None,
            container_id=request.container_id,
            restart_policy=request.restart_policy,
            description=request.description,
            auto_start=1 if request.auto_start else 0,
            created_at=datetime.now(),
            is_active=True,
            status="stopped",
            owner_user_id=user.id,
        )
        db.add(db_service)
        db.commit()
        db.refresh(db_service)
        
        return {
            "id": db_service.id,
            "name": db_service.name,
            "code": db_service.code,
            "packages": db_service.packages,
            "container_id": db_service.container_id,
            "created_at": db_service.created_at.isoformat(),
            "started_at": db_service.started_at.isoformat() if db_service.started_at else None,
            "last_restart": db_service.last_restart.isoformat() if db_service.last_restart else None,
            "is_active": db_service.is_active,
            "status": db_service.status,
            "restart_policy": db_service.restart_policy,
            "description": db_service.description,
            "process_id": db_service.process_id,
            "auto_start": bool(db_service.auto_start)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=List[PersistentServiceResponse])
async def list_persistent_services(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """List persistent services owned by the caller (admins see all)."""
    services = _scoped(db, user).all()
    return [
        {
            "id": service.id,
            "name": service.name,
            "code": service.code,
            "packages": service.packages,
            "container_id": service.container_id,
            "created_at": service.created_at.isoformat(),
            "started_at": service.started_at.isoformat() if service.started_at else None,
            "last_restart": service.last_restart.isoformat() if service.last_restart else None,
            "is_active": service.is_active,
            "status": service.status,
            "restart_policy": service.restart_policy,
            "description": service.description,
            "process_id": service.process_id,
            "auto_start": bool(service.auto_start)
        }
        for service in services
    ]

@router.get("/{service_id}", response_model=PersistentServiceResponse)
async def get_persistent_service(
    service_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Get a specific persistent service."""
    service = _scoped(db, user).filter(PersistentService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return {
        "id": service.id,
        "name": service.name,
        "code": service.code,
        "packages": service.packages,
        "container_id": service.container_id,
        "created_at": service.created_at.isoformat(),
        "started_at": service.started_at.isoformat() if service.started_at else None,
        "last_restart": service.last_restart.isoformat() if service.last_restart else None,
        "is_active": service.is_active,
        "status": service.status,
        "restart_policy": service.restart_policy,
        "description": service.description,
        "process_id": service.process_id,
        "auto_start": bool(service.auto_start)
    }

@router.put("/{service_id}", response_model=PersistentServiceResponse)
async def update_persistent_service(
    service_id: int,
    request: PersistentServiceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Update a persistent service."""
    try:
        service = _scoped(db, user).filter(PersistentService.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        # Name is unique per-owner; check only within the caller's namespace.
        existing = db.query(PersistentService).filter(
            PersistentService.name == request.name,
            PersistentService.owner_user_id == service.owner_user_id,
            PersistentService.id != service_id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Service name already exists")
        
        # Update service
        service.name = request.name
        service.code = request.code
        service.packages = ','.join(request.packages) if request.packages else None
        service.container_id = request.container_id
        service.restart_policy = request.restart_policy
        service.description = request.description
        service.auto_start = 1 if request.auto_start else 0
        
        db.commit()
        db.refresh(service)
        
        return {
            "id": service.id,
            "name": service.name,
            "code": service.code,
            "packages": service.packages,
            "container_id": service.container_id,
            "created_at": service.created_at.isoformat(),
            "started_at": service.started_at.isoformat() if service.started_at else None,
            "last_restart": service.last_restart.isoformat() if service.last_restart else None,
            "is_active": service.is_active,
            "status": service.status,
            "restart_policy": service.restart_policy,
            "description": service.description,
            "process_id": service.process_id,
            "auto_start": bool(service.auto_start)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{service_id}")
async def delete_persistent_service(
    service_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Delete a persistent service."""
    try:
        service = _scoped(db, user).filter(PersistentService.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        
        # Stop the service first
        service_manager.stop_service(service_id, db)
        
        # Delete from database
        db.delete(service)
        db.commit()
        return {"message": "Service deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Service control endpoints
@router.post("/{service_id}/start")
async def start_persistent_service(
    service_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Start a persistent service."""
    try:
        # Enforce ownership before touching the manager.
        svc = _scoped(db, user).filter(PersistentService.id == service_id).first()
        if not svc:
            raise HTTPException(status_code=404, detail="Service not found")
        success = service_manager.start_service(service_id, db)
        if success:
            return {"message": "Service start initiated"}
        raise HTTPException(status_code=404, detail="Service not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{service_id}/stop")
async def stop_persistent_service(
    service_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Stop a persistent service."""
    try:
        svc = _scoped(db, user).filter(PersistentService.id == service_id).first()
        if not svc:
            raise HTTPException(status_code=404, detail="Service not found")
        success = service_manager.stop_service(service_id, db)
        if success:
            return {"message": "Service stopped"}
        raise HTTPException(status_code=404, detail="Service not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{service_id}/restart")
async def restart_persistent_service(
    service_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Restart a persistent service."""
    try:
        svc = _scoped(db, user).filter(PersistentService.id == service_id).first()
        if not svc:
            raise HTTPException(status_code=404, detail="Service not found")
        success = service_manager.restart_service(service_id, db)
        if success:
            return {"message": "Service restart initiated"}
        raise HTTPException(status_code=404, detail="Service not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{service_id}/logs")
async def get_service_logs(
    service_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Get logs for a specific service."""
    try:
        service = _scoped(db, user).filter(PersistentService.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        
        # If service is running, get live logs from container
        if service.status == "running" and service.container_id:
            try:
                container = docker_client.containers.get(service.container_id)
                logs = container.logs(tail=limit, timestamps=True).decode()
                return {"logs": logs, "service_id": service_id, "status": "live"}
            except Exception as e:
                return {"logs": f"Error fetching live logs: {e}", "service_id": service_id, "status": "error"}
        
        return {"logs": "Service not running", "service_id": service_id, "status": "stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 