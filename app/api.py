from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlmodel import select
from app.db import get_session
from app.models import Video, Room
from app.schemas import VideoRead, RoomRead, RoomCreate
from app.s3 import upload_video_file, make_video_url 

router = APIRouter(prefix="/api")


@router.post("/videos", response_model=VideoRead)
async def upload_video(file: UploadFile = File(...)):
    try:
        s3_key = upload_video_file(file.file, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 upload error: {e}")

    with get_session() as session:
        v = Video(filename=file.filename, s3_key=s3_key)
        session.add(v)
        session.commit()
        session.refresh(v)
        
    return VideoRead(
        id=v.id,
        filename=v.filename,
        s3_key=v.s3_key,
        url=make_video_url(v.s3_key),
    )


@router.get("/videos", response_model=list[VideoRead])
def list_videos():
    with get_session() as session:
        videos = session.exec(select(Video)).all()
    return [
        VideoRead(
            id=v.id,
            filename=v.filename,
            s3_key=v.s3_key,
            url=make_video_url(v.s3_key),
        )
        for v in videos
    ]


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
