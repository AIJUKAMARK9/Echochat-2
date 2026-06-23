import asyncio, time, logging
from pathlib import Path
logger = logging.getLogger(__name__)

async def cleanup_temp_chunks():
    TEMP_DIR = Path("/tmp/echochat_chunks")
    while True:
        try:
            if TEMP_DIR.exists():
                now = time.time()
                for user_dir in TEMP_DIR.iterdir():
                    if user_dir.is_dir():
                        for chunk in user_dir.glob("*.part"):
                            if now - chunk.stat().st_mtime > 3600:
                                chunk.unlink()
                        if not any(user_dir.iterdir()):
                            user_dir.rmdir()
        except Exception as e: logger.exception("Temp cleanup error")
        await asyncio.sleep(600)
