import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api import router as api_router
from app.db import create_db_and_tables
from app import websocket


app = FastAPI(title="Kino — synced watch party (MVP)")

app.include_router(api_router)


templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.websocket("/ws/{room_code}")
async def ws_endpoint(ws: WebSocket, room_code: str):
    
    manager = websocket.manager
    await manager.connect(room_code, ws)
    try:
        while True:
            data = await ws.receive_text()
            
            await manager.broadcast(room_code, {
                "from": "peer",
                "payload": data,
            })
    except WebSocketDisconnect:
        await manager.disconnect(room_code, ws)
