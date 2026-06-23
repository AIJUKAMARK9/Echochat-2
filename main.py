import os, logging, asyncio, uuid, time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from flet_fastapi import FletApp
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from database import get_engine, get_session_maker, Base
from auth import router as auth_router, get_current_user
from social import router as social_router
from ws_manager import get_manager
from presence import router as presence_router
from mediaproxy import save_upload
from cleanup import cleanup_temp_chunks
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s [%(levelname)s] rid=%(request_id)s %(message)s")
logger = logging.getLogger("echochat")

class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = getattr(record, "request_id", "----")
        return True
logger.addFilter(RequestIDFilter())

async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(f"Unhandled: {exc}", extra={"request_id": request_id})
    return JSONResponse(status_code=500, content={"error": "Internal server error", "request_id": request_id})

MAX_BODY_SIZE = 1_000_000
class MaxSizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.headers.get("content-length") and int(request.headers.get("content-length")) > MAX_BODY_SIZE:
            return JSONResponse(status_code=413, content={"error": "Request body too large"})
        return await call_next(request)

@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.LOCAL_MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
    Path("static").mkdir(exist_ok=True)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database ready")
    tasks = [asyncio.create_task(cleanup_temp_chunks())]
    yield
    for t in tasks: t.cancel()
    logger.info("Shutdown")

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan, exception_handlers={Exception: global_exception_handler})
app.add_middleware(MaxSizeMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    logger.info(f"--> {request.method} {request.url.path}", extra={"request_id": request.state.request_id})
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    response.headers["X-Request-ID"] = request.state.request_id
    logger.info(f"<-- {response.status_code} ({duration:.3f}s)", extra={"request_id": request.state.request_id})
    return response

app.include_router(auth_router)
app.include_router(social_router)
app.include_router(presence_router)

# Media upload endpoint for profile pic
@app.post("/upload/profile")
async def upload_profile_pic(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    url = await save_upload(file, current_user.id, "profile")
    return {"url": url}

MEDIA_ROOT = Path(settings.LOCAL_MEDIA_ROOT)
encryption_key = bytes.fromhex(settings.MEDIA_ENCRYPTION_KEY)

@app.get("/media/{file_path:path}")
async def serve_media(file_path: str, current_user=Depends(get_current_user)):
    file_location = MEDIA_ROOT / file_path
    if not file_location.exists(): raise HTTPException(404)
    with open(file_location, "rb") as f: encrypted = f.read()
    if len(encrypted) < 12: raise HTTPException(500, "Invalid encrypted file")
    nonce, ciphertext = encrypted[:12], encrypted[12:]
    aesgcm = AESGCM(encryption_key)
    try: plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except: raise HTTPException(500, "Decryption failed")
    return Response(content=plaintext, media_type="application/octet-stream")

@app.get("/health")
async def health():
    try:
        async with get_session_maker()() as db: await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except: return JSONResponse(status_code=503, content={"status": "unhealthy"})

from flet_app import build_flet_app
app.mount("/app", FletApp(build_flet_app()))
app.mount("/static", StaticFiles(directory="static"), name="static")
