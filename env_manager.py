from cryptography.fernet import Fernet
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import os
import base64

Base = declarative_base()

class EnvironmentVariable(Base):
    __tablename__ = "environment_variables"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=False)  # Encrypted value
    description = Column(String)  # Optional description
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class EnvironmentManager:
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

    def set_variable(self, name: str, value: str, description: str = None) -> None:
        """Set an environment variable with encryption."""
        encrypted_value = self.fernet.encrypt(value.encode())
        var = self.db.query(EnvironmentVariable).filter_by(name=name).first()
        
        if var:
            var.value = encrypted_value.decode()
            var.updated_at = datetime.utcnow()
            if description is not None:
                var.description = description
        else:
            var = EnvironmentVariable(
                name=name,
                value=encrypted_value.decode(),
                description=description
            )
            self.db.add(var)
        
        self.db.commit()

    def get_variable(self, name: str) -> str:
        """Get a decrypted environment variable value."""
        var = self.db.query(EnvironmentVariable).filter_by(name=name).first()
        if not var:
            return None
        
        try:
            decrypted_value = self.fernet.decrypt(var.value.encode())
            return decrypted_value.decode()
        except Exception:
            return None

    def get_variable_metadata(self, name: str) -> dict:
        """Get environment variable metadata without the value."""
        var = self.db.query(EnvironmentVariable).filter_by(name=name).first()
        if not var:
            return None
        
        return {
            "name": var.name,
            "description": var.description,
            "created_at": var.created_at.isoformat(),
            "updated_at": var.updated_at.isoformat()
        }

    def list_variables_with_metadata(self) -> list:
        """List all environment variables with metadata but without values."""
        variables = []
        for var in self.db.query(EnvironmentVariable).all():
            variables.append({
                "name": var.name,
                "description": var.description,
                "created_at": var.created_at.isoformat(),
                "updated_at": var.updated_at.isoformat()
            })
        return variables

    def delete_variable(self, name: str) -> bool:
        """Delete an environment variable."""
        var = self.db.query(EnvironmentVariable).filter_by(name=name).first()
        if var:
            self.db.delete(var)
            self.db.commit()
            return True
        return False

    def list_variables(self) -> list:
        """List all environment variable names."""
        return [var.name for var in self.db.query(EnvironmentVariable).all()]

    def get_all_variables(self) -> dict:
        """Get all environment variables as a dictionary."""
        variables = {}
        for var in self.db.query(EnvironmentVariable).all():
            try:
                decrypted_value = self.fernet.decrypt(var.value.encode())
                variables[var.name] = decrypted_value.decode()
            except Exception:
                continue
        return variables 