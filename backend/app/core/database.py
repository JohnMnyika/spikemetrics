from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
from app.core.config import settings

database_url = make_url(settings.database_url)
query = dict(database_url.query)
if database_url.drivername in ("postgres", "postgresql"):
    database_url = database_url.set(drivername="postgresql+asyncpg")
if "sslmode" in query:
    query["ssl"] = query.pop("sslmode")
    query.pop("channel_binding", None)
    database_url = database_url.set(query=query)
engine = create_async_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=2)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with SessionLocal() as session:
        yield session
