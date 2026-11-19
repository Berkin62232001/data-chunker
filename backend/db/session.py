from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Optional[Engine] = None
_SessionFactory = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        from core.config import settings
        kwargs: dict = {}
        if str(settings.database_url).startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(str(settings.database_url), **kwargs)
    return _engine


def reset_engine() -> None:
    """Force recreation of the engine on next use. Must be called when database_url changes."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


@contextmanager
def get_session() -> Generator[Session, None, None]:
    engine = _get_engine()
    factory = sessionmaker(bind=engine, autoflush=True, autocommit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
