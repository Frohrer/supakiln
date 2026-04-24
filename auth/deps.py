"""FastAPI dependencies: resolve the caller to a User row.

Two entry points:

  current_user    — accepts Bearer header / session cookie, falls back
                    to the system user when SUPAKILN_ALLOW_ANONYMOUS is
                    on. Returns a User.
  require_admin   — same resolution, but rejects non-admins with 403.

Keep these cheap: one indexed SELECT on `hashed_key`, one SELECT on
`users`. A token's `last_used_at` is bumped at most once per N seconds
to avoid hammering the DB on the hot path.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from db_models import ApiKey, User, SYSTEM_USER_ID
from auth.tokens import hash_token


def _allow_anonymous() -> bool:
    return os.environ.get("SUPAKILN_ALLOW_ANONYMOUS", "true").lower() != "false"


# Throttle `last_used_at` updates. 60s is fine-grained enough for
# audit/UX and keeps us off the DB write path on tight hot loops.
_LAST_USED_THROTTLE_SECONDS = 60
_last_used_cache: dict = {}
_last_used_lock = threading.Lock()


def _maybe_bump_last_used(db: Session, key: ApiKey) -> None:
    now = time.time()
    with _last_used_lock:
        prev = _last_used_cache.get(key.id, 0.0)
        if now - prev < _LAST_USED_THROTTLE_SECONDS:
            return
        _last_used_cache[key.id] = now
    key.last_used_at = datetime.utcnow()
    db.commit()


def _extract_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    cookie = request.cookies.get("supakiln_session")
    if cookie:
        return cookie
    return None


def get_or_create_system_user(db: Session) -> User:
    user = db.query(User).filter(User.id == SYSTEM_USER_ID).first()
    if user is not None:
        return user
    # Migration is supposed to seed id=1; if it didn't, create it now
    # so anonymous fallback still works.
    user = User(
        id=SYSTEM_USER_ID,
        email="system@supakiln.local",
        password_hash=None,
        is_admin=0,
        disabled=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = _extract_token(request)

    if token is None:
        if _allow_anonymous():
            return get_or_create_system_user(db)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    hashed = hash_token(token)
    key = (
        db.query(ApiKey)
        .filter(ApiKey.hashed_key == hashed, ApiKey.revoked_at.is_(None))
        .first()
    )
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
        )
    if key.expires_at is not None and key.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token expired",
        )

    user = db.query(User).filter(User.id == key.user_id).first()
    if user is None or user.disabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not available",
        )

    _maybe_bump_last_used(db, key)
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin only",
        )
    return user
