from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from models.evaluation_models import RetrievalEvaluationRequest
from models.grounded_answer_models import GroundedAnswerRequest
from models.job_models import CleanupJobsRequest, CleanupJobsResponse, JobDetail, JobListResponse
from services.document_job_service import (
    run_chunk_job,
    run_convert_job,
    run_grounded_answer_job,
    run_index_job,
    run_retrieval_evaluation_job,
)
from services.job_service import (
    JobNotFoundError,
    JobRetryNotAllowedError,
    JobRetryUnavailableError,
    JobService,
)

router = APIRouter(prefix="/api/jobs")
_jobs = JobService()


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: str) -> JobDetail:
    try:
        return _jobs.get_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found.")


@router.get("", response_model=JobListResponse)
def list_jobs(
    document_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    sort: str = Query("newest"),
) -> JobListResponse:
    jobs = _jobs.list_jobs(
        document_id=document_id,
        status=status,
        job_type=job_type,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    total = _jobs.count_jobs(document_id=document_id, status=status, job_type=job_type)
    return JobListResponse(
        jobs=jobs,
        total=total,
        limit=min(max(1, limit), 200),
        offset=max(0, offset),
        sort="oldest" if sort == "oldest" else "newest",
    )


@router.post("/{job_id}/cancel", response_model=JobDetail)
def cancel_job(job_id: str) -> JobDetail:
    try:
        return _jobs.cancel_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found.")


@router.post("/{job_id}/retry", response_model=JobDetail)
def retry_job(job_id: str, background_tasks: BackgroundTasks) -> JobDetail:
    try:
        job = _jobs.retry_job(job_id)
        _schedule_retry(background_tasks, job)
        return job
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found.")
    except JobRetryNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except JobRetryUnavailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/cleanup", response_model=CleanupJobsResponse)
def cleanup_jobs(request: CleanupJobsRequest) -> CleanupJobsResponse:
    deleted = _jobs.cleanup_jobs(request)
    return CleanupJobsResponse(deleted_count=deleted)


def _schedule_retry(background_tasks: BackgroundTasks, job: JobDetail) -> None:
    if not job.document_id:
        raise HTTPException(status_code=422, detail="Job has no document_id and cannot be retried.")

    if job.job_type == "convert":
        background_tasks.add_task(run_convert_job, job.job_id, job.document_id)
        return
    if job.job_type == "chunk":
        background_tasks.add_task(run_chunk_job, job.job_id, job.document_id)
        return
    if job.job_type == "index":
        background_tasks.add_task(run_index_job, job.job_id, job.document_id)
        return
    if job.job_type == "retrieval_evaluation":
        try:
            request = RetrievalEvaluationRequest(**(job.request or {}))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Retry request is invalid: {exc}")
        background_tasks.add_task(run_retrieval_evaluation_job, job.job_id, job.document_id, request)
        return
    if job.job_type == "grounded_answer":
        try:
            request = GroundedAnswerRequest(**(job.request or {}))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Retry request is invalid: {exc}")
        background_tasks.add_task(run_grounded_answer_job, job.job_id, job.document_id, request)
        return
    raise HTTPException(status_code=422, detail=f"Job type '{job.job_type}' cannot be retried.")
