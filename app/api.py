from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlmodel import select
from app.db import get_session
from app.models import Video, Room
from app.schemas import VideoRead, RoomRead, RoomCreate
from app.s3 import upload_video_file, make_video_url 
from app.s3 import s3, S3_BUCKET_NAME
from pathlib import Path

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

    # enqueue transcode / HLS creation job
    try:
        from app.tasks import transcode_video
        transcode_video.send(s3_key, v.id)
    except Exception:
        # don't fail upload if the worker is not available
        pass

    return VideoRead(
        id=v.id,
        filename=v.filename,
        s3_key=v.s3_key,
        url=make_video_url(v.s3_key),
        hls_master=v.hls_master,
        status=v.status,
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
            hls_master=v.hls_master,
            status=v.status,
        )
        for v in videos
    ]


@router.get("/videos/{video_id}", response_model=VideoRead)
def get_video(video_id: int):
    with get_session() as session:
        v = session.get(Video, video_id)
        if not v:
            raise HTTPException(status_code=404, detail="Video not found")
    return VideoRead(
        id=v.id,
        filename=v.filename,
        s3_key=v.s3_key,
        url=make_video_url(v.s3_key),
        hls_master=v.hls_master,
        status=v.status,
    )


@router.delete("/videos/{video_id}")
def delete_video(video_id: int):
    with get_session() as session:
        v = session.get(Video, video_id)
        if not v:
            raise HTTPException(status_code=404, detail="Video not found")

        # delete original object
        try:
            s3.delete_object(Bucket=S3_BUCKET_NAME, Key=v.s3_key)
        except Exception:
            # best-effort: continue even if S3 fails
            pass

        # delete all HLS objects under prefix
        try:
            prefix = f"hls/{Path(v.s3_key).stem}/"
            resp = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=prefix)
            keys = [obj["Key"] for obj in resp.get("Contents", [])]
            if keys:
                # batch delete
                s3.delete_objects(Bucket=S3_BUCKET_NAME, Delete={"Objects": [{"Key": k} for k in keys]})
        except Exception:
            pass

        session.delete(v)
        session.commit()

    return {"ok": True}


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
