from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlmodel import select
from app.db import get_session
from app.models import Video, Room
from app.schemas import VideoRead, VideoCreate, RoomCreate, RoomRead
from pathlib import Path
from app.tasks import split_video

router = APIRouter(prefix="/api")

STORAGE = Path("./storage/videos")
STORAGE.mkdir(parents=True, exist_ok=True)


@router.post("/videos", response_model=VideoRead)
async def upload_video(file: UploadFile = File(...)):
    target = STORAGE / file.filename
    content = await file.read()
    target.write_bytes(content)
    try:
        split_video.send(str(target), str(STORAGE / "chunks"), segment_seconds=10)
    except Exception:
        pass
    with get_session() as session:
        v = Video(filename=file.filename)
        session.add(v)
        session.commit()
        session.refresh(v)
    return VideoRead(id=v.id, filename=v.filename)


@router.get("/videos", response_model=list[VideoRead])
def list_videos():
    with get_session() as session:
        videos = session.exec(select(Video)).all()
    return [VideoRead(id=v.id, filename=v.filename) for v in videos]


@router.post("/rooms", response_model=RoomRead)
def create_room(in_data: RoomCreate):
    with get_session() as session:
        r = Room(code=in_data.code)
        session.add(r)
        session.commit()
        session.refresh(r)
    return RoomRead(id=r.id, code=r.code)


@router.get("/rooms", response_model=list[RoomRead])
def list_rooms():
    with get_session() as session:
        rooms = session.exec(select(Room)).all()
    return [RoomRead(id=r.id, code=r.code) for r in rooms]
