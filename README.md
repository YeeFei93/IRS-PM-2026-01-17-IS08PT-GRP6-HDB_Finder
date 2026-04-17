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

## Data Sources

| File | Source | Dataset ID |
|---|---|---|
| `resale_prices.csv` | data.gov.sg | `d_8b84c4ee58e3cfc0ece0d773c8ca6abc` |
| `planning_areas.geojson` | data.gov.sg | `d_4765db0e87b9c86336792efe8a1f7a66` |
| `hawker_centres.geojson` | data.gov.sg (NEA) | `d_4a086da0a5553be1d89383cd90d07ebc` |
| `train_stations.geojson` | data.gov.sg (LTA) | `d_b39d3a0871985372d7e1637193335da5` |
| `train_station_lines.geojson` | data.gov.sg (LTA) | `d_d312a5b127e1ae74299b8ae664cedd4e` |
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
| `budget` | effective\_budget > 0 | none (pre-filter + budget adjustment) |
| `flat` | ftype ≠ "any" | — |
| `floor` | floor\_pref ≠ "any" | 0 |
| `region` | regions list non-empty | none (pre-filter only) |
| `mrt` | "mrt" in must\_have | 1 |
| `hawker` | "hawker" in must\_have | 2 |
| `mall` | "mall" in must\_have | 3 |
| `park` | "park" in must\_have | 4 |
| `school` | "school" in must\_have | 5 |
| `hospital` | "hospital" in must\_have | 6 |

Each amenity criterion is activated **individually** — selecting "hawker" as must-have only sets W[2] = 1.0; the other amenity dims remain at 0.25. This avoids inflating scores for amenities the buyer never expressed a preference for.

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

### Coverage factor

Cosine similarity is scale-invariant: when all dimensions share the same weight (all active or all inactive), the score collapses to the unweighted version and clusters high (85–95) for any positive vectors. The **coverage factor** compensates by scaling the cosine score down when the buyer has expressed few preferences, reflecting lower confidence in the match signal.

$$\text{coverage} = 0.40 + 0.60 \times \frac{n_{\text{active\_dims}}}{7}$$

| Active dims | Coverage factor | Effect |
|-------------|----------------|--------|
| 0 | 0.40 | Score capped ~40/100 (low confidence) |
| 1 | 0.486 | Score capped ~49/100 |
| 3 | 0.657 | Score capped ~66/100 |
| 5 | 0.829 | Score capped ~83/100 |
| 7 | 1.000 | No reduction (full confidence) |

This ensures that a buyer who only selects "hawker" as must-have cannot receive misleadingly high scores (e.g. 95/100) — the system honestly communicates that the recommendation is based on limited preference data.

### Budget adjustment

Budget is a one-sided constraint (cheaper is always acceptable), so it cannot be a cosine dimension. Instead, a **separate additive adjustment** rewards under-budget flats and penalises over-budget flats:

$$\text{adjustment} = \begin{cases}
+5\text{ pts} & \text{if price} \leq 70\%\ \text{of budget (best value)} \\
\text{linear } +5 \to 0 & \text{if } 70\%–100\% \\
0 & \text{if price} = 100\%\ \text{of budget} \\
\text{linear } 0 \to -5 & \text{if } 100\%–105\% \\
-5\text{ pts} & \text{if price} > 105\%\ \text{of budget (capped)}
\end{cases}$$

The adjustment is applied **per flat** (not per estate) using the flat's actual `resale_price`:

$$\text{final\_score} = \text{clamp}\bigl(\text{cosine} \times \text{coverage} + \text{budget\_adj},\ 0,\ 1\bigr)$$

### Score explainability

The UI provides three layers of scoring transparency:

1. **Per-dimension breakdown table** — shown on each flat card. Each row shows the dimension (floor, mrt, hawker, …, budget), buyer vs flat values, whether it's a priority (★), and its weighted contribution to the total score.

2. **Confidence indicator** — displayed below the total: *"Low / Moderate / High confidence · N of 7 preferences active"*. This maps directly to the coverage factor and helps the buyer understand how much trust to place in the score.

3. **Estate summary (whyText)** — a natural-language sentence on each estate card explaining the scoring methodology, budget fit, and supply context. Example: *"Score is driven by proximity to hawker centres using weighted cosine similarity, with 1 of 7 preference dimensions active. Median price is ~$26,765 under your budget, offering good value. 105 qualifying 4 ROOM listings were evaluated in BEDOK."*

### Worked examples

#### Scenario 1 — Strong match (score ≈ 0.93)

**Inputs:** `ftype="4 ROOM"`, `regions=["central"]`, `floor="high"`, `must_have=["mrt","hawker","park"]`, `budget=$500k`  
**Flat:** Blk 123 TOA PAYOH CENTRAL (central), `storey_range_start=37, storey_range_end=42`, block amenities: mrt×2, hawker×4, mall×1, park×3, school×3, hospital×1, `resale_price=$400k`  
*(Pre-filters already applied: ftype selects DB query, region restricts town list, budget/lease filter candidates; scoring is per flat)*

**Active criteria:** `budget>0` ✓ | `ftype≠"any"` ✓ | `floor≠"any"` ✓ | `regions≠[]` ✓ | `mrt∈must_have` ✓ | `hawker∈must_have` ✓ | `park∈must_have` ✓  
→ active = [budget, flat, floor, region, mrt, hawker, park]  
→ W = [1.0, 1.0, 1.0, 0.25, 1.0, 0.25, 0.25]  
*(Only mrt/hawker/park get W=1.0; mall/school/hospital stay at 0.25)*

