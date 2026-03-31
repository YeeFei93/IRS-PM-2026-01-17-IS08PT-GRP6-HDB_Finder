-- db/schema.sql
-- HDB Recommender SQLite Schema
-- Run via: db/connection.py on first startup
-- Migrate to PostgreSQL/PostGIS: replace TEXT with VARCHAR,
--   add PostGIS GEOGRAPHY columns for spatial queries.

-- ── Resale transactions ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS resale_transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    month           TEXT NOT NULL,          -- "YYYY-MM"
    town            TEXT NOT NULL,
    flat_type       TEXT NOT NULL,          -- "4 ROOM" etc.
    block           TEXT,
    street_name     TEXT,
    storey_range    TEXT,                   -- "10 TO 12"
    floor_area_sqm  REAL,
    flat_model      TEXT,
    lease_commence_date INTEGER,
    remaining_lease TEXT,
    resale_price    REAL NOT NULL,
    loaded_at       TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_resale_town_type_month
    ON resale_transactions (town, flat_type, month);

-- ── GeoJSON feature cache: hawker centres ────────────────────────────────────
CREATE TABLE IF NOT EXISTS hawker_centres (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    address TEXT,
    lat     REAL NOT NULL,
    lng     REAL NOT NULL
);

-- ── GeoJSON feature cache: MRT stations ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS mrt_stations (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    code    TEXT,
    line    TEXT,
    lat     REAL NOT NULL,
    lng     REAL NOT NULL
);

-- ── GeoJSON feature cache: hospitals ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hospitals (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    address TEXT,
    lat     REAL NOT NULL,
    lng     REAL NOT NULL
);

-- ── GeoJSON feature cache: parks ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS parks (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    lat     REAL NOT NULL,
    lng     REAL NOT NULL
);

-- ── GeoJSON feature cache: schools ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schools (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    address TEXT,
    lat     REAL NOT NULL,
    lng     REAL NOT NULL
);

-- ── Data refresh log ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS refresh_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset     TEXT NOT NULL,
    rows_loaded INTEGER,
    refreshed_at TEXT DEFAULT (datetime('now'))
);

-- ── GeoJSON feature cache: shopping malls ────────────────────────────────────
CREATE TABLE IF NOT EXISTS malls (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    lat     REAL NOT NULL,
    lng     REAL NOT NULL
);
