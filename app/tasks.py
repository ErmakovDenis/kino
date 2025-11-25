import os
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from pathlib import Path

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
