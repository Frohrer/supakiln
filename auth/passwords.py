"""Password hashing with argon2id.

argon2-cffi's PasswordHasher picks the OWASP-recommended parameters by
default; we don't override them. `verify` throws on mismatch/invalid
hash, so we wrap it to a bool.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash


_hasher = PasswordHasher()


def hash_password(plaintext: str) -> str:
    return _hasher.hash(plaintext)


def verify_password(hashed: str, plaintext: str) -> bool:
    try:
        _hasher.verify(hashed, plaintext)
        return True
    except (VerifyMismatchError, InvalidHash):
        return False
