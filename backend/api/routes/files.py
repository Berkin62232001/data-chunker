from utils.storage_paths import storage_path
import json as _json_module
import re as _re
from pathlib import Path
from typing import Optional

# Matches absolute Unix storage paths that should never appear in API responses.
_ABS_PATH_RE = _re.compile(r"/(?:app|home|Users|private|tmp|var|storage)/[^\s\"'<>]+")

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from core.config import settings
from db import repository
from db.session import get_session
from models.chunk_models import ChunkingResult
from models.conversion_models import ConversionResult
from models.evaluation_models import (
    ChunkQualityReport,
    RetrievalEvaluationRequest,
    RetrievalEvaluationResponse,
    RetrievalEvaluationSetRequest,
    RetrievalEvaluationSetResponse,
    TokenEfficiencySummary,
)
from models.file_models import DocumentPreview, InitializeResult, UploadResponse
from models.grounded_answer_models import GroundedAnswerRequest, GroundedAnswerResponse
from models.pipeline_models import PipelineDecision
from models.profile_models import DocumentProfile
from models.integrity_models import IntegrityReport
from models.job_models import JobDetail
from models.llm_payload_models import EstimateContextRequest, EstimateContextResponse, LLMPayloadRequest, LLMPayloadResponse
from models.security_models import SecurityReport
from models.search_models import SearchRequest, SearchResponse
from models.hybrid_search_models import HybridSearchRequest, HybridSearchResponse
from models.vector_models import IndexResponse, SemanticSearchRequest, SemanticSearchResponse
from models.ocr_models import OCRStatusResponse
from models.vector_status_models import DocumentIndexStatusResponse
from services.chunking_service import ChunkingService
from services.chunk_quality_service import ChunkQualityService
from services.conversion_service import ConversionService
from services.document_profiler import DocumentProfiler
from services.grounded_answer_service import GroundedAnswerService
from services.hybrid_search_service import HybridSearchService
from services.integrity_service import IntegrityService
from services.job_service import JobService
from services.llm_payload_service import LLMPayloadService
from services.pipeline_decision_engine import PipelineDecisionEngine
from services.search_service import SearchService
from services.security_report_service import SecurityReportService
from services.retrieval_evaluation_service import RetrievalEvaluationService
from services.token_efficiency_service import TokenEfficiencyService
from services.upload_service import handle_upload
from services.ocr_service import LocalOCRService
from services.document_job_service import (
    run_chunk_job,
    run_convert_job,
    run_grounded_answer_job,
    run_index_job,
    run_retrieval_evaluation_job,
)
from services.vector_index_service import (
    VectorIndexError,
    VectorIndexService,
    check_document_index_status,
    check_qdrant_status,
)

router = APIRouter(prefix="/api/files")

# ── Export constants ──────────────────────────────────────────────────────────

_ALLOWED_ARTIFACTS = frozenset({"markdown", "chunks", "metadata", "profile", "pipeline", "integrity"})

# (storage_key, filename, media_type, extension)
_ARTIFACT_CONFIG: dict = {
    "markdown": ("converted", "document.md",            "text/markdown",         ".md"),
    "chunks":   ("chunks",    "chunks.jsonl",            "application/jsonlines", ".jsonl"),
    "metadata": ("converted", "metadata.json",           "application/json",      ".json"),
    "profile":  ("raw",       "profile.json",            "application/json",      ".json"),
    "pipeline": ("raw",       "pipeline_decision.json",  "application/json",      ".json"),
}


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    safe = "".join(c if c.isalnum() or c in (".", "-", "_") else "_" for c in stem)
    return safe[:64] or "document"


def _artifact_file_path(document_id: str, artifact: str) -> Path:
    storage_key, file_name, _, _ = _ARTIFACT_CONFIG[artifact]
    if storage_key == "converted":
        return storage_path(settings.converted_dir, document_id, file_name)
    if storage_key == "chunks":
        return storage_path(settings.chunks_dir, document_id, file_name)
    return storage_path(settings.raw_uploads_dir, document_id, file_name)


def _vector_error_detail(message: str, indexed: Optional[bool] = None) -> dict:
    safe_message = _ABS_PATH_RE.sub("[redacted-path]", message)
    error_type = _vector_error_type(safe_message)
    detail = {
        "message": safe_message,
        "error_type": error_type,
        "qdrant_configured": True,
        "qdrant_available": error_type != "qdrant_unavailable",
        "embedding_provider": settings.embedding_provider,
    }
    if indexed is not None:
        detail["indexed"] = indexed
    return detail


