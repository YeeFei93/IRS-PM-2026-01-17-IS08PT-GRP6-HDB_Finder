from __future__ import annotations

import math

from input_data_for_all_models import ModelContext


MODEL_KEY = "knn_cosine_recommender"
MODEL_NAME = "knn_cosine_recommender"


def _l2_normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(a_val * b_val for a_val, b_val in zip(a, b))


def recommend(context: ModelContext, limit: int = 10) -> list[dict]:
    if not context.flat_candidates:
        return []

    normalised_buyer = _l2_normalise(context.buyer_vector)
    flat_vectors = [_l2_normalise(candidate.flat_vector) for candidate in context.flat_candidates]
    scored = []

    for idx, candidate in enumerate(context.flat_candidates):
        normalised_flat = flat_vectors[idx]
        buyer_similarity = max(0.0, min(1.0, _dot(normalised_buyer, normalised_flat)))
        neighbour_scores = []

        for other_idx, other_vector in enumerate(flat_vectors):
            if other_idx == idx:
                continue
            neighbour_scores.append(max(0.0, min(1.0, _dot(normalised_flat, other_vector))))

        neighbour_scores.sort(reverse=True)
        top_neighbours = neighbour_scores[:5]
        neighbour_mean = sum(top_neighbours) / len(top_neighbours) if top_neighbours else buyer_similarity
        score = round((buyer_similarity * 0.7) + (neighbour_mean * 0.3), 6)
        reason = (
            "Uses L2-normalized buyer and flat vectors for the cosine buyer match, then smooths the score with the "
            "top 5 cosine-nearest normalized flat neighbours."
        )
        scored.append((score, candidate, reason))

    scored.sort(key=lambda item: item[0], reverse=True)

    return [
        candidate.to_result(MODEL_KEY, MODEL_NAME, score, rank, reason)
        for rank, (score, candidate, reason) in enumerate(scored[:limit], start=1)
    ]
