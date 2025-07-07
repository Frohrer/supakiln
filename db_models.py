from sqlalchemy import Column, Integer, String, DateTime, Text, Float, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class EnvironmentVariable(Base):
    __tablename__ = "environment_variables"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=False)  # Encrypted value
    description = Column(Text)  # Optional description
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    code = Column(Text, nullable=False)
    cron_expression = Column(String(100), nullable=False)
    container_id = Column(String(100))
    packages = Column(Text)  # Stored as comma-separated string
    created_at = Column(DateTime, default=datetime.utcnow)
    last_run = Column(DateTime)
    is_active = Column(Integer, default=1)  # 1 for active, 0 for inactive
    timeout = Column(Integer, default=30)  # Timeout in seconds

class WebhookJob(Base):
    __tablename__ = "webhook_jobs"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    endpoint = Column(String(200), unique=True, nullable=False)  # URL path like /webhook/my-job
    code = Column(Text, nullable=False)
    container_id = Column(String(100))
    packages = Column(Text)  # Stored as comma-separated string
    created_at = Column(DateTime, default=datetime.utcnow)
    last_triggered = Column(DateTime)
    is_active = Column(Integer, default=1)  # 1 for active, 0 for inactive
    timeout = Column(Integer, default=30)  # Timeout in seconds
    description = Column(Text)  # Optional description

class PersistentService(Base):
    __tablename__ = "persistent_services"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    code = Column(Text, nullable=False)
    container_id = Column(String(100))
    packages = Column(Text)  # Stored as comma-separated string
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    last_restart = Column(DateTime)
    is_active = Column(Integer, default=1)  # 1 for active, 0 for inactive
    status = Column(String(20), default="stopped")  # stopped, starting, running, error, restarting
    restart_policy = Column(String(20), default="always")  # always, never, on-failure
    description = Column(Text)  # Optional description
    process_id = Column(String(100))  # Docker exec process ID for running services
    auto_start = Column(Integer, default=1)  # 1 to auto-start on system startup

class ExposedPort(Base):
    __tablename__ = "exposed_ports"
    
    id = Column(Integer, primary_key=True)
    container_id = Column(String(100), nullable=False)
    internal_port = Column(Integer, nullable=False)  # Port inside container
    external_port = Column(Integer, nullable=False)  # Exposed port on host
    service_name = Column(String(100))  # Optional name for the service
    service_type = Column(String(50))  # streamlit, fastapi, flask, dash, etc.
    proxy_path = Column(String(200), unique=True, nullable=False)  # Unique path for proxy access
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime)
    is_active = Column(Integer, default=1)  # 1 for active, 0 for inactive
    description = Column(Text)  # Optional description

class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer)  # Null for manual executions
    webhook_job_id = Column(Integer)  # For webhook job executions
    service_id = Column(Integer)  # For persistent service executions
    code = Column(Text, nullable=False)
    output = Column(Text)
    error = Column(Text)
    container_id = Column(String(100))
    execution_time = Column(Float)  # in seconds
    started_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20))  # success, error, timeout, running
    request_data = Column(Text)  # For webhook jobs: the request payload
    response_data = Column(Text)  # For webhook jobs: the response payload

# Create database engine and session factory
# Use data directory for writable files when in container, fallback to current dir for development
db_path = '/app/data/code_executor.db' if os.path.exists('/app/data') else 'code_executor.db'
engine = create_engine(f'sqlite:///{db_path}')
SessionLocal = sessionmaker(bind=engine)

# Note: Tables are created by the migration system in migrate_database.py
# This ensures proper version tracking and schema migrations

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 