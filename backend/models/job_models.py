from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


JobStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]


class JobDetail(BaseModel):
    job_id: str
    document_id: Optional[str]
    job_type: str
    status: JobStatus
    progress_percent: int
    current_step: Optional[str] = None
    message: Optional[str] = None
    request: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    retry_of_job_id: Optional[str] = None
    can_retry: bool = False
    can_cancel: bool = False


class JobListResponse(BaseModel):
    jobs: List[JobDetail] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
    sort: Literal["newest", "oldest"] = "newest"


class CleanupJobsRequest(BaseModel):
    older_than_days: int = 30
    statuses: List[JobStatus] = Field(default_factory=lambda: ["succeeded", "failed", "canceled"])

    @field_validator("older_than_days")
    @classmethod
    def older_than_days_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("older_than_days must be >= 0")
        return value

    @field_validator("statuses")
    @classmethod
    def statuses_not_empty(cls, value: List[JobStatus]) -> List[JobStatus]:
        if not value:
            raise ValueError("statuses must not be empty")
        return value


class CleanupJobsResponse(BaseModel):
    deleted_count: int
