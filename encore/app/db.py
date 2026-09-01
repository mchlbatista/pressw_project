import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

engine = create_engine(
    os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://showcall:showcall@db:5432/showcall"
    ),
    pool_pre_ping=True,
)


def session() -> Session:
    return Session(engine)
