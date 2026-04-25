from __future__ import annotations

import os
import sys
from typing import Any

_SERVICE_ROOT = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.abspath(os.path.join(_SERVICE_ROOT, ".."))

for _path in (_SERVICE_ROOT, _BACKEND_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from amenity_proximity_service.utils.db_connector import DbConnector
from recommendation_scorer_service.model_catalog import normalise_model_key


FAVOURITES_TABLE = "favourites"


def _ensure_table_with_db(db: DbConnector) -> None:
    db.cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {FAVOURITES_TABLE} (
            resale_flat_id VARCHAR(255) NOT NULL,
            recommendation_model VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (resale_flat_id),
            INDEX idx_favourites_created_at (created_at)
        )
        """
    )
    db.cursor.execute(f"SHOW COLUMNS FROM {FAVOURITES_TABLE}")
    columns = {str(row.get("Field") or "") for row in db.cursor.fetchall() or []}
    if "recommendation_model" not in columns:
        db.cursor.execute(
            f"""
            ALTER TABLE {FAVOURITES_TABLE}
            ADD COLUMN recommendation_model VARCHAR(64) NULL
            """
        )


def _format_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat(sep=" ", timespec="seconds")
    return str(value)


def _normalise_flat_row(row: dict[str, Any]) -> dict[str, Any]:
    flat = dict(row)

    sold_date = flat.get("sold_date")
    if hasattr(sold_date, "strftime"):
        flat["sold_date"] = sold_date.strftime("%Y-%m")

    created_at = flat.get("created_at")
    flat["created_at"] = _format_timestamp(created_at)

    if flat.get("latitude") is not None:
        flat["latitude"] = float(flat["latitude"])
    if flat.get("longitude") is not None:
        flat["longitude"] = float(flat["longitude"])

    return flat


def list_favourites_with_db(db: DbConnector) -> list[dict[str, Any]]:
    _ensure_table_with_db(db)
    db.cursor.execute(
        f"""
        SELECT f.resale_flat_id,
               f.recommendation_model,
               rf.estate,
               rf.block,
               rf.street_name,
               rf.flat_type,
               rf.flat_model,
               rf.storey_range_start,
               rf.storey_range_end,
               rf.floor_area_sqm,
               rf.remaining_lease_years,
               rf.remaining_lease_months,
               rf.resale_price,
               rf.sold_date,
               g.latitude,
               g.longitude,
               f.created_at
        FROM {FAVOURITES_TABLE} f
        JOIN resale_flats rf
          ON rf.resale_flat_id = f.resale_flat_id
        LEFT JOIN resale_flats_geolocation g
          ON g.block = rf.block AND g.street_name = rf.street_name
        ORDER BY f.created_at DESC
        """
    )
    rows = db.cursor.fetchall() or []
    return [_normalise_flat_row(dict(row)) for row in rows]


def list_favourites() -> dict[str, Any]:
    db = DbConnector()
    try:
        favourites = list_favourites_with_db(db)
        return {"favourites": favourites}
    finally:
        db.Close()


def _flat_exists(db: DbConnector, resale_flat_id: str) -> bool:
    db.cursor.execute(
        """
        SELECT resale_flat_id
        FROM resale_flats
        WHERE resale_flat_id = %s
        LIMIT 1
        """,
        (resale_flat_id,),
    )
    return db.cursor.fetchone() is not None


def toggle_favourite(resale_flat_id: str, recommendation_model: str | None = None) -> dict[str, Any]:
    resale_flat_id = str(resale_flat_id or "").strip()
    recommendation_model = normalise_model_key(recommendation_model)
    if not resale_flat_id:
        raise ValueError("resale_flat_id is required")

    db = DbConnector()
    try:
        _ensure_table_with_db(db)
        db.cursor.execute(
            f"""
            SELECT resale_flat_id
            FROM {FAVOURITES_TABLE}
            WHERE resale_flat_id = %s
            LIMIT 1
            """,
            (resale_flat_id,),
        )
        existing = db.cursor.fetchone()

        if existing:
            db.cursor.execute(
                f"DELETE FROM {FAVOURITES_TABLE} WHERE resale_flat_id = %s",
                (resale_flat_id,),
            )
            is_favourite = False
        else:
            if not _flat_exists(db, resale_flat_id):
                raise ValueError("Flat not found")
            db.cursor.execute(
                f"""
                INSERT INTO {FAVOURITES_TABLE} (resale_flat_id, recommendation_model)
                VALUES (%s, %s)
                """,
                (resale_flat_id, recommendation_model),
            )
            is_favourite = True

        db.Commit()
        favourites = list_favourites_with_db(db)
        return {
            "resale_flat_id": resale_flat_id,
            "is_favourite": is_favourite,
            "favourites": favourites,
        }
    finally:
        db.Close()


def remove_favourite(resale_flat_id: str) -> dict[str, Any]:
    resale_flat_id = str(resale_flat_id or "").strip()
    if not resale_flat_id:
        raise ValueError("resale_flat_id is required")

    db = DbConnector()
    try:
        _ensure_table_with_db(db)
        db.cursor.execute(
            f"DELETE FROM {FAVOURITES_TABLE} WHERE resale_flat_id = %s",
            (resale_flat_id,),
        )
        db.Commit()
        favourites = list_favourites_with_db(db)
        return {
            "resale_flat_id": resale_flat_id,
            "is_favourite": False,
            "favourites": favourites,
        }
    finally:
        db.Close()