**Coverage:** 4 of 7 vector dims active (floor, mrt, hawker, park) → coverage = 0.40 + 0.60 × 4/7 = **0.743**

**Budget adjustment:** price/budget = 400k/500k = 80% → between 70–100%: reward = (1.0 − 0.80)/(1.0 − 0.70) × 0.05 = **+0.033**

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

**Why ≈0.93:** Raw cosine ≈ 0.98 (floor close, active amenity dims well-aligned). Coverage ≈ 0.743 scales it to ≈ 0.73. Budget reward +0.033 bumps to ≈ 0.76. On a 0-100 display: **76/100**. *(Note: with all 7 dims active, coverage would be 1.0 and the score would reach ≈ 98 + 3 = ~100.)*

---

#### Scenario 2 — Moderate match (score ≈ 0.50)

**Inputs:** `ftype="4 ROOM"`, `regions=["east"]`, `floor="any"`, `must_have=["mrt"]`, `budget=$400k`  
**Flat:** Blk 456 JURONG WEST ST 41, `storey_range_start=1, storey_range_end=3`, block amenities: mrt×3, hawker×2, mall×1, park×1, school×2, hospital×0, `resale_price=$350k`  
*(Pre-filters already applied: ftype selects DB query, budget/lease filter candidates)*

**Active criteria:** `budget>0` ✓ | `ftype≠"any"` ✓ | `floor="any"` ✗ | `regions≠[]` ✓ | `mrt∈must_have` ✓  
→ active = [budget, flat, region, mrt]  
→ W = [0.25, 1.0, 0.25, 0.25, 0.25, 0.25, 0.25]  
*(Only mrt dim gets W=1.0; floor is inactive because "any")*

**Coverage:** 1 of 7 vector dims active (mrt only) → coverage = 0.40 + 0.60 × 1/7 = **0.486**

**Budget adjustment:** price/budget = 350k/400k = 87.5% → reward = (1.0 − 0.875)/(1.0 − 0.70) × 0.05 = **+0.021**

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

**Why ≈0.50:** MRT matches perfectly (1.0 vs 1.0) but that's the only active dim. Raw cosine ≈ 0.78 but coverage = 0.486 scales it to ≈ 0.38. Budget reward +0.021 bumps to ≈ 0.40. On a 0-100 display: **40/100**. The low coverage reflects that only 1 preference dimension was expressed.

---

#### Scenario 3 — Poor match (score ≈ 0.43)

**Inputs:** `ftype="5 ROOM"`, `regions=["central"]`, `floor="high"`, `must_have=["mrt","hawker","park","school"]`, `budget=$600k`  
**Flat:** Blk 789 JURONG WEST ST 52, `storey_range_start=1, storey_range_end=3`, block amenities: mrt×0, hawker×1, mall×0, park×0, school×0, hospital×0, `resale_price=$580k`  
*(Pre-filters already applied: ftype selects DB query, budget/lease filter candidates)*

**Active criteria:** `budget>0` ✓ | `ftype≠"any"` ✓ | `floor≠"any"` ✓ | `regions≠[]` ✓ | `mrt` ✓ | `hawker` ✓ | `park` ✓ | `school` ✓  
→ active = [budget, flat, floor, region, mrt, hawker, park, school]  
→ W = [1.0, 1.0, 1.0, 0.25, 1.0, 1.0, 0.25]  
*(floor/mrt/hawker/park/school at 1.0; mall/hospital at 0.25)*

**Coverage:** 5 of 7 vector dims active (floor, mrt, hawker, park, school) → coverage = 0.40 + 0.60 × 5/7 = **0.829**

**Budget adjustment:** price/budget = 580k/600k = 96.7% → reward = (1.0 − 0.967)/(1.0 − 0.70) × 0.05 = **+0.006**

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

**Why ≈0.43:** Nearly every active dim is mismatched — floor (1.0 vs 0.04), mrt (1.0 vs 0.0), park (1.0 vs 0.0), school (1.0 vs 0.0). Even hawker only partially matches (1.0 vs 0.2). Raw cosine ≈ 0.55, coverage 0.829 → ≈ 0.46, budget reward +0.006 → **~46/100**.

---

#### Scenario 4 — No amenity preference (score ≈ 0.37)

**Inputs:** `ftype="3 ROOM"`, `regions=["north"]`, `floor="mid"`, `must_have=[]`, `budget=$300k`  
**Flat:** Blk 321 WOODLANDS DR 14, `storey_range_start=10, storey_range_end=12`, block amenities: mrt×1, hawker×2, mall×1, park×2, school×3, hospital×0, `resale_price=$180k`  
*(Pre-filters already applied: ftype selects DB query, region restricts town list, budget/lease filter candidates)*

**Active criteria:** `budget>0` ✓ | `ftype≠"any"` ✓ | `floor≠"any"` ✓ | `regions≠[]` ✓ | `must_have=[]` — no amenities  
→ active = [budget, flat, floor, region]  
→ W = [1.0, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25]  
*(only floor dim active; all 6 amenity dims dampened to 0.25)*

**Coverage:** 1 of 7 vector dims active (floor only) → coverage = 0.40 + 0.60 × 1/7 = **0.486**

**Budget adjustment:** price/budget = 180k/300k = 60% → ≤ 70% → full reward = **+0.050**

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

**Why ≈0.37:** Raw cosine ≈ 0.96 (floor is the only fully weighted dim; dampened amenities contribute little to the angle). But coverage = 0.486 scales it to ≈ 0.47. Budget reward +0.05 bumps to ≈ 0.52. On 0-100 display: **~52/100**. Previously (without coverage factor) this would have scored ~96 — misleadingly high for a buyer who expressed only one preference.

---