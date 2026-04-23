from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import uvicorn
import os

# Import all routers
from routers import containers, execution, jobs, webhooks, services, environment, logs, webhook_execution, proxy, workers

# Import services and models for startup
from services.service_manager import service_manager
from models import SessionLocal, PersistentService

app = FastAPI(title="Code Execution Engine API")

# Add CORS middleware with permissive settings since Cloudflare bypasses OPTIONS to origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins since Cloudflare handles the actual filtering
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
    max_age=86400,  # Cache preflight requests for 24 hours
)

# Add a health check endpoint that bypasses Cloudflare Access
@app.get("/health")
async def health_check():
    """
    Health check endpoint that should bypass Cloudflare Access.
    Configure this endpoint to be public in your Cloudflare Access rules.
    """
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Mount static files - update the path to be relative to the current file
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def read_root():
    """Serve the main page."""
    return FileResponse("static/index.html")

# Include all routers
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