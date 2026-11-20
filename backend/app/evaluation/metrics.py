import math


def brier_score(probabilities: list[float], outcome: int) -> float:
    return sum((p - (1.0 if i == outcome else 0.0)) ** 2 for i, p in enumerate(probabilities))


def log_loss(probabilities: list[float], outcome: int) -> float:
    return -math.log(max(1e-15, probabilities[outcome]))
