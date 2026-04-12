"""
recommendation-scorer-service/vectorizer.py
=====================
Converts raw user form inputs and flat/town data into normalised
numeric vectors for Content-Based cosine similarity scoring.

Buyer Preference Vector (10-dim):
  [flat_type, region, floor_pref, remaining_lease,
   has_mrt, has_hawker, has_mall, has_park, has_school, has_hospital]

Eligible Flat Vector (10-dim):
  [flat_type, region, floor, remaining_lease,
   nearby_mrt, nearby_hawker, nearby_mall, nearby_park, nearby_school, nearby_hospital]
   # nearby_X = count of amenity X within threshold distance / cap (normalised 0–1)

All values normalised to 0–1.

Reference: detectActive() and rawForCriterion() in frontend engine.js

────────────────────────────────────────────────────────────────────────
HOW COSINE SIMILARITY SCORING WORKS — WORKED EXAMPLES
────────────────────────────────────────────────────────────────────────

Overview
--------
Cosine similarity measures the angle between two vectors, ignoring
magnitude.  Two vectors pointing in the same direction → score 1.0;
orthogonal → 0.0.  We weight each dimension so that criteria the
buyer actually configured (active) matter more than defaults (inactive).

  score = cos(W⊙buyer, W⊙flat)
  W[i]  = 1.0 if criterion is active, 0.25 if inactive

Active criteria detection (scorer.py detect_active_criteria):
  - "budget"  → active if effective_budget > 0       (no vector dim)
  - "flat"    → active if ftype ≠ "any"              (dims 0, 2)
  - "region"  → active if regions list is non-empty   (dim 1)
  - "lease"   → active if min_lease > 60              (dim 3)
  - "amenity" → active if must_have list is non-empty  (dims 4–9 ALL share this)

IMPORTANT: dims 4–9 all map to the single "amenity" criterion.  If the
buyer selects even ONE must-have amenity, ALL 6 amenity dims get W=1.0.
This means non-preferred amenities still contribute at full weight.


Scenario 1 — Strong match (score = 0.978)
------------------------------------------
Inputs:
  Buyer: ftype="4 ROOM", regions=["central"], floor="high",
         min_lease=80, must_have=["mrt","hawker","park"], budget=$500k
  Flat:  town="TOA PAYOH" (central), storey_range="37 TO 42",
         avg_lease_years=85,
         amenities: mrt×2, hawker×4, mall×1, park×3, school×3, hospital×1

Active criteria:
  budget>0 ✓ | ftype≠"any" ✓ | regions≠[] ✓ | 80>60 ✓ | must_have≠[] ✓
  → active = [budget, flat, region, lease, amenity]
  → W = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    (every dim's criterion is active, so all weights are 1.0)

Buyer vector (buyer_vector):
  dim  how computed                                      value
  0    FLAT_TYPE_ORD["4 ROOM"] = 4/7                     0.5714
  1    len(regions)>0 → 1.0                              1.0000
  2    FLOOR_PREF_ORD["high"]                            1.0000
  3    min_lease / 99 = 80/99                            0.8081
  4    "mrt" in must_have → 1.0                          1.0000
  5    "hawker" in must_have → 1.0                       1.0000
  6    "mall" NOT in must_have → 0.5 (neutral)           0.5000
  7    "park" in must_have → 1.0                         1.0000
  8    "school" NOT in must_have → 0.5 (neutral)         0.5000
  9    "hospital" NOT in must_have → 0.5 (neutral)       0.5000

Flat vector (flat_vector):
  dim  how computed                                      value
  0    FLAT_TYPE_ORD["4 ROOM"] = 4/7                     0.5714
  1    _TOWN_TO_REGION["TOA PAYOH"]="central" ∈ buyer    1.0000
       regions → match
  2    _storey_midpoint("37 TO 42")=39.5 / 50            0.7900
  3    avg_lease_years / 99 = 85/99                      0.8586
  4    count_within=2 / _AMENITY_COUNT_CAP["mrt"]=3      0.6667
  5    count_within=4 / _AMENITY_COUNT_CAP["hawker"]=5   0.8000
  6    count_within=1 / _AMENITY_COUNT_CAP["mall"]=3     0.3333
  7    count_within=3 / _AMENITY_COUNT_CAP["park"]=4     0.7500
  8    count_within=3 / _AMENITY_COUNT_CAP["school"]=4   0.7500
  9    count_within=1 / _AMENITY_COUNT_CAP["hospital"]=2 0.5000

Why 0.978: flat_type matches exactly (0.57==0.57), region matches
(1.0==1.0), floor/lease are close.  Active amenity dims (mrt, hawker,
park) have buyer=1.0 vs flat 0.67–0.80 — close to parallel.
Non-preferred amenities (mall buyer=0.5, flat=0.33) contribute at
full W=1.0 but the small values don't drag much.


Scenario 2 — Moderate match (score = 0.780)
--------------------------------------------
Inputs:
  Buyer: ftype="4 ROOM", regions=["east"], floor="any",
         min_lease=50, must_have=["mrt"], budget=$400k
  Flat:  town="JURONG WEST" (west ≠ east), storey_range="04 TO 06",
         avg_lease_years=70,
         amenities: mrt×3, hawker×3, mall×1, park×2, school×3, hospital×0

Active criteria:
  budget>0 ✓ | ftype≠"any" ✓ | regions≠[] ✓ | 50>60 ✗ | must_have≠[] ✓
  → active = [budget, flat, region, amenity]  (NOT lease)
  → W = [1.0, 1.0, 1.0, 0.25, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    (dim 3 lease is 0.25 because min_lease 50 ≤ default 60)

Buyer vector:
  dim  how computed                                      value
  0    FLAT_TYPE_ORD["4 ROOM"] = 4/7                     0.5714
  1    len(regions)>0 → 1.0                              1.0000
  2    FLOOR_PREF_ORD["any"] = 0.5                       0.5000
  3    min_lease / 99 = 50/99                            0.5051
  4    "mrt" in must_have → 1.0                          1.0000
  5    "hawker" NOT in must_have → 0.5                   0.5000
  6    "mall" NOT in must_have → 0.5                     0.5000
  7    "park" NOT in must_have → 0.5                     0.5000
  8    "school" NOT in must_have → 0.5                   0.5000
  9    "hospital" NOT in must_have → 0.5                 0.5000

Flat vector:
  dim  how computed                                      value
  0    FLAT_TYPE_ORD["4 ROOM"] = 4/7                     0.5714
  1    _TOWN_TO_REGION["JURONG WEST"]="west" ∉ ["east"]  0.0000
       → no match
  2    _storey_midpoint("04 TO 06")=5.0 / 50             0.1000
  3    avg_lease_years / 99 = 70/99                      0.7071
  4    count_within=3 / cap=3                            1.0000
  5    count_within=3 / cap=5                            0.6000
  6    count_within=1 / cap=3                            0.3333
  7    count_within=2 / cap=4                            0.5000
  8    count_within=3 / cap=4                            0.7500
  9    count_within=0 / cap=2                            0.0000

Why 0.780: MRT is a perfect match (1.0==1.0) but region is the big
drag — buyer=1.0 vs flat=0.0 on an active dim (W=1.0).  Floor dim
also hurts (buyer 0.5 vs flat 0.1) and it's active because "flat"
criterion is active (ftype="4 ROOM"), so dim 2 gets W=1.0 even though
the buyer chose "any" floor.  Lease mismatch barely matters (W=0.25).
Note: if region matched, score would jump to ~0.93.


Scenario 3 — Poor match (score = 0.545)
----------------------------------------
Inputs:
  Buyer: ftype="5 ROOM", regions=["central"], floor="high",
         min_lease=90, must_have=["mrt","hawker","park","school"],
         budget=$600k
  Flat:  town="JURONG WEST" (west ≠ central), storey_range="01 TO 03",
         avg_lease_years=40,
         amenities: mrt×0, hawker×1, mall×1, park×0, school×0, hospital×1

Active criteria:
  budget>0 ✓ | ftype≠"any" ✓ | regions≠[] ✓ | 90>60 ✓ | must_have≠[] ✓
  → active = [budget, flat, region, lease, amenity]
  → W = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]

Buyer vector:
  dim  how computed                                      value
  0    FLAT_TYPE_ORD["5 ROOM"] = 5/7                     0.7143
  1    len(regions)>0 → 1.0                              1.0000
  2    FLOOR_PREF_ORD["high"]                            1.0000
  3    min_lease / 99 = 90/99                            0.9091
  4    "mrt" in must_have → 1.0                          1.0000
  5    "hawker" in must_have → 1.0                       1.0000
  6    "mall" NOT in must_have → 0.5                     0.5000
  7    "park" in must_have → 1.0                         1.0000
  8    "school" in must_have → 1.0                       1.0000
  9    "hospital" NOT in must_have → 0.5                 0.5000

Flat vector:
  dim  how computed                                      value
  0    FLAT_TYPE_ORD["2 ROOM"] = 2/7 (wrong type)        0.2857
  1    "west" ∉ ["central"] → no match                   0.0000
  2    _storey_midpoint("01 TO 03")=2.0 / 50             0.0400
  3    avg_lease_years / 99 = 40/99                      0.4040
  4    count_within=0 / cap=3                            0.0000
  5    count_within=1 / cap=5                            0.2000
  6    count_within=1 / cap=3                            0.3333
  7    count_within=0 / cap=4                            0.0000
  8    count_within=0 / cap=4                            0.0000
  9    count_within=1 / cap=2                            0.5000

Why 0.545: nearly every active dim is mismatched.  flat_type
(0.71 vs 0.29), region (1.0 vs 0.0), floor (1.0 vs 0.04), lease
(0.91 vs 0.40), mrt (1.0 vs 0.0), park (1.0 vs 0.0), school
(1.0 vs 0.0).  The vectors point in very different directions.
The only positive contributions are hawker (1.0 vs 0.2 = small)
and hospital (0.5 vs 0.5 = matches but small product).


Scenario 4 — No amenity preference (score = 0.957)
---------------------------------------------------
Inputs:
  Buyer: ftype="3 ROOM", regions=["north"], floor="mid",
         min_lease=50, must_have=[], budget=$300k
  Flat:  town="WOODLANDS" (north), storey_range="13 TO 15",
         avg_lease_years=60,
         amenities: mrt×1, hawker×3, mall×2, park×2, school×2, hospital×0

Active criteria:
  budget>0 ✓ | ftype≠"any" ✓ | regions≠[] ✓ | 50>60 ✗ | must_have==[] ✗
  → active = [budget, flat, region]  (NOT lease, NOT amenity)
  → W = [1.0, 1.0, 1.0, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25]
    (only flat/region dims amplified, rest dampened)

Buyer vector:
  dim  how computed                                      value
  0    FLAT_TYPE_ORD["3 ROOM"] = 3/7                     0.4286
  1    len(regions)>0 → 1.0                              1.0000
  2    FLOOR_PREF_ORD["mid"] = 0.66                      0.6600
  3    min_lease / 99 = 50/99                            0.5051
  4    must_have empty → 0.5 (neutral)                   0.5000
  5    must_have empty → 0.5                             0.5000
  6    must_have empty → 0.5                             0.5000
  7    must_have empty → 0.5                             0.5000
  8    must_have empty → 0.5                             0.5000
  9    must_have empty → 0.5                             0.5000

Flat vector:
  dim  how computed                                      value
  0    FLAT_TYPE_ORD["3 ROOM"] = 3/7                     0.4286
  1    _TOWN_TO_REGION["WOODLANDS"]="north" ∈ ["north"]  1.0000
  2    _storey_midpoint("13 TO 15")=14.0 / 50            0.2800
  3    avg_lease_years / 99 = 60/99                      0.6061
  4    count_within=1 / cap=3                            0.3333
  5    count_within=3 / cap=5                            0.6000
  6    count_within=2 / cap=3                            0.6667
  7    count_within=2 / cap=4                            0.5000
  8    count_within=2 / cap=4                            0.5000
  9    count_within=0 / cap=2                            0.0000

Why 0.957: flat_type and region match perfectly, dominating the score
because they are the only active dims with W=1.0.  Floor dim is active
(grouped under "flat" criterion) — buyer 0.66 vs flat 0.28 causes a
small drag.  All 6 amenity dims have W=0.25, so the flat's varied
amenity counts (ranging 0.0 to 0.67) barely affect the final score.

Key insight: when no amenities are selected, the amenity dims are all
0.5 in the buyer vector AND dampened by W=0.25.  An estate with poor
amenities and one with excellent amenities score nearly the same.


Count-based amenity scoring detail
-----------------------------------
Amenity dims (4–9) use count-within-threshold / cap:

  score = min(count_within / cap, 1.0)

  Example for dim 4 (MRT), cap = 3:
    0 MRTs within 0.8km → 0/3 = 0.00  (no nearby MRT)
    1 MRT  within 0.8km → 1/3 = 0.33  (one station, partial score)
    2 MRTs within 0.8km → 2/3 = 0.67  (good connectivity)
    3+MRTs within 0.8km → 3/3 = 1.00  (excellent, saturated)

  This rewards amenity density: an estate with 2 MRTs nearby scores
  higher than one with just 1, reflecting genuine liveability.

  Caps per type: MRT=3, hawker=5, mall=3, park=4, school=4, hospital=2.
  Thresholds: MRT/hawker/park/school=0.8km, mall=1.2km, hospital=2.4km.
────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from weights import DEFAULTS


# 7 types from DB, evenly spaced 1/7 ≈ 0.14 per step.
# Order reflects size/desirability: 1RM < 2RM < 3RM < 4RM < 5RM < EXEC < MULTIGEN
FLAT_TYPE_ORD: dict[str, float] = {
    "1 ROOM":           round(1/7, 4),   # 0.1429
    "2 ROOM":           round(2/7, 4),   # 0.2857
    "3 ROOM":           round(3/7, 4),   # 0.4286
    "4 ROOM":           round(4/7, 4),   # 0.5714
    "5 ROOM":           round(5/7, 4),   # 0.7143
    "EXECUTIVE":        round(6/7, 4),   # 0.8571
    "MULTI-GENERATION": 1.0,
}

# ── Floor preference ordinal encoding ───────────────────────────────
FLOOR_PREF_ORD: dict[str, float] = {
    "low":  0.33,
    "mid":  0.66,
    "high": 1.0,
    "any":  0.5,
}

# ── Amenity dimension order (must stay stable) ──────────────────────
AMENITY_DIMS: list[str] = ["mrt", "hawker", "mall", "park", "school", "hospital"]

# ── Max distances used for proximity normalisation (km) ─────────────
# Must match frontend AMENITY_THRESHOLDS (constants.js) and distances.py.
# Walking speed: 5 km/h with 20% buffer → effective 4 km/h (15 min/km).
#   12 min → 0.8 km  |  18 min → 1.2 km  |  36 min → 2.4 km
_AMENITY_MAX_KM: dict[str, float] = {
    "mrt":      0.8,   # ≤1km label (12 min @ 15 min/km)
    "hawker":   0.8,   # ≤1km label (12 min)
    "mall":     1.2,   # ≤1.5km label (18 min)
    "park":     0.8,   # ≤1km label (12 min)
    "school":   0.8,   # ≤1km label (12 min)
    "hospital": 2.4,   # ≤3km label (36 min)
}

# ── Count cap for normalisation ─────────────────────────────────────
# count_within / cap → clamped to [0, 1].
# Reflects diminishing returns: ≥ cap amenities within threshold ≈ 1.0.
_AMENITY_COUNT_CAP: dict[str, int] = {
    "mrt":      3,    # 3+ MRT stations within 1km is excellent
    "hawker":   5,    # hawker centres are dense in HDB estates
    "mall":     3,    # 3+ malls within 1.5km is very good
    "park":     4,    # parks are common, reward density up to 4
    "school":   4,    # primary schools, 4+ is saturated
    "hospital": 2,    # hospitals are sparse, 2 within 3km is excellent
}

# ── Town → region mapping (mirrors frontend/src/constants.js REGIONS) ──────
# Values must exactly match the region keys the frontend sends in BuyerProfile.regions.
# Source: frontend REGIONS = { north, northeast, east, west, central }
_TOWN_TO_REGION: dict[str, str] = {
    # north
    "ANG MO KIO":       "north",
    "BISHAN":           "north",
    "SEMBAWANG":        "north",
    "WOODLANDS":        "north",
    "YISHUN":           "north",
    # northeast
    "HOUGANG":          "northeast",
    "PUNGGOL":          "northeast",
    "SENGKANG":         "northeast",
    "SERANGOON":        "northeast",
    # east
    "BEDOK":            "east",
    "GEYLANG":          "east",
    "KALLANG/WHAMPOA":  "east",
    "PASIR RIS":        "east",
    "TAMPINES":         "east",
    # west
    "BUKIT BATOK":      "west",
    "BUKIT PANJANG":    "west",
    "CHOA CHU KANG":    "west",
    "CLEMENTI":         "west",
    "JURONG EAST":      "west",
    "JURONG WEST":      "west",
    # central
    "BUKIT MERAH":      "central",
    "BUKIT TIMAH":      "central",   # in DB but not in frontend town list
    "CENTRAL AREA":     "central",
    "MARINE PARADE":    "central",
    "QUEENSTOWN":       "central",
    "TOA PAYOH":        "central",
}

# ── Max storey used for floor normalisation ──────────────────────────
_STOREY_MAX = 50.0  # highest HDB block is ~50 storeys

# ── Vector dimension labels (for explainability) ────────────────────
BUYER_VEC_LABELS: list[str] = [
    "flat_type", "region", "floor_pref", "remaining_lease",
    "has_mrt", "has_hawker", "has_mall", "has_park", "has_school", "has_hospital",
]

FLAT_VEC_LABELS: list[str] = [
    "flat_type", "region", "floor", "remaining_lease",
    "nearby_mrt", "nearby_hawker", "nearby_mall", "nearby_park", "nearby_school", "nearby_hospital",
]


def buyer_vector(profile: dict, budget: float = 0.0) -> list[float]:
    """Convert a BuyerProfile dict into a 10-dim list of floats in [0, 1].

    Parameters
    ----------
    profile : dict
        The raw BuyerProfile payload (matches ``api/routes.py BuyerProfile``).
        Expected keys: ``ftype``, ``regions``, ``floor`` (or ``floor_pref``),
        ``min_lease``, ``must_have``.
    budget : float, optional
        Effective budget (unused here but kept for future extensions).

    Returns
    -------
    list[float]
        Length 10, all values in [0.0, 1.0].
    """
    vec: list[float] = [0.0] * 10

    # 0 — flat_type
    ftype = profile.get("ftype", "any")
    vec[0] = FLAT_TYPE_ORD.get(ftype, round(4/7, 4))  # "any" → 4/7≈0.5714 (true midpoint of 7-type scale)

    # 1 — region: 1.0 if buyer stated ≥1 region preference, 0.5 if no preference.
    # Paired with flat_vector dim 1 which encodes match/no-match against these regions.
    # Using binary 1.0/0.5 (not ordinal) ensures cosine rewards matching flats, not
    # flats that happen to have a large ordinal value on this dimension.
    regions = profile.get("regions", [])
    vec[1] = 1.0 if regions else 0.5

    # 2 — floor_pref
    floor = profile.get("floor", profile.get("floor_pref", "any"))
    vec[2] = FLOOR_PREF_ORD.get(floor, 0.5)

    # 3 — remaining_lease (min_lease / 99)
    min_lease = profile.get("min_lease", 20)  # 20 = slider minimum (most permissive)
    vec[3] = min(max(min_lease / 99.0, 0.0), 1.0)

    # 4–9 — amenity dims from mustAmenities (mrt, hawker, mall, park, school, hospital)
    # 1.0 = buyer must have this amenity nearby
    # 0.5 = neutral (no preference — not 0.0 so the flat's amenity richness
    #        on these dims doesn't inflate the cosine denominator unfairly)
    must_have: list[str] = profile.get("must_have", [])
    must_set = set(must_have)
    for i, amenity in enumerate(AMENITY_DIMS):
        vec[4 + i] = 1.0 if amenity in must_set else 0.5

    return vec


# ── Helper: parse storey_range → midpoint floor ─────────────────────────────

def _storey_midpoint(storey_range: str) -> float:
    """
    Parse HDB storey_range string e.g. '07 TO 09' → midpoint 8.0.
    Returns 5.0 as a safe default for unparseable values.
    """
    try:
        parts = storey_range.upper().replace("TO", " ").split()
        nums = [int(p) for p in parts if p.isdigit()]
        if len(nums) >= 2:
            return (nums[0] + nums[1]) / 2.0
        if len(nums) == 1:
            return float(nums[0])
    except (ValueError, AttributeError):
        pass
    return 5.0  # neutral default (low-mid floor)


# ── Helper: parse remaining_lease string → years ────────────────────────────

def _parse_lease_years(remaining_lease) -> float:
    """
    Accept either:
      - int/float (already years)
      - str like '61 years 06 months' or '61 years'

    Returns years as float, 0.0 on failure.
    """
    if isinstance(remaining_lease, (int, float)):
        return float(remaining_lease)
    if isinstance(remaining_lease, str):
        s = remaining_lease.lower()
        try:
            # Extract year component
            year_part = 0.0
            month_part = 0.0
            if "year" in s:
                year_part = float(s.split("year")[0].strip())
            if "month" in s:
                month_str = s.split("month")[0]
                # Take last token before "month"
                month_part = float(month_str.strip().split()[-1]) / 12.0
            return year_part + month_part
        except (ValueError, IndexError):
            pass
    return 0.0


# ── Helper: count-based amenity score ───────────────────────────────────────

def _amenity_count_score(amenity_key: str, amenities: dict) -> float:
    """
    Convert amenity count-within-threshold to a 0–1 score.

    Uses count_within from distances.nearest_amenities() which counts how
    many amenities of this type are within the threshold distance.

    score = min(count_within / cap, 1.0)

    Falls back to proximity-based scoring if count_within is not available
    (backward compatibility with older distance data).
    """
    entry = amenities.get(amenity_key, {})

    # Primary: count-based scoring
    count_within = entry.get("count_within")
    if count_within is not None:
        cap = _AMENITY_COUNT_CAP.get(amenity_key, 3)
        return min(round(count_within / cap, 4), 1.0)

    # Fallback: proximity scoring (for backward compatibility)
    dist_km = entry.get("dist_km")
    if dist_km is None:
        return 0.5  # no data → neutral
    max_km = _AMENITY_MAX_KM.get(amenity_key, 1.0)
    return max(0.0, round(1.0 - dist_km / max_km, 4))


# ── Main function ────────────────────────────────────────────────────────────

def flat_vector(town: str, price_data: dict, amenities: dict,
                buyer_regions: list[str] | None = None) -> list[float]:
    """Convert a town's data into a 10-dim Eligible Flat Vector in [0, 1].

    This is the flat-side counterpart to ``buyer_vector()``. One vector is
    produced per candidate town (aggregated over all eligible flats in that
    town using the price analysis summary from ``core/prices.py``).

    Parameters
    ----------
    town : str
        HDB town name (uppercase), e.g. ``'WOODLANDS'``.
    price_data : dict
        Output of ``core/prices.analyse_town_prices(town, ftype)``.
        Expected keys: ``ftype``, ``avg_area``, ``avg_storey_range``,
        ``avg_lease_years``, ``storey_range``.
    amenities : dict
        Output of ``geo/distances.nearest_amenities(lat, lng)``.
        Keys: mrt, hawker, park, hospital, school, mall — each with
        ``dist_km``, ``walk_mins``, ``within_threshold``.

    Returns
    -------
    list[float]
        Length 10, all values in [0.0, 1.0].

    Vector layout
    -------------
    0  flat_type       — ordinal: 1RM=1/7 … MULTI-GEN=1.0; unknown/any=4/7
    1  region          — 1.0 if town's region is in buyer_regions, 0.0 if not, 0.5 if no buyer preference
    2  floor           — midpoint of avg storey_range / 50
    3  remaining_lease — avg remaining lease years / 99
    4  nearby_mrt      — count within 0.8km / 3  (cap 3)
    5  nearby_hawker   — count within 0.8km / 5  (cap 5)
    6  nearby_mall     — count within 1.2km / 3  (cap 3)
    7  nearby_park     — count within 0.8km / 4  (cap 4)
    8  nearby_school   — count within 0.8km / 4  (cap 4)
    9  nearby_hospital — count within 2.4km / 2  (cap 2)
    """
    vec: list[float] = [0.0] * 10

    # 0 — flat_type
    ftype = price_data.get("ftype", "4 ROOM")
    vec[0] = FLAT_TYPE_ORD.get(ftype, round(4/7, 4))  # unknown type → 4/7 neutral

    # 1 — region: match/no-match against buyer_regions.
    # 1.0 = flat's region is in buyer's preferred list (reward)
    # 0.0 = flat's region is NOT in buyer's preferred list (penalise)
    # 0.5 = buyer stated no preference (neutral for all flats)
    region = _TOWN_TO_REGION.get(town.upper(), "")
    if not buyer_regions:
        vec[1] = 0.5  # no buyer preference → equal for all towns
    elif region.lower() in {r.lower() for r in buyer_regions}:
        vec[1] = 1.0  # match
    else:
        vec[1] = 0.0  # no match

    # 2 — floor (midpoint of avg storey_range / 50)
    # price_data may carry 'storey_range' (most common range string) or
    # 'avg_storey_range' (numeric average from queries.py).
    avg_storey = price_data.get("avg_storey", None)
    if avg_storey is None:
        storey_range_str = price_data.get("storey_range", "")
        avg_storey = _storey_midpoint(storey_range_str)
    vec[2] = min(max(float(avg_storey) / _STOREY_MAX, 0.0), 1.0)

    # 3 — remaining_lease
    lease_years = _parse_lease_years(price_data.get("avg_lease_years", 0))
    vec[3] = min(max(lease_years / 99.0, 0.0), 1.0)

    # 4–9 — amenity count scores (mrt, hawker, mall, park, school, hospital)
    # count_within / cap → 0–1.  Mirrors buyer_vector dims 4–9 (must_have flags).
    for i, amenity in enumerate(AMENITY_DIMS):
        vec[4 + i] = _amenity_count_score(amenity, amenities)

    return vec
