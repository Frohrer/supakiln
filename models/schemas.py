from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class CodeExecutionRequest(BaseModel):
    """Body for `POST /execute` and `POST /execute-web-service`."""

    code: Optional[str] = Field(
        None,
        description="Source to execute. If omitted, `job_id` must be set so "
                    "the server can fetch the code from a scheduled job.",
    )
    job_id: Optional[int] = Field(
        None,
        description="Execute the code stored for this scheduled job. "
                    "Mutually useful with an empty `code`.",
    )
    packages: Optional[List[str]] = Field(
        None,
        description="Package specifiers for the selected runtime's package "
                    "manager. pip/npm/gem syntax supported; ignored for "
                    "bash and go.",
    )
    timeout: Optional[int] = Field(
        30,
        description="Max execution wall-time in seconds.",
    )
    container_id: Optional[str] = Field(
        None,
        description="Legacy: run in this already-named container via docker "
                    "exec. Bypasses the worker cache. Prefer omitting.",
    )
    language: Optional[str] = Field(
        "python",
        description="Runtime name (see `GET /languages`).",
        examples=["python", "node", "ruby", "bash", "go"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"code": "print('hello')", "language": "python",
                 "packages": [], "timeout": 30},
                {"code": "const _ = require('lodash'); "
                         "console.log(_.sum([1,2,3,4]))",
                 "language": "node", "packages": ["lodash"], "timeout": 60},
                {"code": "echo \"bash $BASH_VERSION\"; uname -a",
                 "language": "bash", "timeout": 10},
            ]
        }
    }


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
    """Body for `POST /jobs` and `PUT /jobs/{id}`."""

    name: str = Field(..., description="Human-readable name for the job.")
    code: str = Field(..., description="Source executed on every cron tick.")
    cron_expression: str = Field(
        ...,
        description="Standard 5-field crontab (minute hour dom month dow).",
        examples=["*/5 * * * *", "0 0 * * *"],
    )
    container_id: Optional[str] = None
    packages: Optional[List[str]] = Field(
        None,
        description="Package specifiers for the runtime's package manager.",
    )
    timeout: Optional[int] = Field(30, description="Max seconds per run.")
    language: Optional[str] = Field(
        "python",
        description="Runtime name (see `GET /languages`).",
    )

class ScheduledJobResponse(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    cron_expression: str
    container_id: Optional[str]
    packages: Optional[str]
    created_at: str
    last_run: Optional[str]
    is_active: bool
    timeout: int
    language: Optional[str] = "python"

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
    """Body for `POST /webhook-jobs` and `PUT /webhook-jobs/{id}`.

    Once created, the job is reachable at `/webhook/{endpoint}` via any
    HTTP method. For Python jobs, the request is auto-wrapped: user code
    has access to a `request_data` dict and should write the response
    into a `response_data` variable. For other languages, request data
    arrives via the `SUPAKILN_REQUEST_DATA` env var (JSON-encoded) and
    the user code must print the JSON response to stdout.
    """

    name: str = Field(..., description="Human-readable name.")
    endpoint: str = Field(
        ...,
        description="URL path the webhook is served under (leading slash "
                    "optional). Final URL: `/webhook{endpoint}`.",
        examples=["/stripe-events", "/github-ci"],
    )
    code: str = Field(..., description="Source executed on each request.")
    container_id: Optional[str] = None
    packages: Optional[List[str]] = None
    timeout: Optional[int] = Field(30, description="Max seconds per call.")
    description: Optional[str] = None
    language: Optional[str] = Field(
        "python",
        description="Runtime name (see `GET /languages`).",
    )

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
    language: Optional[str] = "python"

class PersistentServiceRequest(BaseModel):
    name: str
    code: str
    container_id: Optional[str] = None
    packages: Optional[List[str]] = None
    restart_policy: Optional[str] = "always"  # always, never, on-failure
    description: Optional[str] = None
    auto_start: Optional[bool] = True
    language: Optional[str] = "python"

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


# ---------------------------------------------------------------------
# Auth / users / API keys
# ---------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    """Issued on successful login. `session_token` is also set as an
    HttpOnly cookie; callers that prefer Authorization headers can use
    the token directly."""

    session_token: str
    user: "UserResponse"


class UserResponse(BaseModel):
    id: int
    email: str
    is_admin: bool
    disabled: bool
    created_at: str


class UserCreateRequest(BaseModel):
    """Admin-only endpoint body for creating new users."""

    email: str
    password: str
    is_admin: Optional[bool] = False


class UserUpdateRequest(BaseModel):
    """Admin-only endpoint body for updating a user.

    All fields optional; pass only the ones you want to change. Setting
    `password` to non-empty resets the user's password.
    """

    email: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    disabled: Optional[bool] = None


class ApiKeyCreateRequest(BaseModel):
    label: Optional[str] = None


class ApiKeyCreateResponse(BaseModel):
    """Plaintext token is returned exactly once. Store it somewhere
    durable immediately; the server only retains its hash."""

    id: int
    token: str
    prefix: str
    label: Optional[str]
    created_at: str


class ApiKeyResponse(BaseModel):
    id: int
    prefix: str
    label: Optional[str]
    last_used_at: Optional[str]
    created_at: str


LoginResponse.model_rebuild()
 