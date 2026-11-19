import json
from typing import Any, Dict, Optional

from fastapi import APIRouter

from db import repository
from db.session import get_session
from models.db_response_models import AuditEventItem, AuditRecentResponse

router = APIRouter(prefix="/api/audit")


@router.get("/recent", response_model=AuditRecentResponse)
def recent_audit_events(
    limit: int = 50,
    document_id: Optional[str] = None,
    project_id: Optional[str] = None,
    event_type: Optional[str] = None,
    payload_id: Optional[str] = None,
) -> AuditRecentResponse:
    with get_session() as session:
        events = repository.list_recent_audit_events(
            session,
            limit=min(limit, 200),
            document_id=document_id,
            project_id=project_id,
            event_type=event_type,
            payload_id=payload_id,
        )
        items = [_to_audit_item(e) for e in events]
    return AuditRecentResponse(total=len(items), events=items)


def _to_audit_item(e: Any) -> AuditEventItem:
    return AuditEventItem(
        id=e.id,
        event_type=e.event_type,
        document_id=e.document_id,
        project_id=e.project_id,
        payload_id=e.payload_id,
        metadata=_parse_json(e.metadata_json),
        created_at=e.created_at,
    )


def _parse_json(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}
