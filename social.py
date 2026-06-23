import os, base64
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status, Query
from sqlalchemy import select, desc
from database import get_db, AsyncSession
from models import User, Conversation, Group, Message, group_members
from auth import get_current_user
from jose import jwt
from config import settings
from ws_manager import ConnectionManager, get_manager
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

router = APIRouter(prefix="/social", tags=["social"])

async def get_user_from_token(token: str):
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id: return None
        async with get_db() as db: return await db.get(User, int(user_id))
    except: return None

@router.post("/conversations")
async def start_conversation(user2_id: int, current_user=Depends(get_current_user), db=Depends(get_db)):
    stmt = select(Conversation).where(
        ((Conversation.user1_id==current_user.id) & (Conversation.user2_id==user2_id)) |
        ((Conversation.user1_id==user2_id) & (Conversation.user2_id==current_user.id))
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing: return {"conversation_id": existing.id}
    key = os.urandom(32)
    conv = Conversation(user1_id=current_user.id, user2_id=user2_id, aes_key=base64.b64encode(key).decode())
    db.add(conv); await db.commit(); await db.refresh(conv)
    return {"conversation_id": conv.id}

@router.post("/groups")
async def create_group(name: str, description: str="", current_user=Depends(get_current_user), db=Depends(get_db)):
    key = os.urandom(32)
    group = Group(name=name, description=description, created_by=current_user.id, aes_key=base64.b64encode(key).decode())
    group.members.append(current_user)
    db.add(group); await db.commit(); await db.refresh(group)
    return {"group_id": group.id}

@router.post("/groups/{group_id}/join")
async def join_group(group_id: str, current_user=Depends(get_current_user), db=Depends(get_db)):
    group = await db.get(Group, group_id)
    if not group: raise HTTPException(404, "Group not found")
    if current_user in group.members: return {"message": "Already a member"}
    group.members.append(current_user); await db.commit()
    return {"message": "Joined"}

@router.get("/conversations")
async def list_conversations(current_user=Depends(get_current_user), db=Depends(get_db)):
    stmt = select(Conversation).where((Conversation.user1_id==current_user.id) | (Conversation.user2_id==current_user.id))
    convs = (await db.execute(stmt)).scalars().all()
    out = []
    for c in convs:
        other_id = c.user2_id if c.user1_id==current_user.id else c.user1_id
        other = await db.get(User, other_id)
        out.append({"id": c.id, "other_user": other.username if other else "Unknown"})
    return out

@router.get("/groups")
async def list_groups(current_user=Depends(get_current_user), db=Depends(get_db)):
    groups = (await db.execute(select(Group).where(Group.members.any(id=current_user.id)))).scalars().all()
    return [{"id": g.id, "name": g.name} for g in groups]

@router.get("/messages/{chat_id}")
async def get_messages(chat_id: str, chat_type: str="conversation", limit: int=50, offset: int=0,
                       current_user=Depends(get_current_user), db=Depends(get_db)):
    if chat_type == "conversation":
        conv = await db.get(Conversation, chat_id)
        if not conv or (conv.user1_id!=current_user.id and conv.user2_id!=current_user.id):
            raise HTTPException(403, "No access")
        key = base64.b64decode(conv.aes_key)
        stmt = select(Message).where(Message.conversation_id==chat_id).order_by(desc(Message.timestamp)).limit(limit).offset(offset)
    elif chat_type == "group":
        group = await db.get(Group, chat_id)
        if not group or current_user not in group.members:
            raise HTTPException(403, "No access")
        key = base64.b64decode(group.aes_key)
        stmt = select(Message).where(Message.group_id==chat_id).order_by(desc(Message.timestamp)).limit(limit).offset(offset)
    else: raise HTTPException(400, "Invalid chat_type")
    messages = (await db.execute(stmt)).scalars().all()
    aesgcm = AESGCM(key)
    out = []
    for msg in reversed(messages):
        nonce = base64.b64decode(msg.nonce)
        ciphertext = base64.b64decode(msg.encrypted_content)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None).decode()
        out.append({"id": msg.id, "sender_id": msg.sender_id, "sender_username": msg.sender.username,
                    "content": plaintext, "timestamp": str(msg.timestamp)})
    return out

@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, token: str = Query(...), manager: ConnectionManager = Depends(get_manager)):
    user = await get_user_from_token(token)
    if not user: await websocket.close(code=status.WS_1008_POLICY_VIOLATION); return
    await manager.connect(user.id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("action") != "send_message": continue
            conv_id = data.get("conversation_id")
            group_id = data.get("group_id")
            plaintext = data.get("content")
            if not plaintext: continue
            key = None
            async with get_db() as db:
                if conv_id:
                    conv = await db.get(Conversation, conv_id)
                    if not conv or user.id not in [conv.user1_id, conv.user2_id]:
                        await websocket.send_json({"error": "No access"}); continue
                    key = base64.b64decode(conv.aes_key)
                elif group_id:
                    group = await db.get(Group, group_id)
                    if not group or user not in group.members:
                        await websocket.send_json({"error": "No access"}); continue
                    key = base64.b64decode(group.aes_key)
                else: continue
                nonce = os.urandom(12)
                aesgcm = AESGCM(key)
                ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
                msg = Message(conversation_id=conv_id, group_id=group_id, sender_id=user.id,
                              encrypted_content=base64.b64encode(ciphertext).decode(),
                              nonce=base64.b64encode(nonce).decode())
                db.add(msg); await db.commit(); await db.refresh(msg)
                payload = {"id": msg.id, "sender_id": user.id, "sender_username": user.username,
                           "content": plaintext, "timestamp": str(msg.timestamp)}
                if conv_id:
                    conv = await db.get(Conversation, conv_id)
                    if conv:
                        await manager.send_personal_message(payload, conv.user1_id)
                        await manager.send_personal_message(payload, conv.user2_id)
                elif group_id:
                    group = await db.get(Group, group_id)
                    if group:
                        for m in group.members: await manager.send_personal_message(payload, m.id)
    except WebSocketDisconnect: manager.disconnect(user.id, websocket)
    except Exception: manager.disconnect(user.id, websocket)
