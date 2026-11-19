from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import files, health, jobs, llm, projects
from api.routes import documents as documents_route
from api.routes import audit_routes, dashboard
from api.routes import vector_routes
from core.config import settings
from core.request_security import RequestSecurityMiddleware
from utils.storage_paths import UnsafeStoragePath
from db.init_db import init_db
from services.job_service import JobService


@asynccontextmanager
async def lifespan(app: FastAPI):
    for directory in [
        settings.raw_uploads_dir,
        settings.converted_dir,
        settings.chunks_dir,
        settings.llm_payloads_dir,
        settings.projects_dir,
        settings.audit_log_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    init_db()
    JobService().mark_stale_jobs_interrupted()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="File ingestion and chunking pipeline for LLM applications.",
    lifespan=lifespan,
)

@app.exception_handler(UnsafeStoragePath)
async def invalid_storage_path(request, exc):
    return JSONResponse(status_code=422, content={"detail": "Invalid storage identifier or path."})


app.add_middleware(RequestSecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["system"])
app.include_router(files.router, tags=["files"])
app.include_router(jobs.router, tags=["jobs"])
app.include_router(llm.router, tags=["llm"])
app.include_router(projects.router, tags=["projects"])
app.include_router(documents_route.router, tags=["documents"])
app.include_router(audit_routes.router, tags=["audit"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(vector_routes.router, tags=["vector"])
