from statistics import mean


def detect_spikes(matches: list[dict], short_n: int = 4, long_n: int = 20) -> dict:
    recent, baseline = matches[-short_n:], matches[-long_n:]
    if not recent or not baseline: return {"form_spike": None, "xg_regression": None}
    short_form = mean(m.get("points", 1) for m in recent)
    long_form = mean(m.get("points", 1) for m in baseline)
    short_diff = mean(m.get("goals", 0) - m.get("xg", m.get("goals", 0)) for m in recent)
    return {"form_spike": "positive" if short_form - long_form >= 0.6 else "negative" if short_form - long_form <= -0.6 else None,
            "xg_regression": "overperforming xG" if short_diff >= 0.8 else "underperforming xG" if short_diff <= -0.8 else None,
            "short_points_per_game": round(short_form, 2), "baseline_points_per_game": round(long_form, 2)}
