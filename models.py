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

class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer)  # Null for manual executions
    code = Column(Text, nullable=False)
    output = Column(Text)
    error = Column(Text)
    container_id = Column(String(100))
    execution_time = Column(Float)  # in seconds
    started_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20))  # success, error, timeout

# Create database and tables
engine = create_engine('sqlite:///code_executor.db')
Base.metadata.create_all(engine)

# Create session factory
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 