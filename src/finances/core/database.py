from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "finance.db"


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(connection: object, _: object) -> None:
    assert hasattr(connection, "execute")
    connection.execute("PRAGMA foreign_keys = ON")  # type: ignore[union-attr]
    connection.execute("PRAGMA journal_mode = WAL")  # type: ignore[union-attr]
    connection.execute("PRAGMA synchronous = NORMAL")  # type: ignore[union-attr]


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
