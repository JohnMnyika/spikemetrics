import re
import asyncio
from datetime import datetime, timedelta, timezone
from rapidfuzz import process, fuzz
from app.core.limits import QuotaTracker, SpacedRateLimiter


def _key(value: str) -> str:
    value = re.sub(r"\butd\b", "united", value.lower())
    value = re.sub(r"\b(fc|cf|afc)\b", "", value)
    value = re.sub(r"\bman\b", "manchester", value)
    return re.sub(r"[^a-z0-9]", "", value)


def resolve_team(name: str, canonical: dict[str, int], threshold: int = 82) -> int | None:
    """Resolve provider spelling to a deterministic canonical team id."""
    keys = {_key(alias): team_id for alias, team_id in canonical.items()}
    normalized = _key(name)
    if normalized in keys:
        return keys[normalized]
    match = process.extractOne(normalized, list(keys), scorer=fuzz.ratio, score_cutoff=threshold)
    return keys[match[0]] if match else None


class BaseAdapter:
    def __init__(self, base_url: str, headers: dict | None = None, interval: float = 0.0):
        import httpx
        self.base_url, self.headers = base_url.rstrip("/"), headers or {}
        self.client = httpx.AsyncClient(timeout=15, headers=self.headers)
        self.limiter = SpacedRateLimiter(interval)
        self.cache: dict[str, tuple[datetime, dict]] = {}
        self.validators: dict[str, dict[str, str]] = {}

    async def get(self, path: str, params: dict | None = None, ttl: int = 300):
        import httpx
        key = path + str(params)
        cached = self.cache.get(key)
        if cached and (datetime.now(timezone.utc) - cached[0]).total_seconds() < ttl:
            return cached[1]
        headers = dict(self.validators.get(key, {}))
        for attempt in range(4):
            await self.limiter.acquire()
            try:
                response = await self.client.get(f"{self.base_url}/{path.lstrip('/')}", params=params, headers=headers)
                if response.status_code == 304 and cached:
                    self.cache[key] = (datetime.now(timezone.utc), cached[1])
                    return cached[1]
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == 3: response.raise_for_status()
                    await asyncio.sleep(min(8, 0.5 * 2**attempt))
                    continue
                response.raise_for_status()
                data = response.json()
                validators = {}
                if response.headers.get("ETag"): validators["If-None-Match"] = response.headers["ETag"]
                if response.headers.get("Last-Modified"): validators["If-Modified-Since"] = response.headers["Last-Modified"]
                self.validators[key] = validators
                self.cache[key] = (datetime.now(timezone.utc), data)
                return data
            except httpx.TransportError:
                if attempt == 3: raise
                await asyncio.sleep(min(8, 0.5 * 2**attempt))


class FootballDataOrgAdapter(BaseAdapter):
    def __init__(self, token: str = ""):
        super().__init__("https://api.football-data.org/v4", {"X-Auth-Token": token}, interval=6.2)

    async def fixtures(self, competition: str, date_from: str | None = None, date_to: str | None = None):
        return await self.get(f"competitions/{competition}/matches", {"dateFrom": date_from, "dateTo": date_to}, ttl=21600)

    async def standings(self, competition: str):
        return await self.get(f"competitions/{competition}/standings")


class ApiFootballFreeAdapter(BaseAdapter):
    def __init__(self, key: str = ""):
        super().__init__("https://v3.football.api-sports.io", {"x-apisports-key": key})
        self.quota = QuotaTracker(100)

    def _reserved_window(self, kickoff: datetime) -> bool:
        delta = kickoff - datetime.now(timezone.utc)
        return timedelta(0) <= delta <= timedelta(minutes=90)

    async def lineup(self, fixture_id: int, kickoff: datetime):
        if not self._reserved_window(kickoff) or not self.quota.consume():
            return {"available": False, "reason": "outside reserved kickoff window or daily quota exhausted"}
        return await self.get("fixtures/lineups", {"fixture": fixture_id}, ttl=3600)

    async def injuries(self, fixture_id: int, kickoff: datetime):
        if not self._reserved_window(kickoff) or not self.quota.consume():
            return {"available": False, "reason": "outside reserved kickoff window or daily quota exhausted"}
        return await self.get("injuries", {"fixture": fixture_id}, ttl=3600)


class OpenLigaDbAdapter(BaseAdapter):
    def __init__(self): super().__init__("https://www.openligadb.de/api", interval=0.2)
    async def matches(self, league: str): return await self.get(f"getmatchdata/{league}")


class TheSportsDbAdapter(BaseAdapter):
    def __init__(self, api_key: str = "3"): super().__init__(f"https://www.thesportsdb.com/api/v1/json/{api_key}", interval=2)
    async def events(self, league_id: str): return await self.get(f"eventsnextleague.php", {"id": league_id})


class OpenMetricsAdapter:
    """Cached historical-data adapter; parsers deliberately degrade when xG is absent."""
    def __init__(self): self.cache = {}
    async def csv(self, url: str):
        import pandas as pd
        import httpx
        cached = self.cache.get(url)
        if cached and datetime.now(timezone.utc) - cached[0] < timedelta(hours=24): return cached[1]
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url); response.raise_for_status()
        frame = pd.read_csv(__import__("io").StringIO(response.text))
        self.cache[url] = (datetime.now(timezone.utc), frame)
        return frame


class MockDemoProvider:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.fixtures = [
            {"id": -1, "league": "Premier League", "home": "Arsenal", "away": "Liverpool", "kickoff": now + timedelta(hours=5), "lambda_home": 1.72, "lambda_away": 1.38, "xg_available": False, "lineup_confirmed": False, "spike": None},
            {"id": -2, "league": "La Liga", "home": "Real Madrid", "away": "Barcelona", "kickoff": now + timedelta(hours=28), "lambda_home": 1.86, "lambda_away": 1.55, "xg_available": False, "lineup_confirmed": False, "spike": None},
            {"id": -3, "league": "Bundesliga", "home": "Bayern Munich", "away": "Dortmund", "kickoff": now + timedelta(hours=48), "lambda_home": 2.15, "lambda_away": 1.24, "xg_available": False, "lineup_confirmed": False, "spike": None},
        ]
