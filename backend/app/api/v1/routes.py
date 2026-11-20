from datetime import datetime, timedelta, timezone
import secrets
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from app.core.config import settings
from app.core.database import SessionLocal
from app.ingestion.providers import MockDemoProvider
from app.models.entities import ApiQuotaUsage, Fixture, League, Team
from app.simulation.dixon_coles import predict

router = APIRouter()
demo = MockDemoProvider()


class SimulateRequest(BaseModel):
    lambda_home: float | None = Field(default=None, gt=0, le=8)
    lambda_away: float | None = Field(default=None, gt=0, le=8)
    home_adjustment: float = Field(default=0, ge=-.2, le=.2)
    away_adjustment: float = Field(default=0, ge=-.2, le=.2)


def _demo_prediction(f: dict) -> dict:
    return {**f, **predict(f["lambda_home"], f["lambda_away"]), "kickoff": f["kickoff"].isoformat(),
            "confidence": 72 if f["xg_available"] else 58, "data_completeness": 78 if f["xg_available"] else 55,
            "source": "demo", "lineup_confirmed": f["lineup_confirmed"]}


async def _real_upcoming(session):
    now = datetime.now(timezone.utc)
    fixtures_result = await session.execute(select(Fixture).where(Fixture.source == "football-data.org", Fixture.kickoff_time >= now,
                                    Fixture.status.notin_(("finished", "cancelled", "postponed", "suspended"))).order_by(Fixture.kickoff_time).limit(80))
    fixtures = fixtures_result.scalars().all()
    if not fixtures:
        return []
    all_finished_result = await session.execute(select(Fixture).where(Fixture.source == "football-data.org", Fixture.status == "finished",
                                                Fixture.home_score.is_not(None), Fixture.away_score.is_not(None)))
    finished = all_finished_result.scalars().all()
    teams = {x.id: x.name for x in (await session.execute(select(Team))).scalars().all()}
    leagues = {x.id: x.name for x in (await session.execute(select(League))).scalars().all()}

    def rates(fixture):
        league_games = [g for g in finished if g.league_id == fixture.league_id]
        hmean = sum(g.home_score for g in league_games) / len(league_games) if league_games else 1.45
        amean = sum(g.away_score for g in league_games) / len(league_games) if league_games else 1.15
        home_games = [g for g in league_games if g.home_team_id == fixture.home_team_id]
        away_games = [g for g in league_games if g.away_team_id == fixture.away_team_id]
        # Three league-average pseudo-observations shrink small samples toward the competition mean.
        home_attack = (sum(g.home_score for g in home_games) + 3*hmean) / (len(home_games)+3) / max(.1,hmean)
        away_defense = (sum(g.home_score for g in away_games) + 3*hmean) / (len(away_games)+3) / max(.1,hmean)
        away_attack = (sum(g.away_score for g in away_games) + 3*amean) / (len(away_games)+3) / max(.1,amean)
        home_defense = (sum(g.away_score for g in home_games) + 3*amean) / (len(home_games)+3) / max(.1,amean)
        return max(.25,min(3.5,hmean*home_attack*away_defense)), max(.25,min(3.5,amean*away_attack*home_defense)), len(home_games)+len(away_games)

    def recent_goals(team_id):
        appearances = [g for g in finished if g.home_team_id == team_id or g.away_team_id == team_id]
        appearances.sort(key=lambda game: game.kickoff_time)
        return [g.home_score if g.home_team_id == team_id else g.away_score for g in appearances[-10:]]

    output = []
    for f in fixtures:
        lh, la, sample = rates(f)
        output.append({"id": f.id, "external_id": f.external_id, "league": leagues.get(f.league_id, "Football"),
                       "home": teams.get(f.home_team_id, "Home"), "away": teams.get(f.away_team_id, "Away"),
                       "kickoff": f.kickoff_time.isoformat(), "status": f.status,
                       "lambda_home": round(lh,3), "lambda_away": round(la,3), "xg_available": False,
                       "lineup_confirmed": False, "spike": None, "confidence": min(72, 42+sample),
                       "data_completeness": min(60, 35+sample), "source": "football-data.org",
                       "sample_matches": sample, "form": {"home": recent_goals(f.home_team_id), "away": recent_goals(f.away_team_id)}, **predict(lh,la)})
    return output


