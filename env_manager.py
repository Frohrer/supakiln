from cryptography.fernet import Fernet
from datetime import datetime
import os

# Canonical model + SYSTEM_USER_ID live in db_models; re-import locally so
# the manager always operates on the same table definition the rest of
# the app uses (the old duplicate class here caused table-redefinition
# headaches).
from db_models import EnvironmentVariable, SYSTEM_USER_ID


class EnvironmentManager:
    """Per-user Fernet-encrypted environment variables.

    Every mutator and reader takes `owner_user_id`. This keeps one user's
    secrets out of another's `get_all_variables()` result, which is what
    gets injected into the container on `/execute`. Unique key on
    `name` is per-user (composite, enforced in SQL with `_scoped_query`).

    NOTE: the old schema had `UNIQUE(name)` globally. The v9 migration
    added `owner_user_id` but left the unique constraint on `name`
    alone — that's a footgun if two different users want a `SECRET_KEY`
    variable. The variable model still has `unique=True` on `name`; we
    work around it by scoping lookups, but a future migration should
    drop that unique constraint and add a composite unique on
    `(owner_user_id, name)`. For now, names remain global across users
    and set_variable will raise on conflict.
    """

    def __init__(self, db_session, encryption_key=None):
        self.db = db_session
        if encryption_key:
            self.fernet = Fernet(encryption_key)
        else:
            # Generate a new key if none provided
            key = Fernet.generate_key()
            self.fernet = Fernet(key)
            # Store the key in a file for persistence
            with open('.env_key', 'wb') as key_file:
                key_file.write(key)

    def _scoped_query(self, owner_user_id: int):
        return self.db.query(EnvironmentVariable).filter(
            EnvironmentVariable.owner_user_id == owner_user_id
        )

    def set_variable(
        self,
        name: str,
        value: str,
        owner_user_id: int = SYSTEM_USER_ID,
        description: str = None,
    ) -> None:
        """Set an environment variable with encryption."""
        encrypted_value = self.fernet.encrypt(value.encode())
        var = self._scoped_query(owner_user_id).filter(
            EnvironmentVariable.name == name
        ).first()

        if var:
            var.value = encrypted_value.decode()
            var.updated_at = datetime.utcnow()
            if description is not None:
                var.description = description
        else:
            var = EnvironmentVariable(
                name=name,
                value=encrypted_value.decode(),
                description=description,
                owner_user_id=owner_user_id,
            )
            self.db.add(var)

        self.db.commit()

    def get_variable(self, name: str, owner_user_id: int = SYSTEM_USER_ID) -> str:
        """Get a decrypted environment variable value."""
        var = self._scoped_query(owner_user_id).filter(
            EnvironmentVariable.name == name
        ).first()
        if not var:
            return None

        try:
            decrypted_value = self.fernet.decrypt(var.value.encode())
            return decrypted_value.decode()
        except Exception:
            return None

    def get_variable_metadata(
        self, name: str, owner_user_id: int = SYSTEM_USER_ID
    ) -> dict:
        """Get environment variable metadata without the value."""
        var = self._scoped_query(owner_user_id).filter(
            EnvironmentVariable.name == name
        ).first()
        if not var:
            return None

        return {
            "name": var.name,
            "description": var.description,
            "created_at": var.created_at.isoformat(),
            "updated_at": var.updated_at.isoformat(),
        }

    def list_variables_with_metadata(
        self, owner_user_id: int = SYSTEM_USER_ID
    ) -> list:
        """List all environment variables with metadata but without values."""
        variables = []
        for var in self._scoped_query(owner_user_id).all():
            variables.append({
                "name": var.name,
                "description": var.description,
                "created_at": var.created_at.isoformat(),
                "updated_at": var.updated_at.isoformat(),
            })
        return variables

    def delete_variable(
        self, name: str, owner_user_id: int = SYSTEM_USER_ID
    ) -> bool:
        """Delete an environment variable."""
        var = self._scoped_query(owner_user_id).filter(
            EnvironmentVariable.name == name
        ).first()
        if var:
            self.db.delete(var)
            self.db.commit()
            return True
        return False

    def list_variables(self, owner_user_id: int = SYSTEM_USER_ID) -> list:
        """List all environment variable names."""
        return [var.name for var in self._scoped_query(owner_user_id).all()]

    def get_all_variables(
        self, owner_user_id: int = SYSTEM_USER_ID
    ) -> dict:
        """Get all environment variables as a dictionary.

        Call this with the executing user's id; the returned dict is what
        the executor injects into the container. Any leak here crosses
        the per-user isolation boundary.
        """
        variables = {}
        for var in self._scoped_query(owner_user_id).all():
            try:
                decrypted_value = self.fernet.decrypt(var.value.encode())
                variables[var.name] = decrypted_value.decode()
            except Exception:
                continue
        return variables
