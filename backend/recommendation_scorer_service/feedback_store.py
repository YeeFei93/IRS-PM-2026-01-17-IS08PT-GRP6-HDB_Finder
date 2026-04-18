from __future__ import annotations

import math
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from typing import Any

_SERVICE_ROOT = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.abspath(os.path.join(_SERVICE_ROOT, ".."))

for _path in (_SERVICE_ROOT, _BACKEND_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from amenity_proximity_service.utils.db_connector import DbConnector

from recommendation_scorer_service.model_catalog import (
    MODEL_CONFIGS,
    MODEL_KEYS,
    MODEL_LABELS,
    normalise_model_key,
)


USER_RATINGS_TABLE = "user_ratings"
MODEL_EVALUATION_TABLE = "model_evaluation"
_INTERACTION_KINDS = {"view", "like"}
_UNSEEN_MODEL_BONUS = 2


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_tables_with_db(db: DbConnector) -> None:
    db.cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {USER_RATINGS_TABLE} (
            flat_id VARCHAR(255) NOT NULL,
            recommendation VARCHAR(64) NOT NULL,
            user_like_count INT NOT NULL DEFAULT 0,
            user_view_count INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (flat_id, recommendation),
            INDEX idx_user_ratings_recommendation (recommendation)
        )
        """
    )
    db.cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MODEL_EVALUATION_TABLE} (
            recommendation VARCHAR(64) NOT NULL PRIMARY KEY,
            precision_score DECIMAL(10, 6) NOT NULL DEFAULT 0,
            recall_score DECIMAL(10, 6) NOT NULL DEFAULT 0,
            ndcg_score DECIMAL(10, 6) NOT NULL DEFAULT 0,
            coverage_score DECIMAL(10, 6) NOT NULL DEFAULT 0,
            diversity_score DECIMAL(10, 6) NOT NULL DEFAULT 0,
            interacted_flats INT NOT NULL DEFAULT 0,
            relevant_flats INT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
        )
        """
    )


def ensure_feedback_tables() -> None:
    db = DbConnector()
    try:
        _ensure_tables_with_db(db)
        db.Commit()
    finally:
        db.Close()


def _interaction_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in raw_rows
        if int(row.get("user_view_count") or 0) > 0 or int(row.get("user_like_count") or 0) > 0
    ]


def _relevant_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in raw_rows
        if int(row.get("user_like_count") or 0) > 0
    ]


def _dcg(rows: list[dict[str, Any]]) -> float:
    total = 0.0
    for index, row in enumerate(rows, start=1):
        gain = int(row.get("user_like_count") or 0)
        if gain <= 0:
            continue
        total += ((2 ** gain) - 1) / math.log2(index + 1)
    return total


def _diversity_score(rows: list[dict[str, Any]], flat_meta: dict[str, dict[str, Any]]) -> float:
    if len(rows) < 2:
        return 0.0

    dissimilarity_sum = 0.0
    pair_count = 0

    for left, right in combinations(rows, 2):
        pair_count += 1
        left_meta = flat_meta.get(str(left["flat_id"]), {})
        right_meta = flat_meta.get(str(right["flat_id"]), {})

        if not left_meta or not right_meta:
            dissimilarity_sum += 0.5
            continue

        estate_same = left_meta.get("estate") == right_meta.get("estate")
        flat_type_same = left_meta.get("flat_type") == right_meta.get("flat_type")
        similarity = (0.7 if estate_same else 0.0) + (0.3 if flat_type_same else 0.0)
        dissimilarity_sum += max(0.0, 1.0 - similarity)

    return round(dissimilarity_sum / pair_count, 6) if pair_count else 0.0


