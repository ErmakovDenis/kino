from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime


class Video(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class Room(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str
    video_id: Optional[int] = None
