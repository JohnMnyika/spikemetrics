from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
import os
from app.core.config import settings

database_url = make_url(settings.database_url)
query = dict(database_url.query)
if database_url.drivername in ("postgres", "postgresql"):
    database_url = database_url.set(drivername="postgresql+asyncpg")
if "sslmode" in query:
    query["ssl"] = query.pop("sslmode")
    query.pop("channel_binding", None)
    database_url = database_url.set(query=query)
if os.getenv("VERCEL"):
    engine = create_async_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
else:
    engine = create_async_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=2)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with SessionLocal() as session:
        yield session
