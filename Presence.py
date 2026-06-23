from fastapi import APIRouter, WebSocket, Depends, Query, status
from sqlalchemy import select
from database import get_db, AsyncSession
from models import User
from jose import jwt
from config import settings
from ws_manager import ConnectionManager, get_manager
import asyncio

router = APIRouter(prefix="/presence", tags=["presence"])

async def get_user_from_token(token: str):
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id: return None
        async with get_db() as db: return await db.get(User, int(user_id))
    except: return None

@router.websocket("/ws")
async def presence_ws(websocket: WebSocket, token: str = Query(...), manager: ConnectionManager = Depends(get_manager)):
    user = await get_user_from_token(token)
    if not user: await websocket.close(code=status.WS_1008_POLICY_VIOLATION); return
    # use a separate set for presence (not the chat manager)
    from collections import defaultdict
    online = defaultdict(set)
    online[user.id].add(websocket)
    try:
        await websocket.accept()
        while True:
            # just keep connection alive
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except: pass
    finally:
        online[user.id].discard(websocket)
        if not online[user.id]: del online[user.id]
