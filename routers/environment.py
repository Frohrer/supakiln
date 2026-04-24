from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from models.schemas import EnvVarRequest, EnvVarResponse, EnvVarMetadata
from models import EnvironmentVariable, User
from database import get_db
from env_manager import EnvironmentManager
from auth import current_user
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
async def set_environment_variable(
    request: EnvVarRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Set one of the caller's encrypted environment variables.

    Each user has their own namespace — the same `name` can exist for
    several users and will resolve independently.
    """
    manager = get_env_manager()
    manager.set_variable(
        request.name, request.value,
        owner_user_id=user.id, description=request.description,
    )
    var = db.query(EnvironmentVariable).filter(
        EnvironmentVariable.name == request.name,
        EnvironmentVariable.owner_user_id == user.id,
    ).first()
    return EnvVarResponse(
        name=var.name,
        created_at=var.created_at.isoformat(),
        updated_at=var.updated_at.isoformat(),
    )


@router.get("", response_model=List[str])
async def list_environment_variables(user: User = Depends(current_user)):
    """List names of the caller's environment variables."""
    manager = get_env_manager()
    return manager.list_variables(owner_user_id=user.id)


@router.get("/metadata", response_model=List[EnvVarMetadata])
async def list_environment_variable_metadata(user: User = Depends(current_user)):
    """List metadata for the caller's environment variables."""
    manager = get_env_manager()
    return manager.list_variables_with_metadata(owner_user_id=user.id)


@router.get("/metadata/{name}", response_model=EnvVarMetadata)
async def get_environment_variable_metadata(
    name: str,
    user: User = Depends(current_user),
):
    """Get metadata of a specific env var (no value)."""
    manager = get_env_manager()
    metadata = manager.get_variable_metadata(name, owner_user_id=user.id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Environment variable not found")
    return metadata


@router.get("/{name}")
async def get_environment_variable(
    name: str,
    user: User = Depends(current_user),
):
    """Get the decrypted value of the caller's env var by name."""
    manager = get_env_manager()
    value = manager.get_variable(name, owner_user_id=user.id)
    if value is None:
        raise HTTPException(status_code=404, detail="Environment variable not found")
    return {"name": name, "value": value}


@router.delete("/{name}")
async def delete_environment_variable(
    name: str,
    user: User = Depends(current_user),
):
    """Delete one of the caller's env vars."""
    manager = get_env_manager()
    if not manager.delete_variable(name, owner_user_id=user.id):
        raise HTTPException(status_code=404, detail="Environment variable not found")
    return {"message": f"Environment variable {name} deleted successfully"}
