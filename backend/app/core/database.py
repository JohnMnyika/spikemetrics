from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
import os
from app.core.config import settings

def normalize_database_url(raw_url: str):
    url = make_url(raw_url)
    query = dict(url.query)
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+asyncpg")
    if "sslmode" in query:
        query["ssl"] = query.pop("sslmode")
        query.pop("channel_binding", None)
        url = url.set(query=query)
    return url


database_url = normalize_database_url(settings.database_url)
if os.getenv("VERCEL"):
    engine = create_async_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
else:
    engine = create_async_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=2)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with SessionLocal() as session:
        yield session
