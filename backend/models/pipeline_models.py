from typing import List

from pydantic import BaseModel, field_validator

_VALID_OUTPUT_FORMATS = {"markdown_jsonl", "structured_json_summary"}


class PipelineDecision(BaseModel):
    document_id: str
    selected_pipeline: str
    output_format: str           # "markdown_jsonl" | "structured_json_summary"
    output_artifacts: List[str]  # files the conversion stage will produce
    llm_send_format_claude: str
    llm_send_format_openai_gemini: str
    reasons: List[str]
    warnings: List[str]
    decided_at: str

    @field_validator("output_format")
    @classmethod
    def output_format_must_be_known(cls, v: str) -> str:
        if v not in _VALID_OUTPUT_FORMATS:
            raise ValueError(f"output_format must be one of {_VALID_OUTPUT_FORMATS}, got {v!r}")
        return v
