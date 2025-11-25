from typing import Optional
from pydantic import BaseModel


class RoomCreate(BaseModel):
    code: str


class RoomRead(RoomCreate):
    id: int


class VideoCreate(BaseModel):
    filename: str


class VideoRead(VideoCreate):
    id: int
