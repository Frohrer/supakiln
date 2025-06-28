from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import uvicorn
import os

# Import all routers
from routers import containers, execution, jobs, webhooks, services, environment, logs, webhook_execution

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

async def startup_event():
    """Initialize services on startup."""
    try:
        # Run database migration
        from migrate_database import migrate_database
        migrate_database()
        print("Database migration completed")
        
        # Auto-start services marked for auto-start
        db = SessionLocal()
        try:
            auto_start_services = db.query(PersistentService).filter(
                PersistentService.auto_start == 1,
                PersistentService.is_active == 1
            ).all()
            
            for service in auto_start_services:
                print(f"Auto-starting service: {service.name}")
                service_manager.start_service(service.id, db)
        finally:
            db.close()
            
    except Exception as e:
        print(f"Startup error: {e}")

# Add startup event
@app.on_event("startup")
async def on_startup():
    await startup_event()

if __name__ == "__main__":
    # Create static directory if it doesn't exist
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000) 