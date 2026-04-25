from __future__ import annotations

import math

from input_data_for_all_models import ModelContext


MODEL_KEY = "cosine_similarity"
MODEL_NAME = "cosine_similarity"


def _l2_normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(a_val * b_val for a_val, b_val in zip(a, b))


def recommend(context: ModelContext, limit: int = 10) -> list[dict]:
    normalised_buyer = _l2_normalise(context.buyer_vector)
    scored = []

    for candidate in context.flat_candidates:
        normalised_flat = _l2_normalise(candidate.flat_vector)
        score = max(0.0, min(1.0, _dot(normalised_buyer, normalised_flat)))
        reason = (
            "Uses the shared buyer and flat vectors after L2 normalization, then applies plain cosine similarity "
            "without active-criteria weights."
        )
        scored.append((round(score, 6), candidate, reason))

    scored.sort(key=lambda item: item[0], reverse=True)

    return [
        candidate.to_result(MODEL_KEY, MODEL_NAME, score, rank, reason)
        for rank, (score, candidate, reason) in enumerate(scored[:limit], start=1)
    ]
