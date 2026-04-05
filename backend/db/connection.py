"""
db/connection.py
================
SQLite connection management.

To migrate to PostgreSQL/PostGIS later:
  1. Replace sqlite3 with psycopg2 or asyncpg
  2. Update get_conn() to read DATABASE_URL from environment
  3. Replace schema.sql CREATE TABLE with PostGIS equivalents
  4. Update queries.py spatial lookups to use ST_Distance()
  Nothing else needs to change.
"""

import sqlite3
from pathlib import Path

DB_PATH    = Path(__file__).parent.parent / "data" / "hdb.db"
SCHEMA_SQL = Path(__file__).parent / "schema.sql"


def get_conn() -> sqlite3.Connection:
    """
    Return a SQLite connection with row_factory set so rows
    behave like dicts (e.g. row["resale_price"]).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # Better concurrent read performance
    return conn


def init_schema():
    """Create all tables if they don't exist. Safe to call on every startup."""
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL.read_text())
    print("[db] Schema initialised.")
