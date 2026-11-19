from typing import List

from pydantic import BaseModel, field_validator


class IntegrityCheck(BaseModel):
    name: str
    status: str   # "pass" | "warn" | "fail" | "skip"
    message: str

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in {"pass", "warn", "fail", "skip"}:
            raise ValueError(f"Invalid check status: {v!r}")
        return v


class IntegrityReport(BaseModel):
    document_id: str
    status: str   # "pass" | "warn" | "fail"
    checks: List[IntegrityCheck]
    warnings: List[str]
    errors: List[str]

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in {"pass", "warn", "fail"}:
            raise ValueError(f"Invalid report status: {v!r}")
        return v
