import os, shutil, asyncio, logging
from pathlib import Path
from config import settings

logger = logging.getLogger(__name__)
MEDIA_ROOT = Path(settings.LOCAL_MEDIA_ROOT)
os.makedirs(MEDIA_ROOT, exist_ok=True)

async def save_upload(file, user_id: int, folder: str = "profile") -> str:
    safe_name = Path(file.filename).name.replace(" ", "_")
    user_dir = MEDIA_ROOT / str(user_id) / folder
    user_dir.mkdir(parents=True, exist_ok=True)
    dest = user_dir / safe_name
    with open(dest, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return f"{settings.LOCAL_MEDIA_URL_PREFIX}{user_id}/{folder}/{safe_name}"
