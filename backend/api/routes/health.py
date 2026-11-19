from fastapi import APIRouter
from core.config import settings

router = APIRouter()


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "local_only_mode": settings.local_only_mode,
    }
