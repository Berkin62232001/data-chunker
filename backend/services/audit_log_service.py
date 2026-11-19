import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

from core.config import settings

_lock = threading.Lock()

# Fields that must never appear in audit log values (path separators, secrets)
_BLOCKED_PREFIXES = ("/", "\\", "storage/", "./")


def _sanitize(value: Any) -> Any:
    """Strip anything that looks like a file-system path or secret."""
    if isinstance(value, str):
        for prefix in _BLOCKED_PREFIXES:
            if value.startswith(prefix):
                return "[redacted-path]"
    return value


def _safe_dict(**kwargs: Any) -> Dict[str, Any]:
    return {k: _sanitize(v) for k, v in kwargs.items()}


def append(event: str, document_id: str, **kwargs: Any) -> None:
    """Append a single audit event to both JSONL file and DB."""
    if not settings.audit_log_enabled:
        return
    safe = _safe_dict(**kwargs)
    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "document_id": document_id,
        **safe,
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    settings.audit_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.audit_log_dir / "audit.jsonl"
    with _lock:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line)

    # Mirror to DB (non-blocking — import here to avoid circular imports)
    try:
        from db import repository
        from db.session import get_session
        with get_session() as session:
            repository.create_audit_event(
                session,
                event_type=event,
                document_id=document_id,
                metadata=safe,
            )
    except Exception:
        pass  # JSONL is the authoritative log; DB write is supplementary


def read_for_document(document_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Return the most recent audit entries for a given document_id."""
    log_path = settings.audit_log_dir / "audit.jsonl"
    if not log_path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    try:
        with open(log_path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    try:
                        obj = json.loads(line)
                        if obj.get("document_id") == document_id:
                            entries.append(obj)
                    except Exception:
                        pass
    except OSError:
        return []
    return entries[-limit:]
