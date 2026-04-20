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
_INTERACTION_KINDS = {
    "view",
    "like",
    "favorite",
    "favourite",
    "unlike",
    "unfavorite",
    "unfavourite",
}
_SELECTION_PRIOR_FAVOURITES = 1
_SELECTION_PRIOR_VIEWS = 2


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _table_columns(db: DbConnector, table_name: str) -> set[str]:
    db.cursor.execute(f"SHOW COLUMNS FROM {table_name}")
    return {str(row.get("Field") or "") for row in db.cursor.fetchall() or []}


def _ensure_column(
    db: DbConnector,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    if column_name in _table_columns(db, table_name):
        return
    db.cursor.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    )


def _ensure_tables_with_db(db: DbConnector) -> None:
    db.cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {USER_RATINGS_TABLE} (
            resale_flat_id VARCHAR(255) NOT NULL,
            recommendation VARCHAR(64) NOT NULL,
            user_like_count INT NOT NULL DEFAULT 0,
            user_view_count INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (resale_flat_id, recommendation),
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
            viewed_flats INT NOT NULL DEFAULT 0,
            favourited_flats INT NOT NULL DEFAULT 0,
            favourite_rate DECIMAL(10, 6) NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
        )
        """
    )
    _ensure_column(
        db,
        MODEL_EVALUATION_TABLE,
        "viewed_flats",
        "INT NOT NULL DEFAULT 0",
    )
    _ensure_column(
        db,
        MODEL_EVALUATION_TABLE,
        "favourited_flats",
        "INT NOT NULL DEFAULT 0",
    )
    _ensure_column(
        db,
        MODEL_EVALUATION_TABLE,
        "favourite_rate",
        "DECIMAL(10, 6) NOT NULL DEFAULT 0",
    )

    # Older versions stored growing counters. Normalize them into 0/1 state
    # so repeated clicks do not keep increasing the model signal.
    db.cursor.execute(
        f"""
        UPDATE {USER_RATINGS_TABLE}
        SET
            user_like_count = CASE WHEN user_like_count > 0 THEN 1 ELSE 0 END,
            user_view_count = CASE
                WHEN user_view_count > 0 OR user_like_count > 0 THEN 1
                ELSE 0
            END
        WHERE user_like_count NOT IN (0, 1)
           OR user_view_count NOT IN (0, 1)
           OR (user_like_count > 0 AND user_view_count = 0)
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


def _row_resale_flat_id(row: dict[str, Any]) -> str:
    return str(row.get("resale_flat_id") or "")


def _diversity_score(rows: list[dict[str, Any]], flat_meta: dict[str, dict[str, Any]]) -> float:
    if len(rows) < 2:
        return 0.0

    dissimilarity_sum = 0.0
    pair_count = 0

    for left, right in combinations(rows, 2):
        pair_count += 1
        left_meta = flat_meta.get(_row_resale_flat_id(left), {})
        right_meta = flat_meta.get(_row_resale_flat_id(right), {})

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
                int(row.get("user_like_count") or 0),
                int(row.get("user_view_count") or 0),
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

        viewed_count = len(model_rows)
        favourited_count = len(relevant_for_model)
        favourite_rate = round(favourited_count / viewed_count, 6) if viewed_count else 0.0
        precision = favourite_rate
        recall = round(favourited_count / total_relevant, 6) if total_relevant else 0.0
        coverage = round(viewed_count / total_interacted, 6) if total_interacted else 0.0
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
                "interacted_flats": viewed_count,
                "relevant_flats": favourited_count,
                "viewed_flats": viewed_count,
                "favourited_flats": favourited_count,
                "favourite_rate": favourite_rate,
            }
        )

    return metrics


