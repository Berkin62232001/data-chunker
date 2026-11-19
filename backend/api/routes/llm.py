from utils.storage_paths import storage_path
from fastapi import APIRouter, HTTPException

from core.config import settings
from models.llm_gateway_models import AskRequest, AskResponse
from services.llm_gateway.gateway import LLMGateway

router = APIRouter(prefix="/api/llm")
_gateway = LLMGateway()


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    chunks_dir = storage_path(settings.chunks_dir, request.document_id)
    if not (chunks_dir / "chunks.jsonl").exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks not found. Run POST /api/files/{document_id}/chunk first.",
        )
    return _gateway.ask(request)
