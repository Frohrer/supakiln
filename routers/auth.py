"""Login / logout / self endpoints.

Login issues an opaque session token stored in the api_keys table with
kind='session' and an expires_at 14 days out. The token is returned in
the response body AND set as an HttpOnly cookie for browser callers.
Logout revokes the session row.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from database import get_db
from db_models import ApiKey, User
from models.schemas import LoginRequest, LoginResponse, UserResponse
from auth import (
    current_user,
    generate_token,
    hash_token,
    verify_password,
    SESSION_TTL_SECONDS,
)


router = APIRouter(prefix="/auth", tags=["auth"])


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        is_admin=bool(user.is_admin),
        disabled=bool(user.disabled),
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@router.post("/login", response_model=LoginResponse, summary="Exchange email/password for a session token")
async def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == body.email).first()
    # Keep the failure path uniform to avoid user-enumeration by timing.
    if user is None or user.disabled or not user.password_hash:
        # Still do a dummy verify to even out timing.
        verify_password(
            "$argon2id$v=19$m=65536,t=3,p=4$"
            "dummy-salt-for-timing-pad$dummy-hash-for-timing",
            body.password,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    if not verify_password(user.password_hash, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    plaintext, hashed, prefix = generate_token()
    session = ApiKey(
        user_id=user.id,
        hashed_key=hashed,
        prefix=prefix,
        label="login session",
        kind="session",
        expires_at=datetime.utcnow() + timedelta(seconds=SESSION_TTL_SECONDS),
    )
    db.add(session)
    db.commit()

    response.set_cookie(
        key="supakiln_session",
        value=plaintext,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        # Secure flag intentionally not forced here: the deployment
        # reverse-proxy (Cloudflare) terminates TLS. Local dev uses http.
    )
    return LoginResponse(
        session_token=plaintext,
        user=_user_response(user),
    )


@router.post("/logout", summary="Revoke the current session")
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    # Look at the same transports as the dep.
    auth = request.headers.get("Authorization") or ""
    token = None
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip() or None
    if not token:
        token = request.cookies.get("supakiln_session")

    if token:
        hashed = hash_token(token)
        key = db.query(ApiKey).filter(ApiKey.hashed_key == hashed).first()
        if key is not None and key.revoked_at is None:
            key.revoked_at = datetime.utcnow()
            db.commit()

    response.delete_cookie("supakiln_session")
    return {"ok": True}


@router.get("/me", response_model=UserResponse, summary="Current authenticated user")
async def me(user: User = Depends(current_user)):
    return _user_response(user)
