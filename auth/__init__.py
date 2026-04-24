"""Authentication and authorization primitives.

All auth state lives in two tables (see db_models.py):

  users      — id, email, password_hash, is_admin, disabled.
  api_keys   — id, user_id, hashed_key (sha256 hex of plaintext), prefix,
               kind ('api' or 'session'), expires_at.

Request authentication accepts either:
  - `Authorization: Bearer <plaintext-token>` header, or
  - `supakiln_session=<plaintext-token>` cookie.

Both map to the same api_keys table; sessions just have a kind='session'
and an expires_at. The plaintext is never stored; lookups always hash
first and match on `hashed_key`.

Transition mode: while SUPAKILN_ALLOW_ANONYMOUS=true (default), a request
without credentials is attributed to the system user (id=1). Once you're
ready to require auth for everyone, set SUPAKILN_ALLOW_ANONYMOUS=false
and anonymous requests return 401.
"""

from auth.passwords import hash_password, verify_password
from auth.tokens import (
    generate_token,
    hash_token,
    SESSION_TTL_SECONDS,
)
from auth.deps import current_user, require_admin, get_or_create_system_user
from auth.bootstrap import bootstrap_admin

__all__ = [
    "hash_password",
    "verify_password",
    "generate_token",
    "hash_token",
    "SESSION_TTL_SECONDS",
    "current_user",
    "require_admin",
    "get_or_create_system_user",
    "bootstrap_admin",
]
