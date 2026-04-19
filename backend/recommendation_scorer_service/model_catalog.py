from __future__ import annotations

from typing import Final


MODEL_CONFIGS: Final[tuple[dict[str, str], ...]] = (
    {"key": "euclidean_distance", "label": "Euclidean Distance"},
    {"key": "weighted_cosine", "label": "Weighted Cosine"},
    {"key": "knn_cosine_similarity", "label": "KNN Cosine Similarity"},
)

MODEL_KEYS: Final[tuple[str, ...]] = tuple(item["key"] for item in MODEL_CONFIGS)
MODEL_LABELS: Final[dict[str, str]] = {
    item["key"]: item["label"]
    for item in MODEL_CONFIGS
}

_MODEL_ALIASES: Final[dict[str, str]] = {
    "euclidean_distance": "euclidean_distance",
    "weighted_cosine": "weighted_cosine",
    "weighted_cosine_similarity": "weighted_cosine",
    "knn": "knn_cosine_similarity",
    "knn_cosine": "knn_cosine_similarity",
    "knn_cosine_recommender": "knn_cosine_similarity",
    "knn_cosine_similarity": "knn_cosine_similarity",
    "euclidean": "euclidean_distance",
}


def normalise_model_key(value: str | None) -> str | None:
    if value is None:
        return None

    clean = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if not clean:
        return None

    return _MODEL_ALIASES.get(clean, clean if clean in MODEL_LABELS else None)
