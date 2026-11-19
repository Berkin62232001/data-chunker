from typing import Callable

from models.evaluation_models import RetrievalEvaluationRequest
from models.grounded_answer_models import GroundedAnswerRequest
from services.chunking_service import ChunkingService
from services.conversion_service import ConversionService
from services.grounded_answer_service import GroundedAnswerService
from services.job_service import JobService
from services.retrieval_evaluation_service import RetrievalEvaluationService
from services.vector_index_service import VectorIndexService

_jobs = JobService()


def _run_with_failure(job_id: str, step: str, work: Callable[[], object]) -> None:
    try:
        work()
    except Exception as exc:
        _jobs.fail_job(job_id, error=exc, step=step)


def _canceled(job_id: str) -> bool:
    return _jobs.is_canceled(job_id)


def run_convert_job(job_id: str, document_id: str) -> None:
    def work() -> None:
        if _canceled(job_id):
            return
        _jobs.start_job(job_id, step="loading_document", message="Loading document")
        _jobs.update_progress(job_id, progress_percent=10, step="loading_document")
        if _canceled(job_id):
            return
        _jobs.update_progress(job_id, progress_percent=30, step="conversion_setup", message="Preparing conversion")
        if _canceled(job_id):
            return
        _jobs.update_progress(job_id, progress_percent=60, step="converting", message="Converting document")
        result = ConversionService().convert(document_id)
        if _canceled(job_id):
            return
        _jobs.update_progress(job_id, progress_percent=85, step="writing_artifacts", message="Writing conversion artifacts")
        _jobs.succeed_job(job_id, result=result, message="Conversion complete")

    _run_with_failure(job_id, "converting", work)


def run_chunk_job(job_id: str, document_id: str) -> None:
    def work() -> None:
        if _canceled(job_id):
            return
        _jobs.start_job(job_id, step="loading_converted_text", message="Loading converted text")
        _jobs.update_progress(job_id, progress_percent=20, step="loading_converted_text")
        if _canceled(job_id):
            return
        _jobs.update_progress(job_id, progress_percent=50, step="generating_chunks", message="Generating chunks")
        result = ChunkingService().chunk(document_id)
        if _canceled(job_id):
            return
        _jobs.update_progress(job_id, progress_percent=80, step="writing_chunks", message="Writing chunk artifacts")
        _jobs.succeed_job(job_id, result=result, message="Chunking complete")

    _run_with_failure(job_id, "generating_chunks", work)


def run_index_job(job_id: str, document_id: str) -> None:
    def work() -> None:
        if _canceled(job_id):
            return
        _jobs.start_job(job_id, step="loading_chunks", message="Loading chunks")
        _jobs.update_progress(job_id, progress_percent=20, step="loading_chunks")
        if _canceled(job_id):
            return
        _jobs.update_progress(job_id, progress_percent=40, step="embedding_chunks", message="Embedding chunks")
        if _canceled(job_id):
            return
        _jobs.update_progress(job_id, progress_percent=70, step="upserting_qdrant", message="Upserting vectors to Qdrant")
        result = VectorIndexService().index(document_id)
        if _canceled(job_id):
            return
        _jobs.succeed_job(job_id, result=result, message="Indexing complete")

    _run_with_failure(job_id, "indexing", work)


def run_retrieval_evaluation_job(
    job_id: str,
    document_id: str,
    request: RetrievalEvaluationRequest,
) -> None:
    def work() -> None:
        if _canceled(job_id):
            return
        _jobs.start_job(job_id, step="running_retrieval", message="Running retrieval")
        _jobs.update_progress(job_id, progress_percent=30, step="running_retrieval")
        result = RetrievalEvaluationService().evaluate(document_id, request)
        if _canceled(job_id):
            return
        _jobs.update_progress(job_id, progress_percent=60, step="computing_metrics", message="Computing evaluation metrics")
        _jobs.succeed_job(job_id, result=result, message="Retrieval evaluation complete")

    _run_with_failure(job_id, "retrieval_evaluation", work)


def run_grounded_answer_job(
    job_id: str,
    document_id: str,
    request: GroundedAnswerRequest,
) -> None:
    def work() -> None:
        if _canceled(job_id):
            return
        _jobs.start_job(job_id, step="retrieving_chunks", message="Retrieving chunks")
        _jobs.update_progress(job_id, progress_percent=20, step="retrieving_chunks")
        if _canceled(job_id):
            return
        _jobs.update_progress(job_id, progress_percent=45, step="building_context", message="Building grounded context")
        if _canceled(job_id):
            return
        _jobs.update_progress(job_id, progress_percent=70, step="calling_provider", message="Calling provider")
        result = GroundedAnswerService().answer(document_id, request)
        if _canceled(job_id):
            return
        _jobs.update_progress(job_id, progress_percent=90, step="formatting_citations", message="Formatting citations")
        _jobs.succeed_job(job_id, result=result, message="Grounded answer complete")

    _run_with_failure(job_id, "grounded_answer", work)
