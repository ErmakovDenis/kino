import os
import uuid
import boto3
from botocore.client import Config
import httpx
from pathlib import Path

S3_INTERNAL_ENDPOINT = os.environ.get("S3_ENDPOINT_URL", "http://minio:9000")
S3_PUBLIC_ENDPOINT = os.environ.get("S3_PUBLIC_ENDPOINT", S3_INTERNAL_ENDPOINT)
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "kino-videos")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "minioadmin123")

s3 = boto3.client(
    "s3",
    endpoint_url=S3_INTERNAL_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)

# ensure bucket exists (idempotent)
try:
    existing = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    if S3_BUCKET_NAME not in existing:
        s3.create_bucket(Bucket=S3_BUCKET_NAME)
except Exception:
    # don't crash app import if minio is unreachable during local runs/tests
    pass


def upload_video_file(file_obj, original_filename: str) -> str:
    ext = original_filename.rsplit(".", 1)[-1] if "." in original_filename else "bin"
    key = f"videos/{uuid.uuid4().hex}.{ext}"

    s3.upload_fileobj(
        Fileobj=file_obj,
        Bucket=S3_BUCKET_NAME,
        Key=key,
        ExtraArgs={"ContentType": f"video/{ext}"},
    )
    return key


def make_video_url(key: str) -> str:
    try:
        # Use a client configured with the public endpoint to generate a presigned URL
        public_client = boto3.client(
            "s3",
            endpoint_url=S3_PUBLIC_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        return public_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": S3_BUCKET_NAME, "Key": key},
            ExpiresIn=3600,
        )
    except Exception:
        return f"{S3_PUBLIC_ENDPOINT}/{S3_BUCKET_NAME}/{key}"


# list of remote sample videos to preload to the bucket (idempotent)
SAMPLE_VIDEOS = [
    {
        "name": "flower.mp4",
        "url": "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
    },
    {
        "name": "bunny_240.mp4",
        "url": "https://sample-videos.com/video123/mp4/240/big_buck_bunny_240p_1mb.mp4",
    },
]


def ensure_sample_videos():
    """Ensure sample videos exist in the S3 bucket. This is idempotent and
    will not overwrite existing objects.
    """
    if not S3_BUCKET_NAME:
        return
    for entry in SAMPLE_VIDEOS:
        key = f"videos/{entry['name']}"
        try:
            s3.head_object(Bucket=S3_BUCKET_NAME, Key=key)
            # object exists in S3, ensure DB record exists too
            try:
                from app.db import get_session
                from app.models import Video
                from sqlmodel import select

                with get_session() as session:
                    vid = session.exec(select(Video).where(Video.s3_key == key)).first()
                    if not vid:
                        v = Video(filename=entry["name"], s3_key=key)
                        session.add(v)
                        session.commit()
            except Exception:
                pass
            continue
        except Exception:
            # object missing — download and upload
            try:
                resp = httpx.get(entry["url"], timeout=30.0)
                if resp.status_code == 200:
                    bio = resp.content
                    s3.put_object(Bucket=S3_BUCKET_NAME, Key=key, Body=bio, ContentType="video/mp4")
                    from app.db import get_session
                    from app.models import Video
                    from sqlmodel import select

                    try:
                        with get_session() as session:
                            vid = session.exec(select(Video).where(Video.s3_key == key)).first()
                            if not vid:
                                v = Video(filename=entry["name"], s3_key=key)
                                session.add(v)
                                session.commit()
                                # enqueue transcode job for this video (best effort)
                                try:
                                    from app.tasks import transcode_video

                                    transcode_video.send(key, v.id)
                                except Exception:
                                    pass
                    except Exception:
                        # best-effort: ignore DB errors during preload
                        pass
            except Exception:
                continue

