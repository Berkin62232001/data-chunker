from fastapi import APIRouter

from db import repository
from db.session import get_session
from models.db_response_models import DashboardStats

router = APIRouter(prefix="/api/dashboard")


@router.get("/stats", response_model=DashboardStats)
def get_stats() -> DashboardStats:
    with get_session() as session:
        total_documents = repository.count_all_documents(session)
        total_projects = repository.count_all_projects(session)
        completed = repository.count_documents_by_phase(session, "chunked")
        upload_only = repository.count_documents_by_phase(session, "upload")
        in_progress = total_documents - completed - upload_only
    return DashboardStats(
        total_documents=total_documents,
        total_projects=total_projects,
        completed_documents=completed,
        documents_in_progress=max(0, in_progress),
    )
