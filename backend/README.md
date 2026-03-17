# HDB Estate Recommender — Backend

FastAPI backend for the HDB Estate Recommender. Serves the
`hdb-recommender.html` front-end via a single POST endpoint.

---

## Quick Start (Local)

```bash
# 1. Clone / copy this folder to your machine

# 2. Install dependencies (Python 3.11+)
pip install -r requirements.txt

# 3. Download data files
python scripts/download_data.py

# 4. Start the server
uvicorn main:app --reload --port 8000
# → API running at http://localhost:8000
# → Docs at http://localhost:8000/docs
```

Then open `hdb-recommender.html` in your browser.
Set `API_BASE = "http://localhost:8000"` in the HTML (one line change).

---

## Project Structure

```
hdb-backend/
├── main.py                 ← FastAPI app entry point
├── requirements.txt
├── Dockerfile              ← For Railway/Render deployment
├── .env.example            ← Environment variable template
│
├── api/
│   └── routes.py           ← HTTP routes (thin layer only)
│
├── core/                   ← Business logic (no I/O)
│   ├── grants.py           ← EHG, CPF Grant, PHG calculation
│   ├── eligibility.py      ← HDB eligibility rules
│   ├── prices.py           ← Price analysis, forward estimates
│   ├── loan.py             ← Loan capacity calculator
│   └── recommender.py      ← Orchestrator — calls all modules
│
├── scoring/                ← Isolated scoring system
│   ├── weights.py          ← ← Change weights HERE ONLY
│   ├── budget_score.py
│   ├── amenity_score.py
│   ├── transport_score.py
│   ├── region_score.py
│   ├── flat_score.py
│   └── aggregator.py       ← Combines all 5 components
│
├── geo/
│   ├── distances.py        ← Haversine + 20% walking buffer
│   ├── centroids.py        ← Pre-coded town lat/lng
│   └── onemap.py           ← OneMap Routing API (future)
│
├── db/
│   ├── connection.py       ← SQLite connection (swap → PostGIS here)
│   ├── schema.sql          ← Table definitions
│   ├── loader.py           ← Load CSV + GeoJSON → SQLite
│   └── queries.py          ← All SQL queries
│
├── data/                   ← Raw data files (not in git if large)
│   ├── resale_prices.csv   ← Download via scripts/download_data.py
│   ├── planning_areas.geojson
│   ├── hawker_centres.geojson
│   ├── mrt_stations.geojson
│   ├── hospitals.geojson   ← Pre-built (included in repo)
│   ├── schools.geojson     ← Download manually (see below)
│   └── parks.geojson       ← Download manually (see below)
│
└── scripts/
    ├── download_data.py    ← First-time data download
    └── refresh_resale.py   ← Monthly resale CSV update
```

---

## Data Sources

| File | Source | Dataset ID |
|---|---|---|
| `resale_prices.csv` | data.gov.sg | `d_8b84c4ee58e3cfc0ece0d773c8ca6abc` |
| `planning_areas.geojson` | data.gov.sg | `d_4765db0e87b9c86336792efe8a1f7a66` |
| `hawker_centres.geojson` | data.gov.sg (NEA) | `d_4a086da0a5553be1d89383cd90d07ebc` |
| `mrt_stations.geojson` | data.gov.sg (LTA) | `d_5cb3563c5584bb533dfc3fbec97153e8` |
| `hospitals.geojson` | Manually curated | Included in repo |
| `schools.geojson` | data.gov.sg (MOE) | Search: "General Information of Schools" |
| `parks.geojson` | data.gov.sg (NParks) | Search: "Parks" | `d_0542d48f0991541706b58059381a6eca` |

Manual downloads: https://data.gov.sg/datasets

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness check |
| `POST` | `/api/recommend` | Main recommendation endpoint |
| `GET` | `/api/prices?town=X&ftype=Y` | Price trend for Trends tab |
| `POST` | `/api/refresh` | Re-load resale CSV (after monthly update) |

### POST /api/recommend — Request body

```json
{
  "cit": "SC_SC",
  "marital": "married",
  "age": 35,
  "income": 6000,
  "ftimer": "first",
  "prox": "none",
  "ftype": "4 ROOM",
  "regions": ["North", "East"],
  "must_have": ["mrt", "hawker"],
  "max_mrt_mins": 15,
  "min_lease": 60,
  "cash": 50000,
  "cpf": 80000,
  "loan": 2000
}
```

---

## Deployment (Railway — Free Tier)

```bash
# 1. Push to GitHub
git init && git add . && git commit -m "init"
gh repo create hdb-backend --private --push

# 2. Go to railway.app → New Project → Deploy from GitHub
# 3. Select your repo — Railway auto-detects Dockerfile
# 4. Add environment variables in Railway dashboard if needed
# 5. Get your deployment URL (e.g. https://hdb-backend.railway.app)

# 6. Update ONE LINE in hdb-recommender.html:
#    const API_BASE = "https://hdb-backend.railway.app";

# 7. Send hdb-recommender.html to project mates — done.
```

**Important**: Railway's free tier uses ephemeral storage.
The SQLite DB and CSV are rebuilt on each deploy from the
data files committed to the repo.
For persistent storage, add a Railway Volume or switch to PostgreSQL.

---

## Monthly Data Refresh

```bash
# Run manually after data.gov.sg publishes new resale data (usually mid-month)
python scripts/refresh_resale.py

# Or schedule with cron (runs at 2am on the 1st of each month):
# 0 2 1 * * cd /path/to/hdb-backend && python scripts/refresh_resale.py
```

---

## Upgrading to PostgreSQL + PostGIS (future)

Only these files change:
1. `db/connection.py` — replace `sqlite3` with `psycopg2`
2. `db/schema.sql` — add `GEOGRAPHY` columns for spatial queries
3. `db/queries.py` — replace Python-side distance loops with
   `ST_DWithin()` / `ST_Distance()` PostGIS queries
4. `requirements.txt` — add `psycopg2-binary`

Everything else (scoring, grants, eligibility, routes) stays the same.

---

## Scoring Weights

Edit `scoring/weights.py` only. Current weights:

| Component | Weight |
|---|---|
| Budget fit | 20 pts |
| Amenity proximity | 30 pts |
| Transport (MRT) | 20 pts |
| Region match | 15 pts |
| Flat attributes | 15 pts |

---

## Switching Distance Method (Haversine → OneMap)

1. Get an OneMap API key: https://www.onemap.gov.sg/apidocs/
2. Add `ONEMAP_API_KEY=your_key` to `.env`
3. In `geo/distances.py`, replace `_nearest()` calls with
   `onemap.get_route_walk_mins()` from `geo/onemap.py`
4. No other files change.
