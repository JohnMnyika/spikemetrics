from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.config import settings
from app.core.database import SessionLocal
from app.api.v1.routes import router
from app.ingestion.sync import sync_football_data
from app.ingestion.providers import FootballDataOrgAdapter


async def ingest(app: FastAPI):
    try:
        async with SessionLocal() as session:
            app.state.last_sync = await sync_football_data(session, app.state.football_data_adapter)
    except Exception as exc:
        app.state.last_sync = {"status": "error", "error": str(exc)[:240]}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.last_sync = {"status": "not_started"}
    scheduler = None
    if settings.football_data_token:
        app.state.football_data_adapter = FootballDataOrgAdapter(settings.football_data_token)
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(ingest, "interval", args=[app], hours=max(1, settings.sync_interval_hours),
                          next_run_time=datetime.now(timezone.utc) + timedelta(seconds=5),
                          id="football_data_sync", max_instances=1, coalesce=True)
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
        await app.state.football_data_adapter.client.aclose()

app = FastAPI(title="SpikeMetrics", version="1.0.0", description="Pre-match football analysis and probabilistic predictions", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api/v1")
