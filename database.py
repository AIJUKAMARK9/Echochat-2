import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import event, text
from config import settings

logger = logging.getLogger(__name__)
Base = declarative_base()

_engine = None
_session_maker = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
        )
        @event.listens_for(_engine.sync_engine, "connect")
        def _set_pragma(dbapi_conn, record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    return _engine

def get_session_maker():
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _session_maker

async def get_db():
    async with get_session_maker()() as session:
        yield session
