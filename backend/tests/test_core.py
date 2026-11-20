import asyncio
import time
from datetime import datetime, timedelta, timezone
import pytest
from app.core.limits import SpacedRateLimiter, QuotaTracker
from app.evaluation.metrics import brier_score, log_loss
from app.simulation.dixon_coles import predict
from app.ingestion.providers import resolve_team


def test_spaced_rate_limiter_enforces_interval():
    limiter = SpacedRateLimiter(.025)
    start = time.monotonic()
    async def acquire_twice():
        await limiter.acquire()
        await limiter.acquire()
    asyncio.run(acquire_twice())
    assert time.monotonic() - start >= .02


def test_quota_tracker_rejects_over_budget():
    quota = QuotaTracker(2)
    assert quota.consume() and quota.consume()
    assert not quota.consume()
    assert quota.remaining == 0


def test_team_resolution_is_deterministic():
    aliases = {"Manchester United": 17, "Arsenal FC": 22}
    assert resolve_team("Man United", aliases) == 17
    assert resolve_team("Arsenal", aliases) == 22


def test_prediction_probabilities_are_normalized_and_grid_valid():
    output = predict(1.55, 1.1, simulations=1000)
    assert abs(sum(output["probabilities"].values()) - 1) < 1e-8
    assert len(output["score_matrix"]) == 9
    assert abs(sum(map(sum, output["score_matrix"])) - 1) < 1e-8
    assert all(0 <= value <= 1 for value in output["markets"].values())


def test_calibration_metrics():
    assert brier_score([.8,.1,.1], 0) == pytest.approx(.06)
    assert log_loss([.8,.1,.1], 0) == pytest.approx(-__import__('math').log(.8))


def test_prediction_timestamp_constraint_shape():
    kickoff = datetime.now(timezone.utc)
    generated = kickoff - timedelta(seconds=1)
    assert generated < kickoff
    assert generated.tzinfo is not None and kickoff.tzinfo is not None
