"""Create the first admin user from env so operators can actually log in.

Runs at startup after migrations. If SUPAKILN_BOOTSTRAP_ADMIN_EMAIL /
SUPAKILN_BOOTSTRAP_ADMIN_PASSWORD are set and no admin exists yet, we
create that admin. If an admin already exists, we leave it alone —
operators can rotate the password via the /users API or directly in
the DB.
"""

from __future__ import annotations

import os

from db_models import SessionLocal, User
from auth.passwords import hash_password


def bootstrap_admin() -> None:
    email = os.environ.get("SUPAKILN_BOOTSTRAP_ADMIN_EMAIL")
    password = os.environ.get("SUPAKILN_BOOTSTRAP_ADMIN_PASSWORD")
    if not email or not password:
        return

    db = SessionLocal()
    try:
        existing_admin = (
            db.query(User)
            .filter(User.is_admin == 1, User.disabled == 0)
            .first()
        )
        if existing_admin is not None:
            print(f"✅ Admin already exists ({existing_admin.email}), "
                  f"skipping bootstrap")
            return

        existing = db.query(User).filter(User.email == email).first()
        if existing is not None:
            existing.is_admin = 1
            existing.disabled = 0
            if password:
                existing.password_hash = hash_password(password)
            db.commit()
            print(f"✅ Promoted existing user {email} to admin")
            return

        admin = User(
            email=email,
            password_hash=hash_password(password),
            is_admin=1,
            disabled=0,
        )
        db.add(admin)
        db.commit()
        print(f"✅ Bootstrapped admin user {email}")
    finally:
        db.close()
