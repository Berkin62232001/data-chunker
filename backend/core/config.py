from pathlib import Path
from typing import Dict, List, Optional

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", populate_by_name=True)

    app_name: str = "LLM File Analyzer"
    app_version: str = "0.1.0"
    debug: bool = False

    # CORS — env override is JSON, e.g. CORS_ORIGINS='["http://localhost:3000"]'
    cors_origins: List[str] = ["http://localhost:3000"]

    # Storage paths
    storage_root: Path = Path("storage")
    raw_uploads_dir: Path = Path("storage/raw")
    converted_dir: Path = Path("storage/converted")
    chunks_dir: Path = Path("storage/chunks")
    llm_payloads_dir: Path = Path("storage/llm_payloads")
    projects_dir: Path = Path("storage/projects")

    # Upload limits
    max_upload_size_mb: int = 100
    allowed_extensions: List[str] = [
        ".pdf", ".docx", ".pptx", ".xlsx", ".csv",
        ".txt", ".md", ".html", ".png", ".jpg", ".jpeg", ".webp",
    ]

    # LLM provider API keys (set via environment variables — never hardcode)
    anthropic_api_key: Optional[str] = None   # ANTHROPIC_API_KEY
    openai_api_key: Optional[str] = None       # OPENAI_API_KEY
    gemini_api_key: Optional[str] = None       # GEMINI_API_KEY

    # Claude model — override via CLAUDE_MODEL env var if needed
    claude_model: str = "claude-sonnet-4-6"

    # Qdrant vector database (all optional — keyword search works without it)
    qdrant_url: Optional[str] = None             # QDRANT_URL
    qdrant_api_key: Optional[str] = None         # QDRANT_API_KEY
    qdrant_collection: str = Field(
        default="llm_file_chunks",
        validation_alias=AliasChoices("QDRANT_COLLECTION_NAME", "QDRANT_COLLECTION"),
    )

    # Embeddings (deterministic demo is the default for local/dev/test use)
    embedding_provider: str = "deterministic_demo"  # EMBEDDING_PROVIDER
    lm_studio_base_url: str = "http://localhost:1234/v1"  # LM_STUDIO_BASE_URL
    lm_studio_embedding_model: str = "nomic-embed-text"  # LM_STUDIO_EMBEDDING_MODEL
    lm_studio_api_key: str = "lm-studio"  # LM_STUDIO_API_KEY
    lm_studio_timeout_seconds: int = 30  # LM_STUDIO_TIMEOUT_SECONDS
    lm_studio_batch_size: int = 16  # LM_STUDIO_BATCH_SIZE
    local_embedding_hosts: List[str] = ["localhost", "127.0.0.1", "::1", "host.docker.internal"]

    # OCR (optional local-only scanned document support)
    ocr_enabled: bool = False  # OCR_ENABLED
    ocr_provider: str = "ocrmypdf"  # OCR_PROVIDER
    ocr_language: str = "eng"  # OCR_LANGUAGE
    ocr_timeout_seconds: int = 120  # OCR_TIMEOUT_SECONDS
    ocr_max_pages: int = 50  # OCR_MAX_PAGES
    ocr_dpi: int = 300  # OCR_DPI
    ocr_output_mode: str = "text"  # OCR_OUTPUT_MODE
    ocr_fail_open: bool = True  # OCR_FAIL_OPEN

    # Token budget manager
    default_context_token_budget: int = 8000
    max_chunks_per_request: int = 20
    provider_context_limits: Dict[str, int] = Field(
        default={"claude": 180000, "openai": 128000, "gemini": 1000000, "generic": 32000}
    )

    # Keyword retrieval
    keyword_bm25_k1: float = Field(default=1.2, gt=0, allow_inf_nan=False)
    keyword_bm25_b: float = Field(default=0.75, ge=0, le=1, allow_inf_nan=False)
    keyword_section_weight: float = Field(default=3.0, ge=0, allow_inf_nan=False)

    # Security
    api_access_key: Optional[SecretStr] = Field(default=None, min_length=32)
    max_request_size_mb: int = Field(default=102, ge=1)
    request_spool_bytes: int = Field(default=1024 * 1024, ge=1)
    requests_per_minute: int = Field(default=300, ge=1)
    local_only_mode: bool = True          # LOCAL_ONLY_MODE — blocks external LLM calls
    allowed_mime_categories: List[str] = Field(
        default=["text/", "application/pdf", "application/vnd.", "application/msword", "image/"]
    )

    # Audit log
    audit_log_enabled: bool = True
    audit_log_dir: Path = Path("storage/audit")

    # Database
    database_url: str = "sqlite:///storage/app.db"


settings = Settings()