def calculate_model_evaluations(
    raw_rows: list[dict[str, Any]],
    flat_meta: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    flat_meta = flat_meta or {}
    interacted_rows = _interaction_rows(raw_rows)
    relevant_rows = _relevant_rows(interacted_rows)

    total_interacted = len(interacted_rows)
    total_relevant = len(relevant_rows)

    rows_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in interacted_rows:
        model_key = normalise_model_key(row.get("recommendation"))
        if model_key in MODEL_KEYS:
            rows_by_model[model_key].append(row)

    metrics: list[dict[str, Any]] = []
    for config in MODEL_CONFIGS:
        model_key = config["key"]
        model_rows = rows_by_model.get(model_key, [])
        relevant_for_model = _relevant_rows(model_rows)

        observed_rank = sorted(
            model_rows,
            key=lambda row: (
                int(row.get("user_view_count") or 0),
                int(row.get("user_like_count") or 0),
            ),
            reverse=True,
        )
        ideal_rank = sorted(
            model_rows,
            key=lambda row: int(row.get("user_like_count") or 0),
            reverse=True,
        )

        dcg = _dcg(observed_rank)
        ideal_dcg = _dcg(ideal_rank)
        ndcg = round(dcg / ideal_dcg, 6) if ideal_dcg else 0.0

        interacted_count = len(model_rows)
        relevant_count = len(relevant_for_model)
        precision = round(relevant_count / interacted_count, 6) if interacted_count else 0.0
        recall = round(relevant_count / total_relevant, 6) if total_relevant else 0.0
        coverage = round(interacted_count / total_interacted, 6) if total_interacted else 0.0
        diversity = _diversity_score(model_rows, flat_meta)

        metrics.append(
            {
                "recommendation": model_key,
                "recommendation_label": MODEL_LABELS[model_key],
                "precision_score": precision,
                "recall_score": recall,
                "ndcg_score": ndcg,
                "coverage_score": coverage,
                "diversity_score": diversity,
                "interacted_flats": interacted_count,
                "relevant_flats": relevant_count,
            }
        )

    return metrics


def _load_flat_meta(db: DbConnector, flat_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not flat_ids:
        return {}

    placeholders = ", ".join(["%s"] * len(flat_ids))
    db.cursor.execute(
        f"""
        SELECT resale_flat_id AS flat_id, estate, flat_type
        FROM resale_flats
        WHERE resale_flat_id IN ({placeholders})
        """,
        tuple(flat_ids),
    )

    return {
        str(row["flat_id"]): {
            "estate": row.get("estate"),
            "flat_type": row.get("flat_type"),
        }
        for row in db.cursor.fetchall()
    }


def refresh_model_evaluations(db: DbConnector | None = None) -> list[dict[str, Any]]:
    close_db = db is None
    if close_db:
        db = DbConnector()

    try:
        _ensure_tables_with_db(db)
        db.cursor.execute(
            f"""
            SELECT flat_id, recommendation, user_like_count, user_view_count
            FROM {USER_RATINGS_TABLE}
            """
        )
        raw_rows = [dict(row) for row in db.cursor.fetchall()]
        flat_meta = _load_flat_meta(db, [str(row["flat_id"]) for row in raw_rows])
        metrics = calculate_model_evaluations(raw_rows, flat_meta)

        for metric in metrics:
            db.cursor.execute(
                f"""
                INSERT INTO {MODEL_EVALUATION_TABLE} (
                    recommendation,
                    precision_score,
                    recall_score,
                    ndcg_score,
                    coverage_score,
                    diversity_score,
                    interacted_flats,
                    relevant_flats
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    precision_score = VALUES(precision_score),
                    recall_score = VALUES(recall_score),
                    ndcg_score = VALUES(ndcg_score),
                    coverage_score = VALUES(coverage_score),
                    diversity_score = VALUES(diversity_score),
                    interacted_flats = VALUES(interacted_flats),
                    relevant_flats = VALUES(relevant_flats)
                """,
                (
                    metric["recommendation"],
                    metric["precision_score"],
                    metric["recall_score"],
                    metric["ndcg_score"],
                    metric["coverage_score"],
                    metric["diversity_score"],
                    metric["interacted_flats"],
                    metric["relevant_flats"],
                ),
            )

        db.Commit()
        return metrics
    finally:
        if close_db:
            db.Close()


def get_model_evaluations() -> list[dict[str, Any]]:
    db = DbConnector()
    try:
        _ensure_tables_with_db(db)
        db.cursor.execute(
            f"""
            SELECT recommendation, precision_score, recall_score, ndcg_score,
                   coverage_score, diversity_score, interacted_flats, relevant_flats,
                   updated_at
            FROM {MODEL_EVALUATION_TABLE}
            ORDER BY recommendation
            """
        )
        rows = [dict(row) for row in db.cursor.fetchall()]
        if not rows:
            return refresh_model_evaluations(db)
        for row in rows:
            row["recommendation_label"] = MODEL_LABELS.get(row["recommendation"], row["recommendation"])
        return rows
    finally:
        db.Close()


def get_model_selection_snapshot() -> dict[str, dict[str, Any]]:
    db = DbConnector()
    try:
        _ensure_tables_with_db(db)
        db.cursor.execute(
            f"""
            SELECT recommendation,
                   COALESCE(SUM(user_like_count), 0) AS total_likes,
                   COALESCE(SUM(user_view_count), 0) AS total_views
            FROM {USER_RATINGS_TABLE}
            GROUP BY recommendation
            """
        )
        interaction_totals = {}
        for row in db.cursor.fetchall():
            model_key = normalise_model_key(row.get("recommendation"))
            if model_key not in MODEL_KEYS:
                continue
            interaction_totals[model_key] = {
                "likes": int(row.get("total_likes") or 0),
                "views": int(row.get("total_views") or 0),
            }
    finally:
        db.Close()

    weights = {}
    for model_key in MODEL_KEYS:
        totals = interaction_totals.get(model_key, {})
        likes = max(int(totals.get("likes") or 0), 0)
        views = max(int(totals.get("views") or 0), 0)

        # Keep likes as the main signal, but give unseen models a short-lived
        # exploration boost so adaptive selection doesn't get stuck on the
        # first model that happened to receive feedback.
        weights[model_key] = likes + 1 + (_UNSEEN_MODEL_BONUS if views == 0 else 0)

    weight_total = sum(weights.values()) or len(MODEL_KEYS)

    return {
        model_key: {
            "key": model_key,
            "label": MODEL_LABELS[model_key],
            "likes": interaction_totals.get(model_key, {}).get("likes", 0),
            "views": interaction_totals.get(model_key, {}).get("views", 0),
            "weight": weights[model_key],
            "probability": round(weights[model_key] / weight_total, 6),
        }
        for model_key in MODEL_KEYS
    }


def choose_recommendation_model(requested_model: str | None = None) -> dict[str, Any]:
    snapshot = get_model_selection_snapshot()
    manual_key = normalise_model_key(requested_model)

    if manual_key in snapshot:
        choice = dict(snapshot[manual_key])
        choice["selection_method"] = "manual"
        choice["selected_at"] = _utc_now_iso()
        return choice

    chosen_key = random.choices(
        population=list(snapshot.keys()),
        weights=[snapshot[key]["weight"] for key in snapshot],
        k=1,
    )[0]
    choice = dict(snapshot[chosen_key])
    choice["selection_method"] = "adaptive"
    choice["selected_at"] = _utc_now_iso()
    return choice


def record_feedback(flat_id: str, recommendation: str, event: str) -> dict[str, Any]:
    model_key = normalise_model_key(recommendation)
    if not flat_id:
        raise ValueError("flat_id is required")
    if model_key not in MODEL_KEYS:
        raise ValueError("recommendation model is invalid")
    if event not in _INTERACTION_KINDS:
        raise ValueError("event must be 'view' or 'like'")

    view_inc = 1 if event == "view" else 0
    like_inc = 1 if event == "like" else 0

    db = DbConnector()
    try:
        _ensure_tables_with_db(db)
        db.cursor.execute(
            f"""
            INSERT INTO {USER_RATINGS_TABLE} (
                flat_id, recommendation, user_like_count, user_view_count
            ) VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                user_like_count = user_like_count + VALUES(user_like_count),
                user_view_count = user_view_count + VALUES(user_view_count)
            """,
            (str(flat_id), model_key, like_inc, view_inc),
        )

        db.cursor.execute(
            f"""
            SELECT flat_id, recommendation, user_like_count, user_view_count
            FROM {USER_RATINGS_TABLE}
            WHERE flat_id = %s AND recommendation = %s
            """,
            (str(flat_id), model_key),
        )
        row = dict(db.cursor.fetchone() or {})
        metrics = refresh_model_evaluations(db)
        db.Commit()

        return {
            "flat_id": str(flat_id),
            "recommendation": model_key,
            "recommendation_label": MODEL_LABELS[model_key],
            "event": event,
            "user_like_count": int(row.get("user_like_count") or 0),
            "user_view_count": int(row.get("user_view_count") or 0),
            "model_evaluation": metrics,
        }
    finally:
        db.Close()
