from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine
from netscan.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
)


def init_db() -> None:
    """Initialize database tables and configure SQLite for production use."""
    SQLModel.metadata.create_all(engine)

    if settings.DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA busy_timeout=5000"))
            conn.commit()


def get_session():
    """FastAPI dependency for database session."""
    with Session(engine) as session:
        yield session
