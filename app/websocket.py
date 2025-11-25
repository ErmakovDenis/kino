from typing import Dict, Set
from starlette.websockets import WebSocket
import asyncio
import json
import os

REDIS_URL = os.environ.get("REDIS_URL")


class InMemoryManager:
    def __init__(self):
        self.rooms: Dict[str, Set[WebSocket]] = {}

    async def connect(self, room: str, ws: WebSocket):
        await ws.accept()
        self.rooms.setdefault(room, set()).add(ws)

    async def disconnect(self, room: str, ws: WebSocket):
        if room in self.rooms and ws in self.rooms[room]:
            self.rooms[room].remove(ws)

    async def broadcast(self, room: str, message: dict):
        if room not in self.rooms:
            return
        data = json.dumps(message)
        to_remove = []
        for ws in set(self.rooms[room]):
            try:
                await ws.send_text(data)
            except RuntimeError:
                to_remove.append(ws)
        for ws in to_remove:
            self.rooms[room].remove(ws)


class RedisManager:
    def __init__(self, channel_prefix: str = "room"):
        import redis.asyncio as aioredis  # local import

        self._redis = aioredis.from_url(REDIS_URL or "redis://localhost:6379")
        self.prefix = channel_prefix

    async def connect(self, room: str, ws: WebSocket):
        
        await ws.accept()
        sub = self._redis.pubsub()
        ch = f"{self.prefix}:{room}"
        await sub.subscribe(ch)

        async def reader():
            async for msg in sub.listen():
                if msg is None:
                    continue
                if msg.get("type") != "message":
                    continue
                try:
                    await ws.send_text(msg["data"].decode())
                except Exception:
                    break

        
        ws._redis_sub = sub
        ws._redis_task = asyncio.create_task(reader())

    async def disconnect(self, room: str, ws: WebSocket):
        if hasattr(ws, "_redis_task"):
            task = ws._redis_task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if hasattr(ws, "_redis_sub"):
            await ws._redis_sub.unsubscribe(f"{self.prefix}:{room}")

    async def broadcast(self, room: str, message: dict):
        ch = f"{self.prefix}:{room}"
        await self._redis.publish(ch, json.dumps(message))



use_redis = os.environ.get("USE_REDIS", "0").lower() in ("1", "true", "yes")
manager = RedisManager() if REDIS_URL and use_redis else InMemoryManager()