def _vector_error_type(message: str) -> str:
    lower = message.lower()
    if lower.startswith("lm studio") or "embedding_model" in lower or "embedding provider" in lower:
        return "embedding_provider"
    if "vector size does not match" in lower:
        return "qdrant_dimension_mismatch"
    return "qdrant_unavailable"


_profiler = DocumentProfiler()
_engine = PipelineDecisionEngine()
_conv = ConversionService()
_chunker = ChunkingService()
_integrity = IntegrityService()
_search = SearchService()
_llm_payload = LLMPayloadService()
_vector_index = VectorIndexService()
_hybrid = HybridSearchService()
_security = SecurityReportService()
_chunk_quality = ChunkQualityService()
_retrieval_eval = RetrievalEvaluationService()
_token_efficiency = TokenEfficiencyService()
_grounded_answer = GroundedAnswerService()
_jobs = JobService()


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:
    return await handle_upload(file)


@router.get("/{document_id}/profile", response_model=DocumentProfile)
def get_profile(document_id: str) -> DocumentProfile:
    doc_dir = storage_path(settings.raw_uploads_dir, document_id)
    if not (doc_dir / "metadata.json").exists():
        raise HTTPException(status_code=404, detail="Document not found.")
    return _profiler.profile(document_id)


@router.get("/{document_id}/pipeline", response_model=PipelineDecision)
def get_pipeline(document_id: str) -> PipelineDecision:
    doc_dir = storage_path(settings.raw_uploads_dir, document_id)
    if not (doc_dir / "profile.json").exists():
        raise HTTPException(
            status_code=404,
            detail="Profile not found. Run GET /api/files/{document_id}/profile first.",
        )
    return _engine.decide(document_id)


@router.post("/{document_id}/convert", response_model=ConversionResult)
def convert_document(document_id: str) -> ConversionResult:
    doc_dir = storage_path(settings.raw_uploads_dir, document_id)
    if not (doc_dir / "pipeline_decision.json").exists():
        raise HTTPException(
            status_code=404,
            detail="Pipeline decision not found. Run GET /api/files/{document_id}/pipeline first.",
        )
    return _conv.convert(document_id)


@router.post("/{document_id}/convert/job", response_model=JobDetail)
def convert_document_job(document_id: str, background_tasks: BackgroundTasks) -> JobDetail:
    doc_dir = storage_path(settings.raw_uploads_dir, document_id)
    if not (doc_dir / "pipeline_decision.json").exists():
        raise HTTPException(
            status_code=404,
            detail="Pipeline decision not found. Run GET /api/files/{document_id}/pipeline first.",
        )
    job = _jobs.create_job(
        job_type="convert",
        document_id=document_id,
        request={"operation": "convert"},
    )
    background_tasks.add_task(run_convert_job, job.job_id, document_id)
    return job


@router.get("/{document_id}/converted", response_model=ConversionResult)
def get_converted(document_id: str) -> ConversionResult:
    out_dir = storage_path(settings.converted_dir, document_id)
    if not (out_dir / "document.md").exists():
        raise HTTPException(
            status_code=404,
            detail="Not converted yet. Run POST /api/files/{document_id}/convert first.",
        )
    return _conv.get_result(document_id)


@router.post("/{document_id}/chunk", response_model=ChunkingResult)
def chunk_document(document_id: str) -> ChunkingResult:
    converted_dir = storage_path(settings.converted_dir, document_id)
    if not (converted_dir / "document.md").exists():
        raise HTTPException(
            status_code=404,
            detail="Converted document not found. Run POST /api/files/{document_id}/convert first.",
        )
    return _chunker.chunk(document_id)


@router.post("/{document_id}/chunk/job", response_model=JobDetail)
def chunk_document_job(document_id: str, background_tasks: BackgroundTasks) -> JobDetail:
    converted_dir = storage_path(settings.converted_dir, document_id)
    if not (converted_dir / "document.md").exists():
        raise HTTPException(
            status_code=404,
            detail="Converted document not found. Run POST /api/files/{document_id}/convert first.",
        )
    job = _jobs.create_job(
        job_type="chunk",
        document_id=document_id,
        request={"operation": "chunk"},
    )
    background_tasks.add_task(run_chunk_job, job.job_id, document_id)
    return job


@router.get("/{document_id}/chunks", response_model=ChunkingResult)
def get_chunks(document_id: str) -> ChunkingResult:
    chunks_dir = storage_path(settings.chunks_dir, document_id)
    if not (chunks_dir / "chunk_manifest.json").exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks not generated yet. Run POST /api/files/{document_id}/chunk first.",
        )
    return _chunker.get_result(document_id)


