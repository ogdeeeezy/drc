"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.deps import get_job_manager
from backend.api.routes import drc, fix, layout, pdk, upload

app = FastAPI(
    title="Agentic DRC",
    description="Open-source DRC tool for semiconductor layout verification",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(upload.router, prefix="/api")
app.include_router(drc.router, prefix="/api")
app.include_router(fix.router, prefix="/api")
app.include_router(layout.router, prefix="/api")
app.include_router(pdk.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/jobs")
async def list_jobs():
    """List all DRC jobs."""
    manager = get_job_manager()
    return {"jobs": [j.to_dict() for j in manager.list_jobs()]}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job details."""
    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        from fastapi import HTTPException
        raise HTTPException(404, f"Job '{job_id}' not found")
    return job.to_dict()
