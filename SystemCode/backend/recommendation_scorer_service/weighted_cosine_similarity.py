from __future__ import annotations

import math

from input_data_for_all_models import ModelContext
from weights import (
    CRITERION_FLOOR,
    CRITERION_HAWKER,
    CRITERION_HOSPITAL,
    CRITERION_MALL,
    CRITERION_MRT,
    CRITERION_PARK,
    CRITERION_SCHOOL,
)


MODEL_KEY = "weighted_cosine"
MODEL_NAME = "weighted_cosine"

ACTIVE_WEIGHT = 1.0
INACTIVE_WEIGHT = 0.25
# λ=0.7 is the standard value from the original MMR paper (Carbonell & Goldstein, 1998)
MMR_LAMBDA = 0.8  # 0 = pure diversity, 1 = pure relevance.
_DIM_CRITERION = [
    CRITERION_FLOOR,
    CRITERION_MRT,
    CRITERION_HAWKER,
    CRITERION_MALL,
    CRITERION_PARK,
    CRITERION_SCHOOL,
    CRITERION_HOSPITAL,
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


def _cosine_sim(a: list[float], b: list[float]) -> float:
    d = _dot(a, b)
    na = math.sqrt(_dot(a, a))
    nb = math.sqrt(_dot(b, b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return d / (na * nb)


def _mmr_select(
    relevance_scores: list[float],
    weighted_vecs: list[list[float]],
    limit: int,
    lam: float,
) -> list[int]:
    """Select indices via Maximal Marginal Relevance.

    MMR(d) = λ · relevance(d) − (1−λ) · max_sim(d, selected)
    """
    n = len(relevance_scores)
    if n == 0:
        return []

    selected: list[int] = []
    remaining = set(range(n))

    # Pick the most relevant candidate first
    best = max(remaining, key=lambda i: relevance_scores[i])
    selected.append(best)
    remaining.discard(best)

    while len(selected) < limit and remaining:
        best_mmr = -float("inf")
        best_idx = -1

        for i in remaining:
            max_sim_to_selected = max(
                _cosine_sim(weighted_vecs[i], weighted_vecs[j])
                for j in selected
            )
            mmr = lam * relevance_scores[i] - (1.0 - lam) * max_sim_to_selected
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i

        selected.append(best_idx)
        remaining.discard(best_idx)

    return selected


_MMR_POOL_SIZE = 200  # MMR only re-ranks the top-N by relevance for performance


def recommend(context: ModelContext, limit: int = 10) -> list[dict]:
    normalised_buyer = _l2_normalise(context.buyer_vector)
    weight_vector = _build_weight_vector(context.active_criteria)
    weighted_buyer = _l2_normalise(_apply_weights(normalised_buyer, weight_vector))

    relevance_scores: list[float] = []
    weighted_vecs: list[list[float]] = []
    candidates = list(context.flat_candidates)

    for candidate in candidates:
        normalised_flat = _l2_normalise(candidate.flat_vector)
        weighted_flat = _l2_normalise(_apply_weights(normalised_flat, weight_vector))
        score = max(0.0, min(1.0, _dot(weighted_buyer, weighted_flat)))
        relevance_scores.append(score)
        weighted_vecs.append(weighted_flat)

    # Pre-sort by relevance, apply MMR only to the top pool for performance.
    # Without this, MMR on thousands of candidates is O(n³) and causes timeouts.
    pool_size = min(_MMR_POOL_SIZE, len(candidates))
    sorted_indices = sorted(range(len(candidates)), key=lambda i: relevance_scores[i], reverse=True)
    pool_indices = sorted_indices[:pool_size]

    pool_scores = [relevance_scores[i] for i in pool_indices]
    pool_vecs = [weighted_vecs[i] for i in pool_indices]

    mmr_limit = min(limit, pool_size)
    selected_pool_positions = _mmr_select(pool_scores, pool_vecs, mmr_limit, MMR_LAMBDA)

    # Map pool-local indices back to original candidate indices
    selected_indices = [pool_indices[p] for p in selected_pool_positions]

    # Append remaining candidates (outside the MMR pool) sorted by relevance
    selected_set = set(selected_indices)
    for i in sorted_indices:
        if len(selected_indices) >= limit:
            break
        if i not in selected_set:
            selected_indices.append(i)
            selected_set.add(i)

    reason = (
        "Uses weighted cosine similarity with MMR re-ranking for diversity, giving full weight to active "
        "criteria and reduced weight to the rest."
    )

    return [
        candidates[idx].to_result(
            MODEL_KEY, MODEL_NAME, round(relevance_scores[idx], 6), rank, reason,
        )
        for rank, idx in enumerate(selected_indices[:limit], start=1)
    ]
