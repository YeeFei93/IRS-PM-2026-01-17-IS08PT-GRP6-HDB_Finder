from __future__ import annotations

import math

from input_data_for_all_models import ModelContext


MODEL_KEY = "euclidean_distance"
MODEL_NAME = "euclidean_distance"


def _l2_normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def _euclidean_distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((a_val - b_val) ** 2 for a_val, b_val in zip(a, b)))


def recommend(context: ModelContext, limit: int = 10) -> list[dict]:
    normalised_buyer = _l2_normalise(context.buyer_vector)
    scored = []

    for candidate in context.flat_candidates:
        normalised_flat = _l2_normalise(candidate.flat_vector)
        distance = _euclidean_distance(normalised_buyer, normalised_flat)
        score = 1.0 / (1.0 + distance)
        reason = "Ranks flats by inverse Euclidean distance after L2-normalizing the buyer and flat vectors."
        scored.append((round(score, 6), candidate, reason))

    scored.sort(key=lambda item: item[0], reverse=True)

    return [
        candidate.to_result(MODEL_KEY, MODEL_NAME, score, rank, reason)
        for rank, (score, candidate, reason) in enumerate(scored[:limit], start=1)
    ]
