from typing import Optional
from pydantic import BaseModel


class RoomCreate(BaseModel):
    code: str


class RoomRead(RoomCreate):
    id: int


class VideoCreate(BaseModel):
    filename: str
    s3_key: str


class VideoRead(BaseModel):
    id: int
    filename: str
    s3_key: str
    url: str
    hls_master: Optional[str] = None
    status: Optional[str] = None