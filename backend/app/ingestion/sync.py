"""Normalize football-data.org fixtures/results into the canonical PostgreSQL schema."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.entities import ApiQuotaUsage, Fixture, League, Team, TeamAlias, TeamMatchStats
from app.ingestion.providers import FootballDataOrgAdapter, _key, resolve_team


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


async def _team(session: AsyncSession, league_id: int, name: str) -> Team:
    alias_rows = (await session.execute(select(TeamAlias.normalized_alias, TeamAlias.team_id).where(TeamAlias.league_id == league_id))).all()
    resolved_id = resolve_team(name, {alias: team_id for alias, team_id in alias_rows}) if alias_rows else None
    result = await session.execute(select(Team).where(Team.id == resolved_id)) if resolved_id else await session.execute(select(Team).where(Team.league_id == league_id, Team.name == name))
    team = result.scalar_one_or_none()
    if team is None:
        team = Team(league_id=league_id, name=name)
        session.add(team)
        await session.flush()
    alias = await session.execute(select(TeamAlias).where(TeamAlias.league_id == league_id, TeamAlias.normalized_alias == _key(name)))
    if alias.scalar_one_or_none() is None:
        session.add(TeamAlias(league_id=league_id, team_id=team.id, normalized_alias=_key(name)))
    return team


async def sync_football_data(session: AsyncSession, adapter: FootballDataOrgAdapter | None = None) -> dict:
    """Fetch at most the configured competition catalogue at 6.2s spacing and upsert it."""
    owns_adapter = adapter is None
    adapter = adapter or FootballDataOrgAdapter(settings.football_data_token)
    competitions = [code.strip() for code in settings.football_data_competitions.split(",") if code.strip()]
    if len(competitions) > settings.football_data_per_minute:
        raise ValueError("Configured competitions exceed the football-data.org per-minute budget")
    counts = {"competitions": 0, "fixtures": 0, "results": 0, "errors": []}
    for code in competitions:
        try:
            today = datetime.now(timezone.utc).date()
            start = (today - timedelta(days=150)).isoformat()
            end = (today + timedelta(days=45)).isoformat()
            payload = await adapter.fixtures(code, date_from=start, date_to=end)
            competition = payload.get("competition") or {"name": code, "area": {"name": "Unknown"}}
            result = await session.execute(select(League).where(League.name == competition["name"]))
            league = result.scalar_one_or_none()
            if league is None:
                league = League(name=competition["name"], country=(competition.get("area") or {}).get("name", "Unknown"), provider_code=code)
                session.add(league)
                await session.flush()
            counts["competitions"] += 1
            for raw in payload.get("matches", []):
                home_name, away_name = raw.get("homeTeam", {}).get("name"), raw.get("awayTeam", {}).get("name")
                if not home_name or not away_name or not raw.get("utcDate"):
                    continue
                home, away = await _team(session, league.id, home_name), await _team(session, league.id, away_name)
                external_id = str(raw["id"])
                result = await session.execute(select(Fixture).where(Fixture.source == "football-data.org", Fixture.external_id == external_id))
                fixture = result.scalar_one_or_none()
                score = raw.get("score", {}).get("fullTime", {})
                home_score, away_score = score.get("home"), score.get("away")
                status = raw.get("status", "SCHEDULED").lower()
                if fixture is None:
                    fixture = Fixture(league_id=league.id, home_team_id=home.id, away_team_id=away.id,
                                      kickoff_time=_instant(raw["utcDate"]), status=status,
                                      home_score=home_score, away_score=away_score,
                                      source="football-data.org", external_id=external_id)
                    session.add(fixture)
                    await session.flush()
                else:
                    fixture.league_id, fixture.home_team_id, fixture.away_team_id = league.id, home.id, away.id
                    fixture.kickoff_time, fixture.status = _instant(raw["utcDate"]), status
                    fixture.home_score, fixture.away_score = home_score, away_score
                if status == "finished" and home_score is not None and away_score is not None:
                    counts["results"] += 1
                    for team, goals in ((home, home_score), (away, away_score)):
                        stat = await session.execute(select(TeamMatchStats).where(TeamMatchStats.fixture_id == fixture.id, TeamMatchStats.team_id == team.id))
                        match_stat = stat.scalar_one_or_none()
                        if match_stat is None:
                            session.add(TeamMatchStats(fixture_id=fixture.id, team_id=team.id, goals=goals))
                        else:
                            match_stat.goals = goals
                else:
                    counts["fixtures"] += 1
            session.add(ApiQuotaUsage(provider="football-data.org", window_start=datetime.now(timezone.utc), request_count=1, daily_limit=settings.football_data_per_minute))
            await session.commit()
        except Exception as exc:
            await session.rollback()
            counts["errors"].append({"competition": code, "error": str(exc)[:240]})
    if owns_adapter:
        await adapter.client.aclose()
    counts["status"] = "complete" if not counts["errors"] else "partial"
    counts["synced_at"] = datetime.now(timezone.utc).isoformat()
    return counts
