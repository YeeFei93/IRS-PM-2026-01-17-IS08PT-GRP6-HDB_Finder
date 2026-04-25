"""
recommendation_scorer_service/recommender.py
===================
Runs one of three flat-level recommenders, selected adaptively from
historical user favourite/view behaviour:
  1. Euclidean Distance
  2. Weighted Cosine
  3. KNN Cosine Similarity

The selected model scores every qualifying flat, then the results are grouped
back into estate-level recommendations so the existing frontend can keep its
estate-first workflow while each flat carries the underlying model metadata.
"""

from __future__ import annotations

import os
import sys
from collections import Counter

_SERVICE_ROOT = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.abspath(os.path.join(_SERVICE_ROOT, ".."))

for _path in (_SERVICE_ROOT, _BACKEND_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from euclidean_distance_recommender import recommend as recommend_euclidean
from input_data_for_all_models import build_model_context
from knn_recommender import recommend as recommend_knn
from weighted_cosine_similarity import recommend as recommend_weighted

from recommendation_scorer_service.feedback_store import (
    choose_recommendation_model,
    get_model_selection_snapshot,
)
from recommendation_scorer_service.model_catalog import MODEL_LABELS, MODEL_KEYS


_TOP_FLATS_GLOBAL = 50
_STRONG_MATCH_THRESHOLD = 0.75

_MODEL_RUNNERS = {
    "euclidean_distance": recommend_euclidean,
    "weighted_cosine": recommend_weighted,
    "knn_cosine_similarity": recommend_knn,
}


def _run_ranker(context, model_key: str) -> list[dict]:
    runner = _MODEL_RUNNERS[model_key]
    items = runner(context, limit=len(context.flat_candidates))
    label = MODEL_LABELS[model_key]

    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
        item["model_key"] = model_key
        item["model_name"] = label
        item["recommendation_model"] = model_key
        item["recommendation_model_label"] = label

    return items


def _group_into_estates(context, ranked_items: list[dict], selection: dict) -> list[dict]:
    if not ranked_items:
        return []

    ranked_items = ranked_items[:_TOP_FLATS_GLOBAL]

    candidate_lookup = {
        candidate.resale_flat_id: candidate
        for candidate in context.flat_candidates
    }
    qualifying_counts = Counter(candidate.estate for candidate in context.flat_candidates)
    estate_map: dict[str, dict] = {}

    for item in ranked_items:
        candidate = candidate_lookup.get(item["resale_flat_id"])
        if candidate is None:
            continue

        town = candidate.estate
        estate_entry = estate_map.get(town)
        if estate_entry is None:
            estate_entry = {
                "town": town,
                "ftype": context.profile.get("ftype", "4 ROOM"),
                "price_data": dict(candidate.estate_price_data),
                "amenities": dict(candidate.amenities),
                "score": item["score"],
                "active_criteria": list(context.active_criteria),
                "top_flats": [],
                "qualifying_flats": int(qualifying_counts.get(town, 0)),
                "grants": context.grants,
                "effective_budget": int(round(context.effective_budget)),
                "recommendation_model": selection["key"],
                "recommendation_model_label": selection["label"],
            }
            estate_map[town] = estate_entry

        if len(estate_entry["top_flats"]) < 10:
            estate_entry["top_flats"].append(
                {
                    **item,
                    "latitude": candidate.latitude,
                    "longitude": candidate.longitude,
                }
            )

    for estate in estate_map.values():
        scores = [float(flat.get("score") or 0.0) for flat in estate["top_flats"]]
        estate["avg_score"] = round(sum(scores) / len(scores), 4) if scores else 0.0
        estate["strong_matches"] = sum(
            1 for score in scores
            if score >= _STRONG_MATCH_THRESHOLD
        )

    estate_results = sorted(
        estate_map.values(),
        key=lambda estate: (estate["avg_score"], estate["qualifying_flats"]),
        reverse=True,
    )

    price_sorted = sorted(
        estate_results,
        key=lambda estate: abs(float(estate["price_data"].get("median") or 0) - context.effective_budget),
    )
    price_rank_map = {
        estate["town"]: index
        for index, estate in enumerate(price_sorted, start=1)
    }

    popularity_sorted = sorted(
        estate_results,
        key=lambda estate: int(estate["price_data"].get("n") or 0),
        reverse=True,
    )
    popularity_rank_map = {
        estate["town"]: index
        for index, estate in enumerate(popularity_sorted, start=1)
    }

    for estate in estate_results:
        estate["baseline_price_rank"] = price_rank_map[estate["town"]]
        estate["baseline_pop_rank"] = popularity_rank_map[estate["town"]]

    return estate_results


def _response_notes(context) -> list[str]:
    notes = []
    for item in list(context.eligibility.get("notes", [])) + list(context.notes):
        if item and item not in notes:
            notes.append(item)
    return notes


def run_recommendation(profile: dict) -> dict:
    selection = choose_recommendation_model(profile.get("recommendation_model"))
    model_probabilities = get_model_selection_snapshot()
    context = build_model_context(profile)

    if not context.eligibility.get("eligible"):
        return {
            "eligible": False,
            "warnings": list(context.eligibility.get("warnings", [])),
            "notes": _response_notes(context),
            "grants": context.grants,
            "effective_budget": int(round(context.effective_budget)),
            "selected_model": selection,
            "model_probabilities": model_probabilities,
            "available_models": [
                {"key": key, "label": MODEL_LABELS[key]}
                for key in MODEL_KEYS
            ],
            "recommendations": [],
        }

    if not context.flat_candidates:
        return {
            "eligible": True,
            "warnings": list(context.eligibility.get("warnings", [])),
            "notes": _response_notes(context),
            "grants": context.grants,
            "effective_budget": int(round(context.effective_budget)),
            "selected_model": selection,
            "model_probabilities": model_probabilities,
            "available_models": [
                {"key": key, "label": MODEL_LABELS[key]}
                for key in MODEL_KEYS
            ],
            "recommendations": [],
        }

    ranked_items = _run_ranker(context, selection["key"])
    recommendations = _group_into_estates(context, ranked_items, selection)

    return {
        "eligible": True,
        "warnings": list(context.eligibility.get("warnings", [])),
        "notes": _response_notes(context),
        "grants": context.grants,
        "effective_budget": int(round(context.effective_budget)),
        "selected_model": selection,
        "model_probabilities": model_probabilities,
        "available_models": [
            {"key": key, "label": MODEL_LABELS[key]}
            for key in MODEL_KEYS
        ],
        "recommendations": recommendations,
    }
