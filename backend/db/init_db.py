from db.models import Base
from db.session import _get_engine


def init_db() -> None:
    """Create all tables. Safe to call multiple times (CREATE TABLE IF NOT EXISTS)."""
    engine = _get_engine()
    Base.metadata.create_all(bind=engine)
