from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from models.schemas import EnvVarRequest, EnvVarResponse, EnvVarMetadata
from models import EnvironmentVariable
from database import get_db
from env_manager import EnvironmentManager
import os

router = APIRouter(prefix="/env", tags=["environment"])

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

@router.post("", response_model=EnvVarResponse)
async def set_environment_variable(request: EnvVarRequest, db: Session = Depends(get_db)):
    """Set an environment variable."""
    manager = get_env_manager()
    manager.set_variable(request.name, request.value, request.description)
    var = db.query(EnvironmentVariable).filter_by(name=request.name).first()
    return EnvVarResponse(
        name=var.name,
        created_at=var.created_at.isoformat(),
        updated_at=var.updated_at.isoformat()
    )

@router.get("", response_model=List[str])
async def list_environment_variables():
    """List all environment variable names."""
    manager = get_env_manager()
    return manager.list_variables()

@router.get("/metadata", response_model=List[EnvVarMetadata])
async def list_environment_variable_metadata():
    """List all environment variable metadata without values."""
    manager = get_env_manager()
    return manager.list_variables_with_metadata()

@router.get("/metadata/{name}", response_model=EnvVarMetadata)
async def get_environment_variable_metadata(name: str):
    """Get an environment variable metadata without value."""
    manager = get_env_manager()
    metadata = manager.get_variable_metadata(name)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Environment variable not found")
    return metadata

@router.get("/{name}")
async def get_environment_variable(name: str):
    """Get an environment variable value."""
    manager = get_env_manager()
    value = manager.get_variable(name)
    if value is None:
        raise HTTPException(status_code=404, detail="Environment variable not found")
    return {"name": name, "value": value}

@router.delete("/{name}")
async def delete_environment_variable(name: str):
    """Delete an environment variable."""
    manager = get_env_manager()
    if not manager.delete_variable(name):
        raise HTTPException(status_code=404, detail="Environment variable not found")
    return {"message": f"Environment variable {name} deleted successfully"} 