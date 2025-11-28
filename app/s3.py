import os
import uuid
import boto3
from botocore.client import Config

S3_ENDPOINT_URL = os.environ.get("S3_PUBLIC_ENDPOINT", "http://localhost:9000")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "kino-videos")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "minioadmin123")

s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)


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
    return s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": S3_BUCKET_NAME, "Key": key},
        ExpiresIn=3600,
    )
