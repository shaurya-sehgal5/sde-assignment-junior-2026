from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def check_database():
    from sqlalchemy import text

    with engine.connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one()