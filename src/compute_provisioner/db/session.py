from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from compute_provisioner.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout_seconds,
    pool_pre_ping=True,
)

SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_db_session():
    with SessionFactory() as session:
        yield session
