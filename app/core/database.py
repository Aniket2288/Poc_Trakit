from collections.abc import Iterator

import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.request_context import count_query

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

sql_logger = logging.getLogger("trackit.sql")


@event.listens_for(engine, "before_cursor_execute")
def _on_query(conn, cursor, statement, parameters, context, executemany):
    """Runs before EVERY SQL statement: count it for the access log, and log it if LOG_SQL is on."""
    count_query()
    if settings.log_sql:
        sql_logger.info("sql", extra={"sql": " ".join(statement.split())[:300]})


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# we can make open sessions req to db and close after each req