from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class CodeExecutionRequest(BaseModel):
    code: Optional[str] = None
    job_id: Optional[int] = None
    packages: Optional[List[str]] = None
    timeout: Optional[int] = 30
    container_id: Optional[str] = None

class PackageInstallRequest(BaseModel):
    name: str
    packages: List[str]

class ContainerResponse(BaseModel):
    container_id: str
    name: str
    packages: List[str]
    created_at: str
    code: Optional[str] = None

class ScheduledJobRequest(BaseModel):
    name: str
    code: str
    cron_expression: str
    container_id: Optional[str] = None
    packages: Optional[List[str]] = None
    timeout: Optional[int] = 30

class ScheduledJobResponse(BaseModel):
    id: int
    name: str
    cron_expression: str
    container_id: Optional[str]
    packages: Optional[str]
    created_at: str
    last_run: Optional[str]
    is_active: bool
    timeout: int

class ExecutionLogResponse(BaseModel):
    id: int
    job_id: Optional[int]
    webhook_job_id: Optional[int]
    code: str
    output: Optional[str]
    error: Optional[str]
    container_id: Optional[str]
    execution_time: float
    started_at: str
    status: str
    request_data: Optional[str]
    response_data: Optional[str]

class EnvVarRequest(BaseModel):
    name: str
    value: str
    description: Optional[str] = None

class EnvVarResponse(BaseModel):
    name: str
    created_at: str
    updated_at: str

class EnvVarMetadata(BaseModel):
    name: str
    description: Optional[str]
    created_at: str
    updated_at: str

class WebhookJobRequest(BaseModel):
    name: str
    endpoint: str  # URL path like /webhook/my-job
    code: str
    container_id: Optional[str] = None
    packages: Optional[List[str]] = None
    timeout: Optional[int] = 30
    description: Optional[str] = None

class WebhookJobResponse(BaseModel):
    id: int
    name: str
    endpoint: str
    code: str
    container_id: Optional[str]
    packages: Optional[str]
    created_at: str
    last_triggered: Optional[str]
    is_active: bool
    timeout: int
    description: Optional[str]

class PersistentServiceRequest(BaseModel):
    name: str
    code: str
    container_id: Optional[str] = None
    packages: Optional[List[str]] = None
    restart_policy: Optional[str] = "always"  # always, never, on-failure
    description: Optional[str] = None
    auto_start: Optional[bool] = True

class PersistentServiceResponse(BaseModel):
    id: int
    name: str
    code: str
    container_id: Optional[str]
    packages: Optional[str]
    created_at: str
    started_at: Optional[str]
    last_restart: Optional[str]
    is_active: bool
    status: str  # stopped, starting, running, error, restarting
    restart_policy: str
    description: Optional[str]
    process_id: Optional[str]
    auto_start: bool 