@router.get("/{document_id}/preview", response_model=DocumentPreview)
def get_document_preview(document_id: str, max_chars: int = 12000) -> DocumentPreview:
    doc_dir = storage_path(settings.raw_uploads_dir, document_id)
    if not (doc_dir / "metadata.json").exists():
        raise HTTPException(status_code=404, detail="Document not found.")
    safe_max = min(max(1, max_chars), 50000)
    md_path = storage_path(settings.converted_dir, document_id, "document.md")
    if not md_path.exists():
        return DocumentPreview(
            document_id=document_id,
            exists=False,
            preview="",
            char_count=0,
            truncated=False,
            source="converted_document_md",
        )
    content = md_path.read_text(encoding="utf-8")
    truncated = len(content) > safe_max
    return DocumentPreview(
        document_id=document_id,
        exists=True,
        preview=content[:safe_max] if truncated else content,
        char_count=len(content),
        truncated=truncated,
        source="converted_document_md",
    )


@router.post("/{document_id}/initialize", response_model=InitializeResult)
def initialize_document(document_id: str) -> InitializeResult:
    doc_dir = storage_path(settings.raw_uploads_dir, document_id)
    if not (doc_dir / "metadata.json").exists():
        raise HTTPException(status_code=404, detail="Document not found.")
    warnings: list = []
    profile_created = False
    pipeline_created = False
    if not (doc_dir / "profile.json").exists():
        try:
            _profiler.profile(document_id)
            profile_created = True
        except Exception as exc:
            warnings.append(f"Profile failed: {exc}")
    if not (doc_dir / "pipeline_decision.json").exists():
        if (doc_dir / "profile.json").exists():
            try:
                _engine.decide(document_id)
                pipeline_created = True
            except Exception as exc:
                warnings.append(f"Pipeline decision failed: {exc}")
        else:
            warnings.append("Skipped pipeline decision: profile not available.")
    with get_session() as session:
        doc = repository.get_document(session, document_id)
        phase = doc.current_phase if doc else "upload"
    return InitializeResult(
        document_id=document_id,
        profile_created=profile_created,
        pipeline_created=pipeline_created,
        current_phase=phase,
        warnings=warnings,
    )


@router.get("/{document_id}/security-report", response_model=SecurityReport)
def get_security_report(document_id: str) -> SecurityReport:
    doc_dir = storage_path(settings.raw_uploads_dir, document_id)
    if not (doc_dir / "metadata.json").exists():
        raise HTTPException(status_code=404, detail="Document not found.")
    return _security.generate(document_id)


@router.get("/{document_id}/integrity", response_model=IntegrityReport)
def get_integrity(document_id: str) -> IntegrityReport:
    doc_dir = storage_path(settings.raw_uploads_dir, document_id)
    if not (doc_dir / "metadata.json").exists():
        raise HTTPException(status_code=404, detail="Document not found.")
    return _integrity.verify_document_outputs(document_id)


@router.get("/{document_id}/ocr-status", response_model=OCRStatusResponse)
def get_ocr_status(document_id: str) -> OCRStatusResponse:
    doc_dir = storage_path(settings.raw_uploads_dir, document_id)
    if not (doc_dir / "metadata.json").exists():
        raise HTTPException(status_code=404, detail="Document not found.")

    requires_ocr = None
    ocr_supported = False
    warnings = []
    profile_path = doc_dir / "profile.json"
    if profile_path.exists():
        profile = DocumentProfile(**_json_module.loads(profile_path.read_text(encoding="utf-8")))
        requires_ocr = profile.requires_ocr
        ocr_supported = profile.ocr_supported
        if profile.ocr_reason:
            warnings.append(profile.ocr_reason)

    availability = LocalOCRService().is_ocr_available()
    if not settings.ocr_enabled:
        warnings.append("OCR is disabled. Set OCR_ENABLED=true to enable local OCR.")
    warnings.extend(availability.warnings)

    return OCRStatusResponse(
        document_id=document_id,
        ocr_enabled=settings.ocr_enabled,
        ocr_available=availability.available,
        requires_ocr=requires_ocr,
        ocr_supported=ocr_supported,
        provider=availability.provider,
        language=settings.ocr_language,
        warnings=warnings,
        error=availability.error,
    )


@router.post("/{document_id}/search", response_model=SearchResponse)
def search_document(document_id: str, request: SearchRequest) -> SearchResponse:
    chunks_dir = storage_path(settings.chunks_dir, document_id)
    if not (chunks_dir / "chunks.jsonl").exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks not found. Run POST /api/files/{document_id}/chunk first.",
        )
    return _search.search(document_id, request)


