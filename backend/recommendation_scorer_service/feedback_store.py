from __future__ import annotations

import math
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
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
RECOMMENDATION_SESSION_TABLE = "recommendation_session_feedback"
MODEL_EVALUATION_TABLE = "model_evaluation"
EVALUATION_K = 10
_INTERACTION_KINDS = {
    "view",
    "like",
    "favorite",
    "favourite",
    "unlike",
    "unfavorite",
    "unfavourite",
}


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


def _drop_column(
    db: DbConnector,
    table_name: str,
    column_name: str,
) -> None:
    if column_name not in _table_columns(db, table_name):
        return
    db.cursor.execute(
        f"ALTER TABLE {table_name} DROP COLUMN {column_name}"
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
        CREATE TABLE IF NOT EXISTS {RECOMMENDATION_SESSION_TABLE} (
            session_id VARCHAR(255) NOT NULL,
            recommendation VARCHAR(64) NOT NULL,
            resale_flat_id VARCHAR(255) NOT NULL,
            position INT NULL,
            user_like_count INT NOT NULL DEFAULT 0,
            user_view_count INT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (session_id, recommendation, resale_flat_id),
            INDEX idx_recommendation_session_feedback_recommendation (recommendation),
            INDEX idx_recommendation_session_feedback_position (
                session_id, recommendation, position
            )
        )
        """
    )
    db.cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MODEL_EVALUATION_TABLE} (
            recommendation VARCHAR(64) NOT NULL PRIMARY KEY,
            recommendation_label VARCHAR(255) NOT NULL,
            k_value INT NOT NULL DEFAULT 10,
            sessions INT NOT NULL DEFAULT 0,
            precision_at_k DECIMAL(10, 6) NOT NULL DEFAULT 0,
            recall_at_k DECIMAL(10, 6) NOT NULL DEFAULT 0,
            ndcg_at_k DECIMAL(10, 6) NOT NULL DEFAULT 0,
            viewed_flats INT NOT NULL DEFAULT 0,
            favorited_flats INT NOT NULL DEFAULT 0,
            favorite_rate DECIMAL(10, 6) NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
        )
        """
    )
    _ensure_column(
        db,
        RECOMMENDATION_SESSION_TABLE,
        "position",
        "INT NULL",
    )
    _ensure_column(
        db,
        MODEL_EVALUATION_TABLE,
        "recommendation_label",
        "VARCHAR(255) NOT NULL DEFAULT ''",
    )
    _ensure_column(
        db,
        MODEL_EVALUATION_TABLE,
        "k_value",
        "INT NOT NULL DEFAULT 10",
    )
    _ensure_column(
        db,
        MODEL_EVALUATION_TABLE,
        "sessions",
        "INT NOT NULL DEFAULT 0",
    )
    _ensure_column(
        db,
        MODEL_EVALUATION_TABLE,
        "precision_at_k",
        "DECIMAL(10, 6) NOT NULL DEFAULT 0",
    )
    _ensure_column(
        db,
        MODEL_EVALUATION_TABLE,
        "recall_at_k",
        "DECIMAL(10, 6) NOT NULL DEFAULT 0",
    )
    _ensure_column(
        db,
        MODEL_EVALUATION_TABLE,
        "ndcg_at_k",
        "DECIMAL(10, 6) NOT NULL DEFAULT 0",
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
        "favorited_flats",
        "INT NOT NULL DEFAULT 0",
    )
    _ensure_column(
        db,
        MODEL_EVALUATION_TABLE,
        "favorite_rate",
        "DECIMAL(10, 6) NOT NULL DEFAULT 0",
    )
    for obsolete_column in (
        "precision_score",
        "recall_score",
        "ndcg_score",
        "precision_at_10",
        "recall_at_10",
        "ndcg_at_10",
        "coverage_score",
        "diversity_score",
        "interacted_flats",
        "relevant_flats",
        "favourited_flats",
        "favourite_rate",
    ):
        _drop_column(db, MODEL_EVALUATION_TABLE, obsolete_column)

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
    db.cursor.execute(
        f"""
        UPDATE {RECOMMENDATION_SESSION_TABLE}
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _session_has_ranked_rows(session_rows: list[dict[str, Any]]) -> bool:
    return any(_safe_int(row.get("position")) >= 1 for row in session_rows)


def _session_favourited_flat_ids(session_rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("resale_flat_id") or "")
        for row in session_rows
        if _safe_int(row.get("user_like_count")) > 0 and str(row.get("resale_flat_id") or "")
    }


def _session_viewed_flat_ids(session_rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("resale_flat_id") or "")
        for row in session_rows
        if (
            _safe_int(row.get("user_view_count")) > 0
            or _safe_int(row.get("user_like_count")) > 0
        )
        and str(row.get("resale_flat_id") or "")
    }


def _session_relevance_at_k(session_rows: list[dict[str, Any]], k: int = EVALUATION_K) -> list[int]:
    favourited_flat_ids = _session_favourited_flat_ids(session_rows)
    flat_id_by_position: dict[int, str] = {}

    ordered_rows = sorted(
        session_rows,
        key=lambda row: (
            _safe_int(row.get("position"), k + 1),
            str(row.get("resale_flat_id") or ""),
        ),
    )
    for row in ordered_rows:
        position = _safe_int(row.get("position"))
        flat_id = str(row.get("resale_flat_id") or "")
        if not flat_id or position < 1 or position > k or position in flat_id_by_position:
            continue
        flat_id_by_position[position] = flat_id

    return [
        1 if flat_id_by_position.get(position) in favourited_flat_ids else 0
        for position in range(1, k + 1)
    ]


def _dcg_at_k(relevance: list[int], k: int = EVALUATION_K) -> float:
    total = 0.0
    for index, rel in enumerate(relevance[:k], start=1):
        if rel <= 0:
            continue
        total += rel / math.log2(index + 1)
    return total


def _idcg_at_k(total_relevant: int, k: int = EVALUATION_K) -> float:
    ideal_hits = min(k, max(total_relevant, 0))
    return sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))


def calculate_model_evaluations(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_model_and_session: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in raw_rows:
        model_key = normalise_model_key(row.get("recommendation"))
        session_id = str(row.get("session_id") or "").strip()
        if model_key not in MODEL_KEYS or not session_id:
            continue
        rows_by_model_and_session[model_key][session_id].append(row)

    metrics: list[dict[str, Any]] = []
    for config in MODEL_CONFIGS:
        model_key = config["key"]
        session_rows_map = rows_by_model_and_session.get(model_key, {})
        evaluated_sessions: list[dict[str, Any]] = []

        for session_id, session_rows in session_rows_map.items():
            if not _session_has_ranked_rows(session_rows):
                continue

            relevance = _session_relevance_at_k(session_rows, EVALUATION_K)
            viewed_flat_ids = _session_viewed_flat_ids(session_rows)
            favourited_flat_ids = _session_favourited_flat_ids(session_rows)
            hits_at_k = sum(relevance)
            total_favourited = len(favourited_flat_ids)
            dcg = _dcg_at_k(relevance, EVALUATION_K)
            idcg = _idcg_at_k(total_favourited, EVALUATION_K)

            evaluated_sessions.append(
                {
                    "session_id": session_id,
                    "precision": hits_at_k / EVALUATION_K,
                    "recall": (hits_at_k / total_favourited) if total_favourited else 0.0,
                    "ndcg": (dcg / idcg) if idcg else 0.0,
                    "viewed_flats": len(viewed_flat_ids),
                    "favourited_flats": total_favourited,
                }
            )

        total_viewed = sum(session["viewed_flats"] for session in evaluated_sessions)
        total_favourited = sum(session["favourited_flats"] for session in evaluated_sessions)
        favourite_rate = (total_favourited / total_viewed) if total_viewed else 0.0
        precision = (
            sum(session["precision"] for session in evaluated_sessions) / len(evaluated_sessions)
            if evaluated_sessions
            else 0.0
        )
        recall = (
            sum(session["recall"] for session in evaluated_sessions) / len(evaluated_sessions)
            if evaluated_sessions
            else 0.0
        )
        ndcg = (
            sum(session["ndcg"] for session in evaluated_sessions) / len(evaluated_sessions)
            if evaluated_sessions
            else 0.0
        )

        metric = {
            "recommendation": model_key,
            "recommendation_label": MODEL_LABELS[model_key],
            "k": EVALUATION_K,
            "sessions": len(evaluated_sessions),
            "precision_at_k": round(precision, 6),
            "recall_at_k": round(recall, 6),
            "ndcg_at_k": round(ndcg, 6),
            "viewed_flats": total_viewed,
            "favorited_flats": total_favourited,
            "favorite_rate": round(favourite_rate, 6),
        }
        metrics.append(metric)

    return metrics


def refresh_model_evaluations(db: DbConnector | None = None) -> list[dict[str, Any]]:
    close_db = db is None
    if close_db:
        db = DbConnector()

    try:
        _ensure_tables_with_db(db)
        db.cursor.execute(
            f"""
            SELECT session_id, recommendation, resale_flat_id, position,
                   user_like_count, user_view_count
            FROM {RECOMMENDATION_SESSION_TABLE}
            """
        )
        metrics = calculate_model_evaluations([dict(row) for row in db.cursor.fetchall() or []])
        for metric in metrics:
            db.cursor.execute(
                f"""
                INSERT INTO {MODEL_EVALUATION_TABLE} (
                    recommendation,
                    recommendation_label,
                    k_value,
                    sessions,
                    precision_at_k,
                    recall_at_k,
                    ndcg_at_k,
                    viewed_flats,
                    favorited_flats,
                    favorite_rate
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    recommendation_label = VALUES(recommendation_label),
                    k_value = VALUES(k_value),
                    sessions = VALUES(sessions),
                    precision_at_k = VALUES(precision_at_k),
                    recall_at_k = VALUES(recall_at_k),
                    ndcg_at_k = VALUES(ndcg_at_k),
                    viewed_flats = VALUES(viewed_flats),
                    favorited_flats = VALUES(favorited_flats),
                    favorite_rate = VALUES(favorite_rate)
                """,
                (
                    metric["recommendation"],
                    metric["recommendation_label"],
                    metric["k"],
                    metric["sessions"],
                    metric["precision_at_k"],
                    metric["recall_at_k"],
                    metric["ndcg_at_k"],
                    metric["viewed_flats"],
                    metric["favorited_flats"],
                    metric["favorite_rate"],
                ),
            )
        if close_db:
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
            SELECT recommendation,
                   recommendation_label,
                   k_value AS k,
                   sessions,
                   precision_at_k,
                   recall_at_k,
                   ndcg_at_k,
                   viewed_flats,
                   favorited_flats,
                   favorite_rate,
                   updated_at
            FROM {MODEL_EVALUATION_TABLE}
            ORDER BY recommendation
            """
        )
        rows = [dict(row) for row in db.cursor.fetchall() or []]
        if rows:
            return rows
        metrics = refresh_model_evaluations(db)
        db.Commit()
        return metrics
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

    favourite_rates = {}
    equal_probability = round(1.0 / float(len(MODEL_KEYS)), 6) if MODEL_KEYS else 0.0
    for model_key in MODEL_KEYS:
        totals = interaction_totals.get(model_key, {})
        likes = max(int(totals.get("likes") or 0), 0)
        views = max(int(totals.get("views") or 0), 0)

        raw_rate = round(likes / views, 6) if views else 0.0

        favourite_rates[model_key] = raw_rate

    return {
        model_key: {
            "key": model_key,
            "label": MODEL_LABELS[model_key],
            "likes": interaction_totals.get(model_key, {}).get("likes", 0),
            "views": interaction_totals.get(model_key, {}).get("views", 0),
            "favourited_flats": interaction_totals.get(model_key, {}).get("likes", 0),
            "viewed_flats": interaction_totals.get(model_key, {}).get("views", 0),
            "favourite_rate": favourite_rates[model_key],
            "weight": equal_probability,
            "probability": equal_probability,
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

    chosen_key = random.choice(list(snapshot.keys()))
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


def _parse_recommendation_snapshot(snapshot: Any) -> list[dict[str, Any]]:
    if not isinstance(snapshot, list):
        return []

    parsed: list[dict[str, Any]] = []
    seen_flat_ids: set[str] = set()
    seen_positions: set[int] = set()

    for fallback_position, item in enumerate(snapshot, start=1):
        if not isinstance(item, dict):
            continue

        resale_flat_id = str(item.get("resale_flat_id") or "").strip()
        position = _safe_int(item.get("position"), fallback_position)
        if (
            not resale_flat_id
            or resale_flat_id in seen_flat_ids
            or position < 1
            or position in seen_positions
        ):
            continue

        parsed.append(
            {
                "resale_flat_id": resale_flat_id,
                "position": position,
            }
        )
        seen_flat_ids.add(resale_flat_id)
        seen_positions.add(position)

    return sorted(parsed, key=lambda item: item["position"])


def _fetch_session_feedback_rows(
    db: DbConnector,
    session_id: str,
    recommendation: str,
    resale_flat_id: str | None = None,
) -> list[dict[str, Any]]:
    if resale_flat_id:
        db.cursor.execute(
            f"""
            SELECT session_id, resale_flat_id, recommendation, position,
                   user_like_count, user_view_count
            FROM {RECOMMENDATION_SESSION_TABLE}
            WHERE session_id = %s
              AND recommendation = %s
              AND resale_flat_id = %s
            """,
            (session_id, recommendation, resale_flat_id),
        )
    else:
        db.cursor.execute(
            f"""
            SELECT session_id, resale_flat_id, recommendation, position,
                   user_like_count, user_view_count
            FROM {RECOMMENDATION_SESSION_TABLE}
            WHERE session_id = %s
              AND recommendation = %s
            """,
            (session_id, recommendation),
        )
    return [dict(row) for row in db.cursor.fetchall() or []]


def _upsert_session_snapshot(
    db: DbConnector,
    session_id: str,
    recommendation: str,
    recommendation_snapshot: list[dict[str, Any]],
) -> None:
    for item in recommendation_snapshot:
        db.cursor.execute(
            f"""
            INSERT INTO {RECOMMENDATION_SESSION_TABLE} (
                session_id, recommendation, resale_flat_id, position,
                user_like_count, user_view_count
            ) VALUES (%s, %s, %s, %s, 0, 0)
            ON DUPLICATE KEY UPDATE
                position = VALUES(position)
            """,
            (
                session_id,
                recommendation,
                item["resale_flat_id"],
                item["position"],
            ),
        )


def sync_recommendation_snapshot(
    recommendation: str,
    session_id: str,
    recommendation_snapshot: Any,
) -> dict[str, Any]:
    model_key = normalise_model_key(recommendation)
    session_key = str(session_id or "").strip()
    parsed_recommendation_snapshot = _parse_recommendation_snapshot(recommendation_snapshot)

    if model_key not in MODEL_KEYS:
        raise ValueError("recommendation model is invalid")
    if not session_key:
        raise ValueError("session_id is required")
    if not parsed_recommendation_snapshot:
        raise ValueError("recommendation_snapshot must contain at least one recommendation")

    db = DbConnector()
    try:
        _ensure_tables_with_db(db)
        _upsert_session_snapshot(
            db,
            session_key,
            model_key,
            parsed_recommendation_snapshot,
        )
        metrics = refresh_model_evaluations(db)
        db.Commit()
        return {
            "session_id": session_key,
            "recommendation": model_key,
            "recommendation_label": MODEL_LABELS[model_key],
            "stored_recommendations": len(parsed_recommendation_snapshot),
            "model_evaluation": metrics,
        }
    finally:
        db.Close()


def _write_session_feedback_row(
    db: DbConnector,
    session_id: str,
    resale_flat_id: str,
    recommendation: str,
    viewed_flag: int,
    favourite_flag: int,
    position: int | None = None,
) -> dict[str, Any]:
    db.cursor.execute(
        f"""
        INSERT INTO {RECOMMENDATION_SESSION_TABLE} (
            session_id, recommendation, resale_flat_id, position,
            user_like_count, user_view_count
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            position = COALESCE(VALUES(position), position),
            user_like_count = VALUES(user_like_count),
            user_view_count = VALUES(user_view_count)
        """,
        (
            session_id,
            recommendation,
            str(resale_flat_id),
            position,
            int(favourite_flag),
            int(viewed_flag),
        ),
    )
    rows = _fetch_session_feedback_rows(db, session_id, recommendation, resale_flat_id)
    row = rows[0] if rows else {
        "session_id": session_id,
        "resale_flat_id": str(resale_flat_id),
        "recommendation": recommendation,
        "position": position,
        "user_like_count": int(favourite_flag),
        "user_view_count": int(viewed_flag),
    }
    row["user_favourite"] = int(row.get("user_like_count") or 0) > 0
    row["user_viewed"] = int(row.get("user_view_count") or 0) > 0
    return row


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
    session_id: str | None = None,
    recommendation_snapshot: Any = None,
) -> dict[str, Any]:
    resale_flat_id = str(resale_flat_id or "").strip()
    model_key = normalise_model_key(recommendation) if recommendation else None
    session_key = str(session_id or "").strip() or None
    parsed_recommendation_snapshot = _parse_recommendation_snapshot(recommendation_snapshot)

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
            if session_key:
                _upsert_session_snapshot(
                    db,
                    session_key,
                    model_key,
                    parsed_recommendation_snapshot,
                )
                snapshot_position = next(
                    (
                        item["position"]
                        for item in parsed_recommendation_snapshot
                        if item["resale_flat_id"] == resale_flat_id
                    ),
                    None,
                )
                _write_session_feedback_row(
                    db,
                    session_key,
                    resale_flat_id,
                    model_key,
                    next_viewed,
                    next_favourite,
                    snapshot_position,
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
        db.Commit()
        summary_row = updated_rows[0] if len(updated_rows) == 1 else None

        return {
            "resale_flat_id": resale_flat_id,
            "session_id": session_key,
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


def record_feedback(
    resale_flat_id: str,
    recommendation: str,
    event: str,
    session_id: str | None = None,
    recommendation_snapshot: Any = None,
) -> dict[str, Any]:
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
            session_id=session_id,
            recommendation_snapshot=recommendation_snapshot,
        )
    elif event in {"like", "favorite", "favourite"}:
        result = set_feedback_state(
            resale_flat_id=resale_flat_id,
            recommendation=recommendation,
            viewed=True,
            favourite=True,
            session_id=session_id,
            recommendation_snapshot=recommendation_snapshot,
        )
    else:
        result = set_feedback_state(
            resale_flat_id=resale_flat_id,
            recommendation=recommendation,
            viewed=True,
            favourite=False,
            session_id=session_id,
            recommendation_snapshot=recommendation_snapshot,
        )

    result["event"] = event
    return result
