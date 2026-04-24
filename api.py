from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import uvicorn
import os

# Import all routers
from routers import (
    auth as auth_router,
    containers,
    environment,
    execution,
    jobs,
    logs,
    proxy,
    services,
    users as users_router,
    webhook_execution,
    webhooks,
    workers,
)

# Import services and models for startup
from services.service_manager import service_manager
from models import SessionLocal, PersistentService


API_DESCRIPTION = """
Self-hosted, multi-language code execution platform. Run user-submitted
Python, Node.js, Ruby, Bash, or Go in isolated Docker containers with
package installation, scheduled jobs, webhook endpoints, and long-running
web services.

## Execution models

| Model | Entry point | Use case |
|---|---|---|
| **Ad-hoc** | `POST /execute` | Run a snippet and get stdout/stderr back |
| **Scheduled** | `POST /jobs` | Cron-triggered code |
| **Webhook** | `POST /webhook-jobs` → `POST /webhook/{path}` | Run on HTTP request |
| **Persistent service** | `POST /services` | Streamlit / FastAPI / Flask / Dash / Gradio (Python only) |

## Runtimes

Call `GET /languages` for the authoritative list and capabilities.
The default is `python`; specify `language` on any execution request to
pick another.

| Name | Package manager | Notes |
|---|---|---|
| `python` | pip | Streamlit/FastAPI/Flask/Dash/Gradio web-service detection |
| `node` | npm | Node.js 20, global `fetch` available |
| `ruby` | gem | — |
| `bash` | (none) | `curl` and `jq` preinstalled |
| `go` | (none) | stdlib only — dependency support is a follow-up |

## Worker lifecycle

Ad-hoc execution goes through a per-language HTTP worker container cached
per (language, package set). First call for a given cache key is cold
(image build + container create); subsequent calls are warm (~10-30ms
for interpreted languages). Use the `/workers` endpoints to list, evict,
or reset the cache. Idle workers are reaped automatically — see the
`SUPAKILN_WORKER_IDLE_TTL_SECONDS` environment variable.

## Request shape for execution

```json
{
  "code": "print('hello')",
  "language": "python",
  "packages": ["requests"],
  "timeout": 30
}
```

The response includes `output`, `error`, `container_id`, `timed_out`, and
a `timings_ms` breakdown (per-phase timing, useful for diagnosing cold
vs. warm paths).

## Isolation and limits

Every worker container runs as UID 1000 with ALL capabilities dropped,
512MB memory, 50% CPU quota, 100 PID limit. `/tmp` is a 128MB tmpfs
mounted `noexec` so user code can't store and run arbitrary binaries
there (Go is configured to compile outside `/tmp` for this reason).
Environment variables (managed via `/env`) are Fernet-encrypted at rest
and injected into the user subprocess at execution time.
"""

TAG_METADATA = [
    {"name": "auth",
     "description": "Log in, log out, introspect the current session."},
    {"name": "users",
     "description": "CRUD for users and API keys. Non-admins can manage "
                    "their own keys via `/users/me/keys`; admins can "
                    "manage every user via `/admin/users`."},
    {"name": "execution",
     "description": "Run code on demand and introspect the available runtimes."},
    {"name": "scheduled-jobs",
     "description": "Cron-triggered jobs. Each job stores its code, packages, "
                    "timeout, and target `language`."},
    {"name": "webhook-jobs",
     "description": "CRUD for webhook endpoints. The endpoint itself is served "
                    "under the `webhook-execution` tag."},
    {"name": "webhook-execution",
     "description": "Dynamic `/webhook/{path}` endpoints that resolve to a "
                    "configured webhook job and execute its code. Python jobs "
                    "get `request_data`/`response_data` auto-wrapping; other "
                    "languages receive request data via the "
                    "`SUPAKILN_REQUEST_DATA` env var and must emit a JSON "
                    "response on stdout."},
    {"name": "persistent-services",
     "description": "Long-running web apps (Streamlit, FastAPI, Flask, Dash, "
                    "Gradio). Python-only today — uses the legacy container "
                    "pipeline, not the worker path."},
    {"name": "workers",
     "description": "Lifecycle for ad-hoc worker containers cached by "
                    "`/execute`. List what's alive, force-stop one, or reset "
                    "the whole cache."},
    {"name": "containers",
     "description": "Legacy named-container CRUD, used by the frontend's "
                    "'saved containers' flow. The worker path's cache is "
                    "managed via the `workers` endpoints instead."},
    {"name": "environment",
     "description": "Fernet-encrypted environment variables injected into "
                    "every execution."},
    {"name": "logs",
     "description": "History of execution results (ad-hoc, scheduled, webhook, "
                    "service). Retained for 30 days."},
    {"name": "proxy",
     "description": "Reverse-proxy for running web services. `/proxy/{short_id}"
                    "/...` forwards to the container's published port."},
    {"name": "system",
     "description": "Health check, root, static files."},
]


app = FastAPI(
    title="supakiln",
    version="0.2.0",
    description=API_DESCRIPTION,
    openapi_tags=TAG_METADATA,
    contact={"name": "supakiln", "url": "https://github.com/Frohrer/supakiln"},
)

