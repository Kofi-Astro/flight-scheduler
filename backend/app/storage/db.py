"""Database engine and session management.

We use SQLAlchemy 2.0 (the modern ``DeclarativeBase`` style).

Why SQLAlchemy and not "just SQLite"?
  * The spec wants this to grow into a multi-agent agency tool. When that day
    comes you flip ``DATABASE_URL`` to a Railway Postgres URL and everything
    keeps working — no query rewrites.
  * It gives us migrations-friendly models and typed columns.

For the side-business phase the default is a single local SQLite file, which is
zero-setup and perfectly fine for one operator.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Declarative base all ORM tables inherit from."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# ``connect_args`` note: SQLite by default forbids using a connection across
# threads. FastAPI/uvicorn use a threadpool for sync code, so we disable that
# check. It is safe here because SQLAlchemy's session is still per-request.
_is_sqlite = settings.database_url.startswith("sqlite")

if _is_sqlite:
    # Make sure the folder for the SQLite file exists (e.g. app/data/).
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # Reasonable pool defaults for a small app; Postgres benefits from these.
    pool_pre_ping=True,
    echo=False,  # set True to log every SQL statement while debugging
)

# ``sessionmaker`` produces Session objects. ``expire_on_commit=False`` lets us
# keep reading model attributes after commit (handy in service functions).
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def init_db() -> None:
    """Create tables that don't exist yet.

    Called once on startup (see ``app/main.py``). For real schema *migrations*
    later, introduce Alembic — but create_all is right for now and never drops
    or alters existing tables.
    """
    # Importing here (not at module top) avoids a circular import:
    # tables.py imports Base from this module.
    from app.storage import tables  # noqa: F401  (registers the models)

    Base.metadata.create_all(bind=engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a request-scoped session and closes it.

    Usage in a router:

        @router.get(...)
        def handler(db: Session = Depends(get_session)):
            ...
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
