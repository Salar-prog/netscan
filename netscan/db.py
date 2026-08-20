from sqlmodel import SQLModel, Session, create_engine
from netscan.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
)


def init_db() -> None:
    """Initialize database tables."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency for database session."""
    with Session(engine) as session:
        yield session