# CORS.
#
# With `allow_credentials=True`, browsers require Access-Control-Allow-
# Origin to echo a specific origin — the `*` shortcut is rejected. So
# we compute a concrete list: the env-provided ALLOWED_ORIGINS plus
# localhost dev defaults. The `allow_origin_regex` fallback handles
# ephemeral origins (Cloudflare preview URLs, etc.) when ENVIRONMENT
# is not `production`.
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
_allowed_origins = (
    [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
    if _allowed_origins_env
    else []
)
# Always allow the common dev origins so docker-compose works out of the box.
for dev_origin in (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
):
    if dev_origin not in _allowed_origins:
        _allowed_origins.append(dev_origin)

_allow_origin_regex = None
if os.environ.get("ENVIRONMENT", "").lower() != "production":
    # In dev, accept any localhost / 127.* port so ad-hoc vite servers
    # or preview builds also work.
    _allow_origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,  # Cache preflight requests for 24 hours
)

# Add a health check endpoint that bypasses Cloudflare Access
@app.get("/health", tags=["system"], summary="Health check")
async def health_check():
    """Liveness probe. Returns 200 once the app has started.

    Designed to bypass Cloudflare Access — configure this path as public
    in your Access rules so uptime checks don't need auth.
    """
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Mount static files - update the path to be relative to the current file
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", tags=["system"], summary="Serve the frontend shell", include_in_schema=False)
async def read_root():
    """Serves the frontend's index.html. Excluded from the OpenAPI schema."""
    return FileResponse("static/index.html")

# Include all routers
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(containers.router)
app.include_router(execution.router)
app.include_router(jobs.router)
app.include_router(webhooks.router)
app.include_router(services.router)
app.include_router(environment.router)
app.include_router(logs.router)
app.include_router(webhook_execution.router)
app.include_router(proxy.router)
app.include_router(workers.router)

async def startup_event():
    """Initialize services on startup."""
    import time
    import sys

    # Run database migration with retry logic
    max_retries = 5
    retry_delay = 2

    migration_success = False
    for attempt in range(max_retries):
        try:
            print(f"Running database migration (attempt {attempt + 1}/{max_retries})...")
            from migrate_database import migrate_database
            migrate_database()
            print("✅ Database migration completed successfully")
            migration_success = True
            break
        except Exception as e:
            print(f"❌ Database migration failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"⏳ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 1.5  # Exponential backoff
            else:
                print("💥 Failed to migrate database after all retries. Application cannot start.")
                print("This is a critical error - the application requires a proper database schema.")
                # Exit the application if migration fails
                sys.exit(1)

    if not migration_success:
        print("💥 Database migration failed. Application cannot start safely.")
        sys.exit(1)

    # Create the admin user from SUPAKILN_BOOTSTRAP_ADMIN_EMAIL /
    # _PASSWORD if set and no admin exists yet. Runs after migrations
    # so the users table is guaranteed to exist.
    try:
        from auth import bootstrap_admin
        bootstrap_admin()
    except Exception as e:
        print(f"⚠️ Admin bootstrap failed (non-fatal): {e}")

    # Clean up orphaned containers from previous runs/crashes
    try:
        from cleanup import reconcile_orphaned_containers, prune_dead_containers
        from scheduler import scheduler

        # First remove any dead/exited containers
        dead = prune_dead_containers()
        if dead:
            print(f"🧹 Removed {dead} dead containers from previous run")

        # Then reconcile orphans against the executor's tracking state
        orphans = reconcile_orphaned_containers(scheduler.executor)
        if orphans:
            print(f"🧹 Removed {orphans} orphaned containers from previous run")
        else:
            print("✅ No orphaned containers found")
    except Exception as e:
        print(f"⚠️ Startup cleanup failed (non-fatal): {e}")

    # Initialize scheduler after migration is complete
    try:
        from scheduler import scheduler
        scheduler.initialize()
        print("✅ Scheduler initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize scheduler: {e}")

    # Auto-start services marked for auto-start
    try:
        print("🚀 Starting auto-start services...")
        db = SessionLocal()
        try:
            auto_start_services = db.query(PersistentService).filter(
                PersistentService.auto_start == 1,
                PersistentService.is_active == 1
            ).all()

            if auto_start_services:
                print(f"Found {len(auto_start_services)} services to auto-start")
                for service in auto_start_services:
                    try:
                        print(f"Starting service: {service.name}")
                        service_manager.start_service(service.id, db)
                        print(f"✅ Service {service.name} started successfully")
                    except Exception as e:
                        print(f"❌ Failed to start service {service.name}: {e}")
            else:
                print("No services configured for auto-start")
        finally:
            db.close()
    except Exception as e:
        print(f"❌ Error during service auto-start: {e}")

    print("🎉 Application startup completed")

async def shutdown_event():
    """Graceful shutdown: clean up all containers and stop scheduler."""
    print("🛑 Application shutting down...")
    try:
        from scheduler import scheduler
        scheduler.executor.shutdown()
        scheduler.scheduler.shutdown(wait=False)
        print("✅ Cleanup complete")
    except Exception as e:
        print(f"⚠️ Error during shutdown cleanup: {e}")

# Add startup event
@app.on_event("startup")
async def on_startup():
    await startup_event()

@app.on_event("shutdown")
async def on_shutdown():
    await shutdown_event()

if __name__ == "__main__":
    # Create static directory if it doesn't exist
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000) 