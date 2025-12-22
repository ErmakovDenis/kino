import os
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from pathlib import Path
import shutil
import subprocess
import tempfile
import logging
from typing import Optional
from app.s3 import s3, S3_BUCKET_NAME, make_video_url
import json
import redis as redis_lib
from app.db import get_session
from app.models import Video

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

 
try:
    import redis as redis_lib

    try:
        redis_client = redis_lib.Redis.from_url(REDIS_URL)
    except AttributeError:
        redis_client = redis_lib.from_url(REDIS_URL)
except Exception:
    redis_client = None

redis_broker = RedisBroker(client=redis_client)
dramatiq.set_broker(redis_broker)


@dramatiq.actor
def split_video(video_path: str, output_dir: str, segment_seconds: int = 10):
    """Split a video into small segments.

    This is a simple placeholder: in production you'd run `ffmpeg` and store
    the chunks. For the MVP we create placeholder files to simulate segments.
    """
    p = Path(output_dir)
    p.mkdir(parents=True, exist_ok=True)
    
    for i in range(0, 3):
        chunk = p / f"chunk_{i}.txt"
        chunk.write_text(f"Simulated segment {i} from {video_path}\n")


def _perform_transcode(s3_key: str, video_id: Optional[int] = None, simulate: bool = False):
    """Transcode an S3 video into multiple resolutions and produce HLS playlists.

    This task will download the object from S3, run ffmpeg to generate HLS
    segments for a set of target resolutions, upload the results back to S3
    under a dedicated prefix and update the Video record with the master playlist url.
    If ffmpeg is not available or `simulate=True`, this creates simulated segments.
    """
    log = logging.getLogger("transcode")

    if not s3:
        log.error("No s3 client available, aborting transcode")
        return

    tmpdir = Path(tempfile.mkdtemp(prefix="transcode_"))
    try:
        local_input = tmpdir / "input.mp4"

        # mark processing in DB and publish update as early as possible
        try:
            if video_id:
                with get_session() as session:
                    v = session.get(Video, video_id)
                    if v:
                        v.status = "processing"
                        session.add(v)
                        session.commit()
                        try:
                            # publish a notification so UI can react immediately
                            rclient = redis_lib.Redis.from_url(REDIS_URL)
                            message = {"from": "server", "payload": json.dumps({"type": "video_status", "id": video_id, "status": "processing"})}
                            rclient.publish("room:updates", json.dumps(message))
                        except Exception:
                            log.exception("Failed to publish processing status for video %s", video_id)
        except Exception:
            log.exception("Failed to set processing status for id=%s", video_id)

        # download from S3
        try:
            obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
            data = obj["Body"].read()
            local_input.write_bytes(data)
        except Exception as e:
            log.exception("Failed to download from S3: %s", e)
            # mark failed and publish to UI
            if video_id:
                try:
                    with get_session() as session:
                        v = session.get(Video, video_id)
                        if v:
                            v.status = "failed"
                            session.add(v)
                            session.commit()
                    try:
                        rclient = redis_lib.Redis.from_url(REDIS_URL)
                        message = {"from": "server", "payload": json.dumps({"type": "video_status", "id": video_id, "status": "failed"})}
                        rclient.publish("room:updates", json.dumps(message))
                    except Exception:
                        log.exception("Failed to publish failed status for video %s", video_id)
                except Exception:
                    log.exception("Failed to mark video %s as failed after download error", video_id)
            return

        resolutions = [(1080, "1080p"), (720, "720p"), (480, "480p")]
        master_entries = []

        ffmpeg_available = shutil.which("ffmpeg") is not None
        for height, label in resolutions:
            out_dir = tmpdir / label
            out_dir.mkdir(parents=True, exist_ok=True)
            playlist = out_dir / "playlist.m3u8"
            if simulate or not ffmpeg_available:
                # create placeholder TS segments and playlist
                segs = []
                for i in range(3):
                    seg = out_dir / f"seg_{i}.ts"
                    seg.write_text(f"SIMULATED SEGMENT {i} for {label}\n")
                    segs.append(seg.name)

                playlist.write_text("\n".join(["#EXTM3U", "#EXT-X-VERSION:3"] + [f"#EXTINF:6.0,\n{n}" for n in segs]))
            else:
                # run ffmpeg to produce HLS
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(local_input),
                    "-vf",
                    f"scale=-2:{height}",
                    "-c:a",
                    "aac",
                    "-ar",
                    "48000",
                    "-b:a",
                    "128k",
                    "-c:v",
                    "libx264",
                    "-profile:v",
                    "main",
                    "-crf",
                    "23",
                    "-g",
                    "48",
                    "-keyint_min",
                    "48",
                    "-sc_threshold",
                    "0",
                    "-hls_time",
                    "6",
                    "-hls_playlist_type",
                    "vod",
                    "-hls_segment_filename",
                    str(out_dir / "seg_%03d.ts"),
                    str(playlist),
                ]
                try:
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                except subprocess.CalledProcessError as e:
                    log.exception("ffmpeg failed: %s", e)
                    # fallback to simulated segments
                    segs = []
                    for i in range(3):
                        seg = out_dir / f"seg_{i}.ts"
                        seg.write_text(f"SIMULATED SEGMENT {i} for {label}\n")
                        segs.append(seg.name)
                    playlist.write_text("\n".join(["#EXTM3U", "#EXT-X-VERSION:3"] + [f"#EXTINF:6.0,\n{n}" for n in segs]))

            # upload all files from out_dir to S3 under hls/{video_basename}/{label}/
            prefix = f"hls/{Path(s3_key).stem}/{label}"
            for f in out_dir.iterdir():
                key = f"{prefix}/{f.name}"
                with f.open("rb") as fh:
                    s3.put_object(Bucket=S3_BUCKET_NAME, Key=key, Body=fh, ContentType="application/octet-stream")

            # register playlist URL
            playlist_key = f"{prefix}/playlist.m3u8"
            url = make_video_url(playlist_key)
            master_entries.append((label, url))

        # build master playlist referencing each variant
        master_lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
        for label, url in master_entries:
            # we don't set bandwidth/resolution exactly — keep simple
            master_lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=1280x720")
            master_lines.append(url)

        master_key = f"hls/{Path(s3_key).stem}/master.m3u8"
        s3.put_object(Bucket=S3_BUCKET_NAME, Key=master_key, Body="\n".join(master_lines).encode("utf-8"), ContentType="application/vnd.apple.mpegurl")

        master_url = make_video_url(master_key)

        # update DB record with hls_master
        if video_id:
            try:
                with get_session() as session:
                    v = session.get(Video, video_id)
                    if v:
                        v.hls_master = master_url
                        v.status = "ready"
                        session.add(v)
                        session.commit()
                        # notify via redis pubsub that video status changed
                        try:
                            rclient = redis_lib.Redis.from_url(REDIS_URL)
                            message = {"from": "server", "payload": json.dumps({"type": "video_status", "id": video_id, "status": "ready", "hls_master": master_url})}
                            rclient.publish("room:updates", json.dumps(message))
                        except Exception:
                            log.exception("Failed to publish redis update for video %s", video_id)
            except Exception:
                log.exception("Failed to update Video.hls_master for id=%s", video_id)

    finally:
        # ensure temp dir is cleaned up
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            log.exception("Failed to cleanup tmpdir %s", tmpdir)

        # If we reach here and the video still doesn't have an HLS master - mark it failed
        if video_id:
            try:
                with get_session() as session:
                    v = session.get(Video, video_id)
                    if v and not v.hls_master:
                        v.status = "failed"
                        session.add(v)
                        session.commit()
                        try:
                            rclient = redis_lib.Redis.from_url(REDIS_URL)
                            message = {"from": "server", "payload": json.dumps({"type": "video_status", "id": video_id, "status": "failed"})}
                            rclient.publish("room:updates", json.dumps(message))
                        except Exception:
                            log.exception("Failed to publish failed status for video %s", video_id)
            except Exception:
                log.exception("Failed to mark video %s as failed", video_id)


@dramatiq.actor
def transcode_video(s3_key: str, video_id: Optional[int] = None, simulate: bool = False):
    """Dramatiq actor wrapper that runs the transcode synchronously and returns.
    Keeping the heavy logic in a separate function makes it callable from tests.
    """
    _perform_transcode(s3_key, video_id=video_id, simulate=simulate)


def transcode_video_sync(s3_key: str, video_id: Optional[int] = None, simulate: bool = False):
    """Helper for tests / synchronous invocation."""
    _perform_transcode(s3_key, video_id=video_id, simulate=simulate)
