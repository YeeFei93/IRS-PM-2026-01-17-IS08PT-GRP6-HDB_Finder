from __future__ import annotations

import math

from input_data_for_all_models import ModelContext
from weights import CRITERION_AMENITY, CRITERION_FLAT


MODEL_KEY = "weighted_cosine"
MODEL_NAME = "weighted_cosine"

ACTIVE_WEIGHT = 1.0
INACTIVE_WEIGHT = 0.25
_DIM_CRITERION = [
    CRITERION_FLAT,
    CRITERION_AMENITY,
    CRITERION_AMENITY,
    CRITERION_AMENITY,
    CRITERION_AMENITY,
    CRITERION_AMENITY,
    CRITERION_AMENITY,
]


def _l2_normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def _apply_weights(vector: list[float], weight_vector: list[float]) -> list[float]:
    return [value * weight for value, weight in zip(vector, weight_vector)]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(a_val * b_val for a_val, b_val in zip(a, b))


def _build_weight_vector(active_criteria: list[str]) -> list[float]:
    active_set = set(active_criteria)
    return [
        ACTIVE_WEIGHT if criterion in active_set else INACTIVE_WEIGHT
        for criterion in _DIM_CRITERION
    ]


def recommend(context: ModelContext, limit: int = 10) -> list[dict]:
    normalised_buyer = _l2_normalise(context.buyer_vector)
    weight_vector = _build_weight_vector(context.active_criteria)
    weighted_buyer = _l2_normalise(_apply_weights(normalised_buyer, weight_vector))
    scored = []

    for candidate in context.flat_candidates:
        normalised_flat = _l2_normalise(candidate.flat_vector)
        weighted_flat = _l2_normalise(_apply_weights(normalised_flat, weight_vector))
        score = max(0.0, min(1.0, _dot(weighted_buyer, weighted_flat)))
        reason = (
            "Uses the shared buyer and flat vectors after L2 normalization, then applies the same active-criteria "
            "dimension weights as the main recommender before weighted cosine scoring."
        )
        scored.append((round(score, 6), candidate, reason))

    scored.sort(key=lambda item: item[0], reverse=True)

    return [
        candidate.to_result(MODEL_KEY, MODEL_NAME, score, rank, reason)
        for rank, (score, candidate, reason) in enumerate(scored[:limit], start=1)
    ]