def _load_flat_meta(db: DbConnector, resale_flat_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not resale_flat_ids:
        return {}

    placeholders = ", ".join(["%s"] * len(resale_flat_ids))
    db.cursor.execute(
        f"""
        SELECT resale_flat_id, estate, flat_type
        FROM resale_flats
        WHERE resale_flat_id IN ({placeholders})
        """,
        tuple(resale_flat_ids),
    )

    return {
        str(row["resale_flat_id"]): {
            "estate": row.get("estate"),
            "flat_type": row.get("flat_type"),
        }
        for row in db.cursor.fetchall() or []
    }


def refresh_model_evaluations(db: DbConnector | None = None) -> list[dict[str, Any]]:
    close_db = db is None
    if close_db:
        db = DbConnector()

    try:
        _ensure_tables_with_db(db)
        db.cursor.execute(
            f"""
            SELECT resale_flat_id, recommendation, user_like_count, user_view_count
            FROM {USER_RATINGS_TABLE}
            """
        )
        raw_rows = [dict(row) for row in db.cursor.fetchall() or []]
        flat_meta = _load_flat_meta(db, [_row_resale_flat_id(row) for row in raw_rows])
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
                    relevant_flats,
                    viewed_flats,
                    favourited_flats,
                    favourite_rate
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    precision_score = VALUES(precision_score),
                    recall_score = VALUES(recall_score),
                    ndcg_score = VALUES(ndcg_score),
                    coverage_score = VALUES(coverage_score),
                    diversity_score = VALUES(diversity_score),
                    interacted_flats = VALUES(interacted_flats),
                    relevant_flats = VALUES(relevant_flats),
                    viewed_flats = VALUES(viewed_flats),
                    favourited_flats = VALUES(favourited_flats),
                    favourite_rate = VALUES(favourite_rate)
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
                    metric["viewed_flats"],
                    metric["favourited_flats"],
                    metric["favourite_rate"],
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
                   viewed_flats, favourited_flats, favourite_rate, updated_at
            FROM {MODEL_EVALUATION_TABLE}
            ORDER BY recommendation
            """
        )
        rows = [dict(row) for row in db.cursor.fetchall() or []]
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
        for row in db.cursor.fetchall() or []:
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
    favourite_rates = {}
    for model_key in MODEL_KEYS:
        totals = interaction_totals.get(model_key, {})
        likes = max(int(totals.get("likes") or 0), 0)
        views = max(int(totals.get("views") or 0), 0)

        raw_rate = round(likes / views, 6) if views else 0.0
        smoothed_rate = (likes + _SELECTION_PRIOR_FAVOURITES) / (views + _SELECTION_PRIOR_VIEWS)

        favourite_rates[model_key] = raw_rate
        weights[model_key] = smoothed_rate

    weight_total = sum(weights.values()) or float(len(MODEL_KEYS))

    return {
        model_key: {
            "key": model_key,
            "label": MODEL_LABELS[model_key],
            "likes": interaction_totals.get(model_key, {}).get("likes", 0),
            "views": interaction_totals.get(model_key, {}).get("views", 0),
            "favourited_flats": interaction_totals.get(model_key, {}).get("likes", 0),
            "viewed_flats": interaction_totals.get(model_key, {}).get("views", 0),
            "favourite_rate": favourite_rates[model_key],
            "weight": round(weights[model_key], 6),
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


def _fetch_feedback_rows(
    db: DbConnector,
    resale_flat_id: str,
    recommendation: str | None = None,
) -> list[dict[str, Any]]:
    if recommendation:
        db.cursor.execute(
            f"""
            SELECT resale_flat_id, recommendation, user_like_count, user_view_count
            FROM {USER_RATINGS_TABLE}
            WHERE resale_flat_id = %s AND recommendation = %s
            """,
            (str(resale_flat_id), recommendation),
        )
    else:
        db.cursor.execute(
            f"""
            SELECT resale_flat_id, recommendation, user_like_count, user_view_count
            FROM {USER_RATINGS_TABLE}
            WHERE resale_flat_id = %s
            """,
            (str(resale_flat_id),),
        )
    return [dict(row) for row in db.cursor.fetchall() or []]


def _flag_value(value: bool | None, default: int) -> int:
    if value is None:
        return int(default)
    return 1 if bool(value) else 0


def _resolve_feedback_state(
    row: dict[str, Any],
    viewed: bool | None,
    favourite: bool | None,
) -> tuple[int, int]:
    next_viewed = _flag_value(viewed, int(row.get("user_view_count") or 0))
    next_favourite = _flag_value(favourite, int(row.get("user_like_count") or 0))
    if next_favourite:
        next_viewed = 1
    return next_viewed, next_favourite


def _write_feedback_row(
    db: DbConnector,
    resale_flat_id: str,
    recommendation: str,
    viewed_flag: int,
    favourite_flag: int,
) -> dict[str, Any]:
    if not viewed_flag and not favourite_flag:
        db.cursor.execute(
            f"""
            DELETE FROM {USER_RATINGS_TABLE}
            WHERE resale_flat_id = %s AND recommendation = %s
            """,
            (str(resale_flat_id), recommendation),
        )
        return {
            "resale_flat_id": str(resale_flat_id),
            "recommendation": recommendation,
            "user_like_count": 0,
            "user_view_count": 0,
            "user_favourite": False,
            "user_viewed": False,
        }

    db.cursor.execute(
        f"""
        INSERT INTO {USER_RATINGS_TABLE} (
            resale_flat_id, recommendation, user_like_count, user_view_count
        ) VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            user_like_count = VALUES(user_like_count),
            user_view_count = VALUES(user_view_count)
        """,
        (str(resale_flat_id), recommendation, int(favourite_flag), int(viewed_flag)),
    )
    rows = _fetch_feedback_rows(db, resale_flat_id, recommendation)
    row = rows[0] if rows else {
        "resale_flat_id": str(resale_flat_id),
        "recommendation": recommendation,
        "user_like_count": int(favourite_flag),
        "user_view_count": int(viewed_flag),
    }
    row["user_favourite"] = int(row.get("user_like_count") or 0) > 0
    row["user_viewed"] = int(row.get("user_view_count") or 0) > 0
    return row


def set_feedback_state(
    resale_flat_id: str,
    recommendation: str | None = None,
    viewed: bool | None = None,
    favourite: bool | None = None,
) -> dict[str, Any]:
    resale_flat_id = str(resale_flat_id or "").strip()
    model_key = normalise_model_key(recommendation) if recommendation else None

    if not resale_flat_id:
        raise ValueError("resale_flat_id is required")
    if recommendation and model_key not in MODEL_KEYS:
        raise ValueError("recommendation model is invalid")
    if viewed is None and favourite is None:
        raise ValueError("viewed or favourite must be provided")

    db = DbConnector()
    try:
        _ensure_tables_with_db(db)

        updated_rows: list[dict[str, Any]] = []
        if model_key:
            existing_rows = _fetch_feedback_rows(db, resale_flat_id, model_key)
            current_row = existing_rows[0] if existing_rows else {
                "resale_flat_id": resale_flat_id,
                "recommendation": model_key,
                "user_like_count": 0,
                "user_view_count": 0,
            }
            next_viewed, next_favourite = _resolve_feedback_state(current_row, viewed, favourite)
            updated_rows.append(
                _write_feedback_row(db, resale_flat_id, model_key, next_viewed, next_favourite)
            )
        else:
            for row in _fetch_feedback_rows(db, resale_flat_id):
                row_model = normalise_model_key(row.get("recommendation"))
                if row_model not in MODEL_KEYS:
                    continue
                next_viewed, next_favourite = _resolve_feedback_state(row, viewed, favourite)
                updated_rows.append(
                    _write_feedback_row(db, resale_flat_id, row_model, next_viewed, next_favourite)
                )

        metrics = refresh_model_evaluations(db)
        summary_row = updated_rows[0] if len(updated_rows) == 1 else None

        return {
            "resale_flat_id": resale_flat_id,
            "recommendation": summary_row.get("recommendation") if summary_row else model_key,
            "recommendation_label": MODEL_LABELS.get(
                summary_row.get("recommendation") if summary_row else model_key,
                summary_row.get("recommendation") if summary_row else model_key,
            ),
            "user_like_count": int(summary_row.get("user_like_count") or 0) if summary_row else None,
            "user_view_count": int(summary_row.get("user_view_count") or 0) if summary_row else None,
            "user_favourite": bool(summary_row.get("user_favourite")) if summary_row else None,
            "user_viewed": bool(summary_row.get("user_viewed")) if summary_row else None,
            "updated_rows": updated_rows,
            "model_evaluation": metrics,
        }
    finally:
        db.Close()


def record_feedback(resale_flat_id: str, recommendation: str, event: str) -> dict[str, Any]:
    event = str(event or "").strip().lower()
    if event not in _INTERACTION_KINDS:
        raise ValueError(
            "event must be 'view', 'like', 'favorite', 'favourite', 'unlike', 'unfavorite', or 'unfavourite'"
        )

    if event == "view":
        result = set_feedback_state(
            resale_flat_id=resale_flat_id,
            recommendation=recommendation,
            viewed=True,
        )
    elif event in {"like", "favorite", "favourite"}:
        result = set_feedback_state(
            resale_flat_id=resale_flat_id,
            recommendation=recommendation,
            viewed=True,
            favourite=True,
        )
    else:
        result = set_feedback_state(
            resale_flat_id=resale_flat_id,
            recommendation=recommendation,
            viewed=True,
            favourite=False,
        )

    result["event"] = event
    return result
