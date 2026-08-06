from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Registered here (not in tenant_context.py itself) so importing app.core.database
# is enough to activate isolation - avoids relying on import order elsewhere.
from app.core.tenant_context import register_tenant_isolation  # noqa: E402

register_tenant_isolation()
