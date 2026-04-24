"""Opaque bearer tokens for both API keys and sessions.

Format: "supa_<base64url(32 random bytes)>". 43 chars of entropy after
the prefix; URL-safe, no padding.

At rest we store sha256(plaintext) as hex (64 chars). Lookups hash the
incoming token first, so the plaintext only ever lives in the user's
client and in memory during one request.

The `prefix` column stores the first 12 chars of the plaintext (the
"supa_" tag + 7 id chars) so UIs can show "supa_ABC1234…" in a list
without revealing the rest.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Tuple


TOKEN_PREFIX = "supa_"
_RANDOM_BYTES = 32
_PREFIX_LEN = 12  # "supa_" + 7 chars

# 14-day session token TTL. API keys are long-lived (no TTL).
SESSION_TTL_SECONDS = 60 * 60 * 24 * 14


def generate_token() -> Tuple[str, str, str]:
    """Return (plaintext, hashed_hex, prefix_for_display)."""
    plaintext = TOKEN_PREFIX + secrets.token_urlsafe(_RANDOM_BYTES)
    hashed = hash_token(plaintext)
    prefix = plaintext[:_PREFIX_LEN]
    return plaintext, hashed, prefix


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
