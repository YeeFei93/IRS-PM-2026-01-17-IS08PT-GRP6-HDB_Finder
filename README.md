# RS-PM-2026-01-17-IS08PT-GRP-HDB

## HDB Estate Recommender — Singapore

A React + Tailwind CSS web app that recommends HDB resale estates based on your buyer profile, budget, and amenity preferences. It pulls live resale transaction data from [data.gov.sg](https://data.gov.sg), computes applicable grants (EHG, CPF Housing Grant, PHG), and scores/ranks estates across budget fit, transport access, amenities, and region match.

## Prerequisites

- [Node.js](https://nodejs.org/) v18 or later
- [Python](https://www.python.org/downloads/release/python-3143/) v3.14.3
- [MySql]
- [MySql Database] https://drive.google.com/file/d/1VlkZ--Xrlk9NDriW_ifACRz9yQRVV24B/view?usp=sharing
- npm (comes with Node.js)

## Getting Started

```bash
# Clone the repo
git clone https://github.com/<your-org>/RS-PM-2026-01-17-IS08PT-GRP-HDB.git
cd RS-PM-2026-01-17-IS08PT-GRP-HDB

# Install dependencies
npm install

# Start the development server
npm run dev
```

The app will be available at `http://localhost:5173/`.

## Build for Production

```bash
npm run build
```

The output will be in the `dist/` folder, ready to be deployed to any static hosting provider.

---

## System Architecture

```
┌──────────────┐        ┌──────────────────────┐        ┌──────────────────────────┐
│   Frontend   │  POST  │   Express API (TS)    │  Redis │   Python Adapters (×4)   │
│  React/Vite  │───────▶│   :3000               │───────▶│   BRPOP / LPUSH          │
│  :5173       │◀───────│                       │◀───────│                          │
└──────────────┘  JSON  └──────────────────────┘  JSON  └────────┬─────────────────┘
                                                                 │ calls
                                                     ┌───────────┼───────────┐
                                                     ▼           ▼           ▼
                                              Eligibility   Recommender   Flat Lookup
                                              Checker       Scorer        + Amenities
                                                     │           │           │
                                                     └───────────┼───────────┘
                                                                 ▼
                                                          MySQL (localhost)
                                              iss-irs-ai-estate-recommender-05
```

### Request flow

1. **Frontend** sends a `POST` request (e.g. `/api/top-recommendations`) to the Express API.
2. **Express API** generates a UUID `request_id`, pushes the job onto a Redis queue (e.g. `queue:recommendation`), then blocks on a reply queue (`reply:{request_id}`) with a timeout.
3. A **Python adapter** running an infinite `BRPOP` loop picks up the job, calls the corresponding Python service function, and `LPUSH`es the result back onto the reply queue (TTL 30 s).
4. The Express API returns the result as JSON to the frontend.

### API Endpoints

| Method | Route | Redis Queue | Timeout | Purpose |
|--------|-------|-------------|---------|---------|
| POST | `/api/eligibility-check` | `queue:eligibility` | 15 s | Validate buyer eligibility |
| POST | `/api/top-recommendations` | `queue:recommendation` | 90 s | Full recommendation pipeline |
| POST | `/api/flats` | `queue:flat_lookup` | 60 s | Flat transactions for an estate |
| POST | `/api/flat-amenities` | `queue:flat_amenities` | 30 s | Amenities near a specific block |

---

## Backend Services

The backend is split into independent Python services, each doing one job:

### Eligibility Checker (`eligibility_checker_service/`)

Pure function `check_eligibility(profile)`. Determines whether a buyer can purchase HDB resale based on citizenship, age, marital status, and income.

- PRs → resale only
- Singles must be ≥ 35
- Income ceilings: $9 k (EHG), $14 k (CPF grant), $7 k (singles)

### Grant Calculator (`budget_estimator_service/grants.py`)

Computes three stacking grants:

| Grant | Max Amount | Key Rules |
|-------|-----------|-----------|
| **EHG** (Enhanced Housing Grant) | $120 k | Banded by income. Table A (families), Table B (singles/mixed — half-income lookup). PRs and second-timers excluded. |
| **CPF Housing Grant** | $80 k | SC/SC up to $80 k (≤ 4 RM) / $50 k (5 RM+). SC/PR, SC/NR, singles get lower amounts. |
| **PHG** (Proximity Housing Grant) | $30 k | $30 k same flat / $20 k within 4 km of parents. No income ceiling. Second-timers and singles receive half. |

### Budget Estimator (`budget_estimator_service/`)

- `loan_capacity()` — annuity formula at 2.6 % p.a. / 25 years, capped at $750 k, MSR 30 %, LTV 75 %.
- `effective_budget = cash + CPF + grants.total + min(loan_capacity, $750k)`

### Price Analyser (`budget_estimator_service/prices.py`)

`analyse_town_prices(town, ftype)` — queries 14-month (fallback 24-month) transactions and computes: median, p25, p75, avg area, PSM, avg storey, avg remaining lease, 12-month trend %, forward estimate, confidence flag.

### Estate Finder (`estate_finder_service/queries.py`)

All SQL queries for flat/estate data. Key functions:

- `get_flats_for_estate()` — with dynamic filters (flat type, floor pref, min lease), sorted by budget proximity. JOINs `resale_flats_geolocation` for lat/lng.
- `get_all_amenities_for_flat()` — returns parks, hawkers, MRTs, schools, malls, hospitals for a block.
- Only returns flats sold from October 2025 onward.

### Amenity Proximity (`amenity_proximity_service/`)

Queries 6 junction tables for per-block amenity statistics:

| Amenity | Junction Table | Threshold |
|---------|---------------|-----------|
| MRT | `resale_flats_mrt_stations` | ≤ 1.0 km |
| Hawker | `resale_flats_hawker_centres` | ≤ 1.0 km |
| Mall | `resale_flats_shopping_malls` | ≤ 1.5 km |
| Park | `resale_flats_parks` | ≤ 1.0 km |
| School | `resale_flats_schools` | ≤ 1.0 km |
| Hospital | `resale_flats_public_hospitals` | ≤ 3.0 km |

Returns `{dist_km, walk_mins, within_threshold, count_within}` per amenity type per block. In-memory cache with background pre-warming on module load.

### Recommendation Scorer (`recommendation_scorer_service/`)

Orchestrates all services to produce the final ranked list:

1. **Eligibility check** → reject if ineligible
2. **Grants + effective budget** calculation
3. **Candidate towns** from selected regions (or all 26)
4. **Price metadata** via `analyse_town_prices()` per town (display only — no filtering)
5. **Parallel per-estate** (ThreadPoolExecutor, up to 8 workers): fetch **all** flats (sold from Oct 2025) with `remaining_lease_years ≥ min_lease` (SQL-level); Python-level filter `resale_price ≤ budget × 1.05`; compute per-block amenity stats; score each flat via 7-dim weighted cosine similarity
6. **Global flat ranking** — all surviving flats sorted by cosine score (descending)
7. **Estate grouping** — estates ordered by best-flat cosine score (descending), qualifying flat count as tiebreaker; return **all estates** with qualifying flats, each with top 10 cosine-ranked flats

---

## Database

**Engine:** MySQL 8.0 on `localhost:3306`
**Schema:** `iss-irs-ai-estate-recommender-05`

### Key Tables

| Table | Purpose |
|-------|---------|
| `estates` | 26 HDB towns (PK: estate name) |
| `regions` | 5 regions: Central, East, North, Northeast, West |
| `estates_regions` | Region ↔ estate mapping |
| `flat_types` | 7 types: 1 ROOM – MULTI-GENERATION |
| `flat_models` | 21 models: Standard, DBSS, Maisonette, etc. |
| `resale_flats` | Core transaction table (UUID PK, estate FK, flat\_type FK, block, storey\_range\_start/end, floor\_area\_sqm, remaining\_lease\_years/months, resale\_price, sold\_date) |
| `resale_flats_geolocation` | Block geocoordinates (PK: block + street\_name) |
| `hawker_centres` | Name, photo URL, lat/lng |
| `parks` | Name, lat/lng |
| `schools` | Name, lat/lng |
| `shopping_malls` | Name, lat/lng |
| `public_hospitals` | Name, lat/lng |
| `resale_flats_hawker_centres` | Junction: block ↔ hawker distance |
| `resale_flats_parks` | Junction: block ↔ park distance |
| `resale_flats_schools` | Junction: block ↔ school distance |
| `resale_flats_shopping_malls` | Junction: block ↔ mall distance |
| `resale_flats_mrt_stations` | Junction: block ↔ MRT distance |
| `resale_flats_public_hospitals` | Junction: block ↔ hospital distance |

Junction tables use **name-based foreign keys** (e.g. `park_name`, `hawker_centre_name`, `school_name`) linking blocks to amenities with pre-computed `distance_km`.

---

## Frontend

**Stack:** React + Vite + Tailwind CSS + Leaflet

### UI Phases

| Phase | Description |
|-------|-------------|
| `welcome` | Landing page with buyer profile sidebar |
| `loading` | Animated progress steps (6 stages) |
| `results` | Ranked estate cards with score breakdown |
| `empty` | No matches found |

### Tabs

- **Map** (`MapView`) — Leaflet map with GeoJSON estate boundaries, ranked estate list panel with drill-down to individual flat listings (cosine score per flat), amenity markers for selected flats
- **Trends** (`TrendsView`) — price trend charts

### Sidebar

Collapsible sections for buyer profile inputs: citizenship, age, marital status, income, first/second-timer, flat type, regions (multi-select tags), floor preference, min lease, cash/CPF/loan amounts, must-have amenities. Shows live eligibility badge and grant/budget summary (computed client-side via `engine.js` which mirrors backend grant logic).

---

## Data Pipeline

Batch import scripts in `backend/data-service/` populate MySQL from raw data:

1. **`save_resale_flats.py`** — imports resale transactions from CSV (data.gov.sg). Multi-threaded (3 threads). Parses storey range (`"X TO Y"` → int columns), remaining lease (`"X years Y months"` → int columns). Populates `estates`, `flat_types`, `flat_models`, `resale_flats_geolocation`, `resale_flats`.
2. **`save_hawker_centres.py`** — hawker centre data with photo URLs
3. **Other amenity scripts** — parks, schools, shopping malls, hospitals

Second-stage scripts in `backend/amenity_proximity_service/` compute distances:

1. **Geocode blocks** — SVY21 → WGS84 coordinate conversion
2. **Block ↔ amenity distances** — compute and store distances for each of the 6 amenity types into junction tables

Utilities: `csv_to_json.py`, `geojson_to_json.py`, `webscraper.py` (shopping malls from Wikipedia), `geolocation_converter.py` (SVY21 ↔ WGS84).

---

## Startup

Requirements: **Redis** and **MySQL** must be running (e.g. `brew services start redis mysql`).

```bash
# Terminal 1 — Backend (Express API + auto-spawned Python adapters)
cd backend/api
npm install
npm run dev

# Terminal 2 — Frontend (Vite dev server)
cd frontend
npm install
npm run dev
```

The Express API starts on `http://localhost:3000`, spawning 4 Python adapter child processes automatically. The frontend dev server runs on `http://localhost:5173`.

---

## Data Sources

| File | Source | Dataset ID |
|---|---|---|
| `resale_prices.csv` | data.gov.sg | `d_8b84c4ee58e3cfc0ece0d773c8ca6abc` |
| `planning_areas.geojson` | data.gov.sg | `d_4765db0e87b9c86336792efe8a1f7a66` |
| `hawker_centres.geojson` | data.gov.sg (NEA) | `d_4a086da0a5553be1d89383cd90d07ebc` |
| `mrt_stations.geojson` | data.gov.sg (LTA) | `d_5cb3563c5584bb533dfc3fbec97153e8` |
| `hospitals.geojson` | data.gov.sg (LTA) Manually curated, Included in repo | `d_1338b55f6d4ea6b2df9884ec4bce4464` | 
| `schools.geojson` | data.gov.sg (MOE) | Search: "General Information of Schools" | `d_688b934f82c1059ed0a6993d2a829089` |
| `parks.geojson` | data.gov.sg (NParks) | Search: "Parks" | `d_0542d48f0991541706b58059381a6eca` |
 `shopping_malls.csv`| Wikipedia | https://en.wikipedia.org/wiki/List_of_shopping_malls_in_Singapore |

Manual downloads: https://data.gov.sg/datasets

---

## Recommendation Scoring — Vector Design

Individual resale flats are scored using **weighted cosine similarity** between a buyer-preference vector and a per-flat vector. Each vector has **7 dimensions**. Estates are then ranked by the highest-scoring flat they contain.

**Scoring granularity:** cosine similarity is computed at the **individual flat** level (using each flat's actual storey and its block-level amenity counts), not at the estate aggregate level. This ensures that the recommendation reflects real listings rather than estate-wide averages.

| Dim | Feature | Encoding | Why a vector dimension |
|-----|---------|----------|----------------------|
| 0 | Floor preference | High → 1.0, Mid → 0.66, Low → 0.33, "Any" → 0.5; flat: storey midpoint / 50 | Genuinely bidirectional — "mid" means not too high and not too low; a one-sided constraint (e.g. min floor) would use a pre-filter instead |
| 1 | MRT proximity | count within 1.0 km / cap 3, clamped [0,1]; buyer: 1.0 if must-have, else 0.5 | Preference with diminishing returns — more MRT stations nearby is always better; cosine rewards alignment between buyer desire and flat supply |
| 2 | Hawker centre | count within 1.0 km / cap 5, clamped [0,1]; buyer: 1.0 if must-have, else 0.5 | Same rationale as MRT — amenity density is a genuine preference, not a hard constraint |
| 3 | Shopping mall | count within 1.5 km / cap 3, clamped [0,1]; buyer: 1.0 if must-have, else 0.5 | Same rationale; wider threshold (1.5 km) reflects typical acceptable walking distance to a mall |
| 4 | Park | count within 1.0 km / cap 4, clamped [0,1]; buyer: 1.0 if must-have, else 0.5 | Same rationale as MRT |
| 5 | School | count within 1.0 km / cap 4, clamped [0,1]; buyer: 1.0 if must-have, else 0.5 | Same rationale as MRT |
| 6 | Hospital | count within 3.0 km / cap 2, clamped [0,1]; buyer: 1.0 if must-have, else 0.5 | Same rationale; wider threshold (3.0 km) reflects that hospitals are sparse and typically reached by transport |

### Why budget, remaining lease, flat type, and region are NOT vector dimensions

Cosine similarity measures the *angle* between two vectors — it rewards alignment and penalises deviation in **both** directions. This is correct for genuine preferences (e.g., floor level, amenity proximity) but wrong for **one-sided constraints** and **hard-filtered features**:

- **Budget** is an **upper-bound constraint**: an estate that costs *less* than the buyer's budget is always acceptable — it should never be penalised. Making budget a vector dimension would penalise affordable estates for being "too cheap."
- **Remaining lease** is a **lower-bound constraint**: an estate with *more* remaining lease than the buyer requires is always acceptable. Making lease a vector dimension would penalise estates for having *too much* lease — the opposite of what the buyer wants.
- **Flat type** is a **hard pre-filter**: `analyse_town_prices(town, ftype)` queries only transactions matching the buyer's exact flat type. Every candidate already has the same flat type, so a vector dimension would be identical for all candidates and add zero discrimination.
- **Region** is a **hard pre-filter**: step 3 of the recommender restricts candidates to towns in the buyer's selected regions. Every candidate's region already matches, so a vector dimension would always score the same.

All four are handled as **pre-filters** that eliminate flats before cosine scoring:
- Budget: individual flat's `resale_price` must be ≤ buyer's effective budget × 1.05 (Python-level, per flat)
- Lease: individual flat's `remaining_lease_years` must be ≥ buyer's minimum lease requirement (SQL-level, per flat)
- Flat type: DB query selects only matching flat type
- Region: candidate town list restricted to selected regions

### How cosine similarity scoring works

The score is the weighted cosine between the buyer vector and an **individual flat's** vector:

$$\text{score} = \cos(W \odot \vec{b},\; W \odot \vec{f})$$

where $W[i] = 1.0$ if the criterion for dimension $i$ is **active** (buyer made a meaningful choice), or $0.25$ if **inactive** (left at default).

**Active criteria detection:**

| Criterion | Active when | Vector dims |
|-----------|------------|-------------|
| `budget` | effective\_budget > 0 | none (pre-filter only) |
| `flat` | ftype ≠ "any" | 0 |
| `region` | regions list non-empty | none (pre-filter only) |
| `amenity` | must\_have list non-empty | 1–6 |

If even one must-have amenity is selected, **all 6 amenity dims** (1–6) get W = 1.0.

### Amenity count scoring

Amenity dims 1–6 use count-within-threshold / cap, clamped to [0, 1]:

$$\text{amenity\_score} = \min\left(\frac{\text{count\_within}}{\text{cap}}, 1.0\right)$$

| Amenity | Threshold | Cap |
|---------|-----------|-----|
| MRT station | 1.0 km | 3 |
| Hawker centre | 1.0 km | 5 |
| Shopping mall | 1.5 km | 3 |
| Park | 1.0 km | 4 |
| Primary school | 1.0 km | 4 |
| Hospital | 3.0 km | 2 |

This rewards **amenity density**: a flat whose block has 2 MRT stations within 1.0 km scores higher than one with 1, reflecting genuine liveability. Amenity counts are computed per block/street (all flats in the same block share the same amenity distances).

### Worked examples

#### Scenario 1 — Strong match (score ≈ 0.98)

**Inputs:** `ftype="4 ROOM"`, `regions=["central"]`, `floor="high"`, `must_have=["mrt","hawker","park"]`, `budget=$500k`  
**Flat:** Blk 123 TOA PAYOH CENTRAL (central), `storey_range_start=37, storey_range_end=42`, block amenities: mrt×2, hawker×4, mall×1, park×3, school×3, hospital×1  
*(Pre-filters already applied: ftype selects DB query, region restricts town list, budget/lease filter candidates; scoring is per flat)*

**Active criteria:** `budget>0` ✓ | `ftype≠"any"` ✓ | `regions≠[]` ✓ | `must_have≠[]` ✓  
→ active = [budget, flat, region, amenity]  
→ W = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]

**Buyer vector:**

| Dim | How computed | Value |
|-----|-------------|-------|
| 0 | `FLOOR_PREF_ORD["high"]` | 1.0000 |
| 1 | `"mrt" in must_have → 1.0` | 1.0000 |
| 2 | `"hawker" in must_have → 1.0` | 1.0000 |
| 3 | `"mall" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 4 | `"park" in must_have → 1.0` | 1.0000 |
| 5 | `"school" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 6 | `"hospital" NOT in must_have → 0.5 (neutral)` | 0.5000 |

**Flat vector:**

| Dim | How computed | Value |
|-----|-------------|-------|
| 0 | `storey_midpoint(37, 42) = 39.5 / 50` | 0.7900 |
| 1 | `count_within=2 / _AMENITY_COUNT_CAP["mrt"]=3` | 0.6667 |
| 2 | `count_within=4 / _AMENITY_COUNT_CAP["hawker"]=5` | 0.8000 |
| 3 | `count_within=1 / _AMENITY_COUNT_CAP["mall"]=3` | 0.3333 |
| 4 | `count_within=3 / _AMENITY_COUNT_CAP["park"]=4` | 0.7500 |
| 5 | `count_within=3 / _AMENITY_COUNT_CAP["school"]=4` | 0.7500 |
| 6 | `count_within=1 / _AMENITY_COUNT_CAP["hospital"]=2` | 0.5000 |

**Why ≈0.98:** Floor close (buyer=1.0 vs flat=0.79). Active amenity dims (mrt, hawker, park) have buyer=1.0 vs flat 0.67–0.80 — close to parallel. Non-preferred amenities (mall buyer=0.5, flat=0.33) contribute at full W=1.0 but the small values don't drag much.

---

#### Scenario 2 — Moderate match (score ≈ 0.78)

**Inputs:** `ftype="4 ROOM"`, `regions=["east"]`, `floor="any"`, `must_have=["mrt"]`, `budget=$400k`  
**Flat:** Blk 456 JURONG WEST ST 41, `storey_range_start=1, storey_range_end=3`, block amenities: mrt×3, hawker×2, mall×1, park×1, school×2, hospital×0  
*(Pre-filters already applied: ftype selects DB query, budget/lease filter candidates)*

**Active criteria:** `budget>0` ✓ | `ftype≠"any"` ✓ | `regions≠[]` ✓ | `must_have≠[]` ✓  
→ active = [budget, flat, region, amenity]  
→ W = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]

**Buyer vector:**

| Dim | How computed | Value |
|-----|-------------|-------|
| 0 | `FLOOR_PREF_ORD["any"]` | 0.5000 |
| 1 | `"mrt" in must_have → 1.0` | 1.0000 |
| 2 | `"hawker" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 3 | `"mall" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 4 | `"park" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 5 | `"school" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 6 | `"hospital" NOT in must_have → 0.5 (neutral)` | 0.5000 |

**Flat vector:**

| Dim | How computed | Value |
|-----|-------------|-------|
| 0 | `storey_midpoint(1, 3) = 2 / 50` | 0.0400 |
| 1 | `count_within=3 / _AMENITY_COUNT_CAP["mrt"]=3` | 1.0000 |
| 2 | `count_within=2 / _AMENITY_COUNT_CAP["hawker"]=5` | 0.4000 |
| 3 | `count_within=1 / _AMENITY_COUNT_CAP["mall"]=3` | 0.3333 |
| 4 | `count_within=1 / _AMENITY_COUNT_CAP["park"]=4` | 0.2500 |
| 5 | `count_within=2 / _AMENITY_COUNT_CAP["school"]=4` | 0.5000 |
| 6 | `count_within=0 / _AMENITY_COUNT_CAP["hospital"]=2` | 0.0000 |

**Why ≈0.78:** MRT matches perfectly (1.0 vs 1.0). Floor hurts (buyer=0.5 "any" vs flat=0.04 ground floor). Hospital dim drags (buyer=0.5 neutral vs flat=0.0).

---

#### Scenario 3 — Poor match (score ≈ 0.55)

**Inputs:** `ftype="5 ROOM"`, `regions=["central"]`, `floor="high"`, `must_have=["mrt","hawker","park","school"]`, `budget=$600k`  
**Flat:** Blk 789 JURONG WEST ST 52, `storey_range_start=1, storey_range_end=3`, block amenities: mrt×0, hawker×1, mall×0, park×0, school×0, hospital×0  
*(Pre-filters already applied: ftype selects DB query, budget/lease filter candidates)*

**Active criteria:** `budget>0` ✓ | `ftype≠"any"` ✓ | `regions≠[]` ✓ | `must_have≠[]` ✓  
→ active = [budget, flat, region, amenity]  
→ W = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]

**Buyer vector:**

| Dim | How computed | Value |
|-----|-------------|-------|
| 0 | `FLOOR_PREF_ORD["high"]` | 1.0000 |
| 1 | `"mrt" in must_have → 1.0` | 1.0000 |
| 2 | `"hawker" in must_have → 1.0` | 1.0000 |
| 3 | `"mall" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 4 | `"park" in must_have → 1.0` | 1.0000 |
| 5 | `"school" in must_have → 1.0` | 1.0000 |
| 6 | `"hospital" NOT in must_have → 0.5 (neutral)` | 0.5000 |

**Flat vector:**

| Dim | How computed | Value |
|-----|-------------|-------|
| 0 | `storey_midpoint(1, 3) = 2 / 50` | 0.0400 |
| 1 | `count_within=0 / _AMENITY_COUNT_CAP["mrt"]=3` | 0.0000 |
| 2 | `count_within=1 / _AMENITY_COUNT_CAP["hawker"]=5` | 0.2000 |
| 3 | `count_within=0 / _AMENITY_COUNT_CAP["mall"]=3` | 0.0000 |
| 4 | `count_within=0 / _AMENITY_COUNT_CAP["park"]=4` | 0.0000 |
| 5 | `count_within=0 / _AMENITY_COUNT_CAP["school"]=4` | 0.0000 |
| 6 | `count_within=0 / _AMENITY_COUNT_CAP["hospital"]=2` | 0.0000 |

**Why ≈0.55:** Nearly every active dim is mismatched — floor (1.0 vs 0.04), mrt (1.0 vs 0.0), park (1.0 vs 0.0), school (1.0 vs 0.0). Even hawker only partially matches (1.0 vs 0.2). Vectors point in very different directions.

---

#### Scenario 4 — No amenity preference (score ≈ 0.96)

**Inputs:** `ftype="3 ROOM"`, `regions=["north"]`, `floor="mid"`, `must_have=[]`, `budget=$300k`  
**Flat:** Blk 321 WOODLANDS DR 14, `storey_range_start=10, storey_range_end=12`, block amenities: mrt×1, hawker×2, mall×1, park×2, school×3, hospital×0  
*(Pre-filters already applied: ftype selects DB query, region restricts town list, budget/lease filter candidates)*

**Active criteria:** `budget>0` ✓ | `ftype≠"any"` ✓ | `regions≠[]` ✓ | `must_have=[]` ✗  
→ active = [budget, flat, region]  
→ W = [1.0, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25]  
*(amenity dims dampened to 0.25 — buyer expressed no amenity preference)*

**Buyer vector:**

| Dim | How computed | Value |
|-----|-------------|-------|
| 0 | `FLOOR_PREF_ORD["mid"]` | 0.6600 |
| 1 | `"mrt" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 2 | `"hawker" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 3 | `"mall" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 4 | `"park" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 5 | `"school" NOT in must_have → 0.5 (neutral)` | 0.5000 |
| 6 | `"hospital" NOT in must_have → 0.5 (neutral)` | 0.5000 |

**Flat vector:**

| Dim | How computed | Value |
|-----|-------------|-------|
| 0 | `storey_midpoint(10, 12) = 11 / 50` | 0.2200 |
| 1 | `count_within=1 / _AMENITY_COUNT_CAP["mrt"]=3` | 0.3333 |
| 2 | `count_within=2 / _AMENITY_COUNT_CAP["hawker"]=5` | 0.4000 |
| 3 | `count_within=1 / _AMENITY_COUNT_CAP["mall"]=3` | 0.3333 |
| 4 | `count_within=2 / _AMENITY_COUNT_CAP["park"]=4` | 0.5000 |
| 5 | `count_within=3 / _AMENITY_COUNT_CAP["school"]=4` | 0.7500 |
| 6 | `count_within=0 / _AMENITY_COUNT_CAP["hospital"]=2` | 0.0000 |

**Why ≈0.96:** Floor preference is the only dim at full weight (W=1.0) — buyer=0.66 mid vs flat=0.22 differs but it's just one dim. All 6 amenity dims are dampened (W=0.25), so the estate's varied amenity counts barely affect the cosine angle. With dampened amenities contributing little, vectors stay nearly parallel.

---