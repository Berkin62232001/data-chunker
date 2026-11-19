from fastapi import APIRouter

from models.vector_status_models import VectorStatusResponse
from services.vector_index_service import check_qdrant_status

router = APIRouter(prefix="/api/vector")


@router.get("/status", response_model=VectorStatusResponse)
def get_vector_status() -> VectorStatusResponse:
    """Return Qdrant infrastructure status without crashing."""
    status = check_qdrant_status()
    return VectorStatusResponse(**status)