@router.get("/{document_id}/chunk-quality", response_model=ChunkQualityReport)
def get_chunk_quality(document_id: str) -> ChunkQualityReport:
    return _chunk_quality.evaluate(document_id)


@router.post("/{document_id}/retrieval-evaluation", response_model=RetrievalEvaluationResponse)
def evaluate_retrieval(
    document_id: str,
    request: RetrievalEvaluationRequest,
) -> RetrievalEvaluationResponse:
    return _retrieval_eval.evaluate(document_id, request)


@router.post("/{document_id}/retrieval-evaluation/job", response_model=JobDetail)
def evaluate_retrieval_job(
    document_id: str,
    request: RetrievalEvaluationRequest,
    background_tasks: BackgroundTasks,
) -> JobDetail:
    chunks_dir = storage_path(settings.chunks_dir, document_id)
    if not (chunks_dir / "chunks.jsonl").exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks not found. Run POST /api/files/{document_id}/chunk first.",
        )
    job = _jobs.create_job(
        job_type="retrieval_evaluation",
        document_id=document_id,
        request=request.model_dump(mode="json"),
    )
    background_tasks.add_task(run_retrieval_evaluation_job, job.job_id, document_id, request)
    return job


@router.post("/{document_id}/retrieval-evaluation-set", response_model=RetrievalEvaluationSetResponse)
def evaluate_retrieval_set(
    document_id: str,
    request: RetrievalEvaluationSetRequest,
) -> RetrievalEvaluationSetResponse:
    return _retrieval_eval.evaluate_set(document_id, request)


@router.get("/{document_id}/token-efficiency", response_model=TokenEfficiencySummary)
def get_token_efficiency(document_id: str) -> TokenEfficiencySummary:
    return _token_efficiency.summarize(document_id)


@router.post("/{document_id}/grounded-answer", response_model=GroundedAnswerResponse)
def grounded_answer(
    document_id: str,
    request: GroundedAnswerRequest,
) -> GroundedAnswerResponse:
    chunks_dir = storage_path(settings.chunks_dir, document_id)
    if not (chunks_dir / "chunks.jsonl").exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks not found. Run POST /api/files/{document_id}/chunk first.",
        )
    return _grounded_answer.answer(document_id, request)


@router.post("/{document_id}/grounded-answer/job", response_model=JobDetail)
def grounded_answer_job(
    document_id: str,
    request: GroundedAnswerRequest,
    background_tasks: BackgroundTasks,
) -> JobDetail:
    chunks_dir = storage_path(settings.chunks_dir, document_id)
    if not (chunks_dir / "chunks.jsonl").exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks not found. Run POST /api/files/{document_id}/chunk first.",
        )
    job = _jobs.create_job(
        job_type="grounded_answer",
        document_id=document_id,
        request=request.model_dump(mode="json"),
    )
    background_tasks.add_task(run_grounded_answer_job, job.job_id, document_id, request)
    return job


@router.post("/{document_id}/prepare-llm-payload", response_model=LLMPayloadResponse)
def prepare_llm_payload(document_id: str, request: LLMPayloadRequest) -> LLMPayloadResponse:
    chunks_dir = storage_path(settings.chunks_dir, document_id)
    if not (chunks_dir / "chunks.jsonl").exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks not found. Run POST /api/files/{document_id}/chunk first.",
        )
    return _llm_payload.prepare(document_id, request)


@router.post("/{document_id}/estimate-context", response_model=EstimateContextResponse)
def estimate_context(document_id: str, request: EstimateContextRequest) -> EstimateContextResponse:
    chunks_dir = storage_path(settings.chunks_dir, document_id)
    if not (chunks_dir / "chunks.jsonl").exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks not found. Run POST /api/files/{document_id}/chunk first.",
        )
    return _llm_payload.estimate(document_id, request)


