from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from models.schemas import PersistentServiceRequest, PersistentServiceResponse
from models import PersistentService
from database import get_db
from services.service_manager import service_manager
from services.docker_client import docker_client

router = APIRouter(prefix="/services", tags=["persistent-services"])

@router.post("", response_model=PersistentServiceResponse)
async def create_persistent_service(request: PersistentServiceRequest, db: Session = Depends(get_db)):
    """Create a new persistent service."""
    try:
        # Check if name already exists
        existing = db.query(PersistentService).filter(PersistentService.name == request.name).first()
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
            status="stopped"
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
async def list_persistent_services(db: Session = Depends(get_db)):
    """List all persistent services."""
    services = db.query(PersistentService).all()
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
async def get_persistent_service(service_id: int, db: Session = Depends(get_db)):
    """Get a specific persistent service."""
    service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
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
async def update_persistent_service(service_id: int, request: PersistentServiceRequest, db: Session = Depends(get_db)):
    """Update a persistent service."""
    try:
        service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        
        # Check if name already exists (excluding current service)
        existing = db.query(PersistentService).filter(
            PersistentService.name == request.name,
            PersistentService.id != service_id
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
async def delete_persistent_service(service_id: int, db: Session = Depends(get_db)):
    """Delete a persistent service."""
    try:
        service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
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
async def start_persistent_service(service_id: int, db: Session = Depends(get_db)):
    """Start a persistent service."""
    try:
        success = service_manager.start_service(service_id, db)
        if success:
            return {"message": "Service start initiated"}
        else:
            raise HTTPException(status_code=404, detail="Service not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{service_id}/stop")
async def stop_persistent_service(service_id: int, db: Session = Depends(get_db)):
    """Stop a persistent service."""
    try:
        success = service_manager.stop_service(service_id, db)
        if success:
            return {"message": "Service stopped"}
        else:
            raise HTTPException(status_code=404, detail="Service not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{service_id}/restart")
async def restart_persistent_service(service_id: int, db: Session = Depends(get_db)):
    """Restart a persistent service."""
    try:
        success = service_manager.restart_service(service_id, db)
        if success:
            return {"message": "Service restart initiated"}
        else:
            raise HTTPException(status_code=404, detail="Service not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{service_id}/logs")
async def get_service_logs(service_id: int, limit: int = 100, db: Session = Depends(get_db)):
    """Get logs for a specific service."""
    try:
        service = db.query(PersistentService).filter(PersistentService.id == service_id).first()
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