async def _find_fixture(fixture_id: int):
    async with SessionLocal() as session:
        upcoming = await _real_upcoming(session)
    return next((f for f in upcoming if f["id"] == fixture_id), None)


@router.get("/health")
async def health(request: Request):
    return {"status": "ok", "time": datetime.now(timezone.utc), "provider": "football-data.org" if settings.football_data_token else "demo",
            "last_sync": request.app.state.last_sync}


@router.get("/fixtures/upcoming")
async def upcoming():
    async with SessionLocal() as session:
        real = await _real_upcoming(session)
    if real:
        return {"items": real, "mode": "live", "last_updated": datetime.now(timezone.utc).isoformat()}
    return {"items": [_demo_prediction(f) for f in demo.fixtures], "mode": "demo", "last_updated": datetime.now(timezone.utc).isoformat()}


@router.get("/fixtures/{fixture_id}/prediction")
async def fixture_prediction(fixture_id: int):
    real = await _find_fixture(fixture_id)
    if real:
        return {**real, "availability": [],
                "data_gaps": ["xG data is not included in the free fixtures/results tier", "Starting lineups have not been confirmed"], "audit": []}
    f = next((x for x in demo.fixtures if x["id"] == fixture_id), None)
    if not f: raise HTTPException(404, "Fixture not found")
    return {**_demo_prediction(f), "form": {"home": [1.1,1.5,1.8,2.1,1.4,1.6,2.2,1.9,1.3,1.8], "away": [1.6,1.2,1.4,1.8,1.9,1.1,1.7,1.4,1.3,1.5]}, "availability": [], "data_gaps": ["Demo data only; configure a football-data.org token for real fixtures"], "audit": []}


@router.post("/fixtures/{fixture_id}/simulate")
async def simulate(fixture_id: int, request: SimulateRequest):
    f = await _find_fixture(fixture_id)
    if f is None:
        f = next((x for x in demo.fixtures if x["id"] == fixture_id), None)
    if not f: raise HTTPException(404, "Fixture not found")
    lh = (request.lambda_home or f["lambda_home"]) * (1 + request.home_adjustment)
    la = (request.lambda_away or f["lambda_away"]) * (1 + request.away_adjustment)
    return {**predict(lh, la), "audit": [{"home_multiplier":round(lh/f["lambda_home"],3), "away_multiplier":round(la/f["lambda_away"],3)}]}


@router.get("/calibration/summary")
async def calibration():
    return {"brier_score":None,"log_loss":None,"samples":0,"curve":[],"status":"No settled real predictions yet"}


@router.get("/system/quotas")
async def quotas():
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        rows = (await session.execute(select(ApiQuotaUsage).where(ApiQuotaUsage.window_start >= now-timedelta(minutes=1)))).scalars().all()
    used = sum(x.request_count for x in rows if x.provider == "football-data.org")
    return {"api_football":{"used":0,"limit":settings.api_football_daily_limit,"remaining":settings.api_football_daily_limit,"window":"daily", "configured":bool(settings.api_football_key)},
            "football_data":{"used":used,"limit":settings.football_data_per_minute,"remaining":max(0,settings.football_data_per_minute-used),"window":"per minute", "configured":bool(settings.football_data_token)}}


async def _sync_now(request: Request):
    from app.main import ingest
    await ingest(request.app)


@router.post("/admin/sync")
async def sync(background_tasks: BackgroundTasks, request: Request):
    supplied = request.headers.get("x-admin-token", "")
    if settings.admin_api_token and not secrets.compare_digest(supplied, settings.admin_api_token):
        raise HTTPException(401, "Invalid admin token")
    if not settings.admin_api_token and settings.football_data_token:
        raise HTTPException(503, "Configure ADMIN_API_TOKEN before enabling remote sync")
    if not settings.football_data_token:
        return {"status":"demo", "message":"Set FOOTBALL_DATA_TOKEN to enable live fixture sync"}
    background_tasks.add_task(_sync_now, request)
    return {"status":"queued","provider":"football-data.org"}