@router.get("/{document_id}/index-status", response_model=DocumentIndexStatusResponse)
def get_index_status(document_id: str) -> DocumentIndexStatusResponse:
    """Return Qdrant + document index status without crashing."""
    qdrant = check_qdrant_status()
    doc_status = check_document_index_status(document_id)
    return DocumentIndexStatusResponse(
        document_id=document_id,
        qdrant_configured=qdrant["qdrant_configured"],
        qdrant_available=qdrant["qdrant_available"],
        collection_name=qdrant["collection_name"],
        indexed=doc_status["indexed"],
        indexed_chunks=doc_status["indexed_chunks"],
        total_chunks=doc_status["total_chunks"],
        embedding_provider=qdrant["embedding_provider"],
        embedding_model=qdrant["embedding_model"],
        vector_size=qdrant["vector_size"],
        indexed_embedding_provider=doc_status["indexed_embedding_provider"],
        indexed_embedding_model=doc_status["indexed_embedding_model"],
        indexed_vector_size=doc_status["indexed_vector_size"],
        error=qdrant["error"],
    )


@router.post("/{document_id}/index", response_model=IndexResponse)
def index_document(document_id: str) -> IndexResponse:
    if not settings.qdrant_url:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Qdrant is not configured. Set QDRANT_URL in your environment.",
                "qdrant_configured": False,
                "qdrant_available": False,
                "embedding_provider": settings.embedding_provider,
            },
        )
    if not (storage_path(settings.chunks_dir, document_id, "chunks.jsonl")).exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks not found. Run POST /api/files/{document_id}/chunk first.",
        )
    try:
        return _vector_index.index(document_id)
    except VectorIndexError as exc:
        raise HTTPException(
            status_code=503,
            detail=_vector_error_detail(str(exc)),
        ) from exc


@router.post("/{document_id}/index/job", response_model=JobDetail)
def index_document_job(document_id: str, background_tasks: BackgroundTasks) -> JobDetail:
    if not (storage_path(settings.chunks_dir, document_id, "chunks.jsonl")).exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks not found. Run POST /api/files/{document_id}/chunk first.",
        )
    job = _jobs.create_job(
        job_type="index",
        document_id=document_id,
        request={"operation": "index"},
    )
    background_tasks.add_task(run_index_job, job.job_id, document_id)
    return job


@router.post("/{document_id}/semantic-search", response_model=SemanticSearchResponse)
def semantic_search_document(
    document_id: str, request: SemanticSearchRequest
) -> SemanticSearchResponse:
    if not settings.qdrant_url:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Qdrant is not configured. Set QDRANT_URL in your environment.",
                "qdrant_configured": False,
                "qdrant_available": False,
                "indexed": False,
                "embedding_provider": settings.embedding_provider,
            },
        )
    if not (storage_path(settings.chunks_dir, document_id, "index_manifest.json")).exists():
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Document not indexed yet. Run POST /api/files/{document_id}/index first.",
                "qdrant_configured": True,
                "indexed": False,
                "embedding_provider": settings.embedding_provider,
            },
        )
    try:
        return _vector_index.semantic_search(document_id, request)
    except VectorIndexError as exc:
        raise HTTPException(
            status_code=503,
            detail=_vector_error_detail(str(exc), indexed=True),
        ) from exc


@router.post("/{document_id}/hybrid-search", response_model=HybridSearchResponse)
def hybrid_search_document(
    document_id: str, request: HybridSearchRequest
) -> HybridSearchResponse:
    if not (storage_path(settings.chunks_dir, document_id, "chunks.jsonl")).exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks not found. Run POST /api/files/{document_id}/chunk first.",
        )
    return _hybrid.search(document_id, request)


@router.get("/{document_id}/export")
def export_artifact(
    document_id: str,
    artifact: str = Query(...),
    download: bool = Query(True),
) -> Response:
    if artifact not in _ALLOWED_ARTIFACTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid artifact. Allowed: {', '.join(sorted(_ALLOWED_ARTIFACTS))}",
        )
    if not (storage_path(settings.raw_uploads_dir, document_id, "metadata.json")).exists():
        raise HTTPException(status_code=404, detail="Document not found.")
    with get_session() as session:
        doc = repository.get_document(session, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        original_filename = doc.original_filename

    stem = _safe_stem(original_filename)
    disp = "attachment" if download else "inline"

    if artifact == "integrity":
        report = _integrity.verify_document_outputs(document_id)
        content = _json_module.dumps(report.model_dump(), indent=2, default=str).encode("utf-8")
        safe_filename = f"{stem}_integrity.json"
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'{disp}; filename="{safe_filename}"'},
        )

    _, _, media_type, ext = _ARTIFACT_CONFIG[artifact]
    path = _artifact_file_path(document_id, artifact)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Artifact '{artifact}' not found. Run the relevant pipeline step first.",
        )

    safe_filename = f"{stem}_{artifact}{ext}"
    return FileResponse(
        path=str(path),
        filename=safe_filename,
        media_type=media_type,
        content_disposition_type=disp,
    )
