from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "EchoChat"
    APP_VERSION: str = "1.0.0"

    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR}/echochat.db"
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    MEDIA_ENCRYPTION_KEY: str   # 64 hex chars

    LOCAL_MEDIA_ROOT: str = str(BASE_DIR / "media")
    LOCAL_MEDIA_URL_PREFIX: str = "/media/"

    LOG_LEVEL: str = "INFO"
    API_BASE: str = "http://localhost:8000"
    CORS_ORIGINS: str = "http://localhost:8550,http://localhost:8000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

settings = Settings()
