from datetime import datetime, timezone
import math


def decayed_ratings(matches: list[dict], xi: float = 0.025) -> dict:
    """Estimate home/away attack and defense with exponentially decayed observations."""
    if not matches: return {"attack_home": 1.35, "attack_away": 1.1, "defense_home": 1.1, "defense_away": 1.2}
    now = datetime.now(timezone.utc)
    total_weight = sum(math.exp(-xi * max(0, (now - m["date"]).total_seconds() / 86400)) for m in matches) or 1
    def avg(key, fallback):
        return sum(m.get(key, fallback) * math.exp(-xi * max(0, (now - m["date"]).total_seconds() / 86400)) for m in matches) / total_weight
    return {"attack_home": avg("home_xg", 1.35), "attack_away": avg("away_xg", 1.1), "defense_home": avg("away_xg", 1.1), "defense_away": avg("home_xg", 1.35)}
