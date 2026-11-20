import math
import numpy as np
from scipy.stats import poisson


def _tau(x: int, y: int, lh: float, la: float, rho: float) -> float:
    if (x, y) == (0, 0): return 1 - lh * la * rho
    if (x, y) == (0, 1): return 1 + lh * rho
    if (x, y) == (1, 0): return 1 + la * rho
    if (x, y) == (1, 1): return 1 - rho
    return 1.0


def predict(lambda_home: float, lambda_away: float, rho: float = -0.08, max_goals: int = 8, simulations: int = 10000) -> dict:
    lh, la = max(.05, lambda_home), max(.05, lambda_away)
    grid = np.array([[poisson.pmf(x, lh) * poisson.pmf(y, la) * max(0, _tau(x,y,lh,la,rho)) for y in range(max_goals+1)] for x in range(max_goals+1)])
    grid /= grid.sum()
    home = sum(grid[x,y] for x in range(max_goals+1) for y in range(max_goals+1) if x > y)
    draw = sum(grid[x,x] for x in range(max_goals+1))
    home, draw = round(float(home), 6), round(float(draw), 6)
    away = round(1-home-draw, 6)
    # Monte Carlo is a cross-check; seeded for repeatable API results.
    rng = np.random.default_rng(17)
    mh, ma = rng.poisson(lh, simulations), rng.poisson(la, simulations)
    return {"probabilities": {"home": home, "draw": draw, "away": away},
            "score_matrix": np.round(grid, 8).tolist(), "projected_score": f"{int(round(lh))}-{int(round(la))}",
            "lambda_home": round(lh, 3), "lambda_away": round(la, 3),
            "markets": {"over_1_5": round(float(grid.sum() - sum(grid[x,y] for x in range(9) for y in range(9) if x+y <= 1)),4),
                        "over_2_5": round(float(sum(grid[x,y] for x in range(9) for y in range(9) if x+y >= 3)),4),
                        "over_3_5": round(float(sum(grid[x,y] for x in range(9) for y in range(9) if x+y >= 4)),4),
                        "btts": round(float(sum(grid[x,y] for x in range(1,9) for y in range(1,9))),4)},
            "monte_carlo": {"home": round(float((mh>ma).mean()),4), "draw": round(float((mh==ma).mean()),4), "away": round(float((mh<ma).mean()),4), "iterations": simulations}}
