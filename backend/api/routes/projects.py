from fastapi import APIRouter, HTTPException

from db import repository
from db.session import get_session
from models.db_response_models import ProjectListItem, ProjectListResponse
from models.project_models import (
    AddDocumentRequest,
    Project,
    ProjectAskRequest,
    ProjectAskResponse,
    ProjectCreateRequest,
    ProjectSearchRequest,
    ProjectSearchResponse,
)
from services.project_service import ProjectService

router = APIRouter(prefix="/api/projects")
_svc = ProjectService()


@router.get("", response_model=ProjectListResponse)
def list_projects() -> ProjectListResponse:
    with get_session() as session:
        projects = repository.list_projects(session)
        items = [
            ProjectListItem(
                project_id=p.project_id,
                name=p.name,
                document_count=repository.count_project_documents(session, p.project_id),
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in projects
        ]
    return ProjectListResponse(total=len(items), projects=items)


@router.post("", response_model=Project)
def create_project(request: ProjectCreateRequest) -> Project:
    return _svc.create(request)


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    try:
        return _svc.get(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.")


@router.post("/{project_id}/add-document", response_model=Project)
def add_document(project_id: str, request: AddDocumentRequest) -> Project:
    try:
        return _svc.add_document(project_id, request)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/{project_id}/search", response_model=ProjectSearchResponse)
def search_project(project_id: str, request: ProjectSearchRequest) -> ProjectSearchResponse:
    try:
        return _svc.search(project_id, request)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.")


@router.post("/{project_id}/ask", response_model=ProjectAskResponse)
def ask_project(project_id: str, request: ProjectAskRequest) -> ProjectAskResponse:
    try:
        return _svc.ask(project_id, request)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
