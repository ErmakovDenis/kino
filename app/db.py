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


def get_session() -> Session:
    engine = get_engine()
    return Session(engine)
