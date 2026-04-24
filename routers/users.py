"""User and API-key management.

  /users/me/keys            — CRUD for the caller's own long-lived keys.
  /admin/users              — admin-only CRUD for every user.

Key plaintext is returned exactly once at creation (POST response) and
never again. After that only the prefix is visible.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from db_models import ApiKey, User, SYSTEM_USER_ID
from models.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from auth import current_user, generate_token, hash_password, require_admin


router = APIRouter(tags=["users"])


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        is_admin=bool(user.is_admin),
        disabled=bool(user.disabled),
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


def _key_response(key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=key.id,
        prefix=key.prefix,
        label=key.label,
        last_used_at=key.last_used_at.isoformat() if key.last_used_at else None,
        created_at=key.created_at.isoformat() if key.created_at else "",
    )


# ---------------------------------------------------------------------
# /users/me/keys — caller-owned API keys
# ---------------------------------------------------------------------


@router.get(
    "/users/me/keys",
    response_model=List[ApiKeyResponse],
    summary="List the caller's API keys",
)
async def list_my_keys(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if user.id == SYSTEM_USER_ID:
        # The system user exists as a backing identity for anonymous
        # requests; its keys (if any) aren't meaningful to clients.
        return []
    keys = (
        db.query(ApiKey)
        .filter(
            ApiKey.user_id == user.id,
            ApiKey.kind == "api",
            ApiKey.revoked_at.is_(None),
        )
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    return [_key_response(k) for k in keys]


@router.post(
    "/users/me/keys",
    response_model=ApiKeyCreateResponse,
    summary="Mint a new API key for the caller (plaintext returned once)",
)
async def create_my_key(
    body: ApiKeyCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if user.id == SYSTEM_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="the system user cannot mint tokens — log in as a "
                   "real user first",
        )
    plaintext, hashed, prefix = generate_token()
    key = ApiKey(
        user_id=user.id,
        hashed_key=hashed,
        prefix=prefix,
        label=body.label,
        kind="api",
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return ApiKeyCreateResponse(
        id=key.id,
        token=plaintext,
        prefix=prefix,
        label=key.label,
        created_at=key.created_at.isoformat() if key.created_at else "",
    )


@router.delete(
    "/users/me/keys/{key_id}",
    summary="Revoke one of the caller's API keys",
)
async def revoke_my_key(
    key_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    key = (
        db.query(ApiKey)
        .filter(ApiKey.id == key_id, ApiKey.user_id == user.id)
        .first()
    )
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="key not found"
        )
    if key.revoked_at is None:
        key.revoked_at = datetime.utcnow()
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------
# /admin/users — admin-only CRUD for every user
# ---------------------------------------------------------------------


@router.get(
    "/admin/users",
    response_model=List[UserResponse],
    summary="List all users (admin only)",
)
async def list_users(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.id.asc()).all()
    return [_user_response(u) for u in users]


@router.post(
    "/admin/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (admin only)",
)
async def create_user(
    body: UserCreateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already in use",
        )
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        is_admin=1 if body.is_admin else 0,
        disabled=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_response(user)


@router.patch(
    "/admin/users/{user_id}",
    response_model=UserResponse,
    summary="Update a user (admin only)",
)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == SYSTEM_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot modify the system user",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        )
    if body.email is not None:
        clash = db.query(User).filter(
            User.email == body.email, User.id != user_id
        ).first()
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="email already in use",
            )
        user.email = body.email
    if body.password:
        user.password_hash = hash_password(body.password)
    if body.is_admin is not None:
        user.is_admin = 1 if body.is_admin else 0
    if body.disabled is not None:
        user.disabled = 1 if body.disabled else 0
    db.commit()
    db.refresh(user)
    return _user_response(user)


@router.delete(
    "/admin/users/{user_id}",
    summary="Delete a user (admin only). Revokes all their keys.",
)
async def delete_user(
    user_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == SYSTEM_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot delete the system user",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        )
    # Revoke their keys rather than cascading deletes; preserves audit
    # trail and keeps owner_user_id FKs on historical rows valid.
    now = datetime.utcnow()
    db.query(ApiKey).filter(
        ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None)
    ).update({ApiKey.revoked_at: now})
    db.delete(user)
    db.commit()
    return {"ok": True}
