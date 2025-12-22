from typing import Optional

from sqlmodel import SQLModel, create_engine, Session

from os import environ


DATABASE_URL = environ.get("DATABASE_URL", "sqlite:///./data/dev.db")


def get_engine():
    
    echo = False
    engine = create_engine(DATABASE_URL, echo=echo)
    return engine


def create_db_and_tables():
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    # Ensure new columns (added by model changes) exist in existing DBs.
    # This is a lightweight, idempotent migration step to add `hls_master` when
    # the table was created before the model change.
    try:
        from sqlalchemy import inspect, text

        insp = inspect(engine)
        cols = [c['name'] for c in insp.get_columns('video')]
        if 'hls_master' not in cols:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE video ADD COLUMN hls_master VARCHAR NULL'))
        if 'status' not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE video ADD COLUMN status VARCHAR NULL DEFAULT 'uploaded'"))
    except Exception:
        # best-effort migration: ignore if DB doesn't support or fails
        pass


def get_session() -> Session:
    engine = get_engine()
    return Session(engine)


# Ensure DB exists and migrations applied during import (helps tests and startup scenarios)
try:
    create_db_and_tables()
except Exception:
    pass
