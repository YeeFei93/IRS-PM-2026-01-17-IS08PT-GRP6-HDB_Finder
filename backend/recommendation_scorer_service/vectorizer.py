"""
recommendation-scorer-service/vectorizer.py
=====================
Converts raw user form inputs and flat/town data into normalised
numeric vectors for Content-Based cosine similarity scoring.

Buyer Preference Vector (7-dim):
  [floor_pref,
   has_mrt, has_hawker, has_mall, has_park, has_school, has_hospital]

Eligible Flat Vector (7-dim):
  [floor,
   nearby_mrt, nearby_hawker, nearby_mall, nearby_park, nearby_school, nearby_hospital]
   # nearby_X = count of amenity X within threshold distance / cap (normalised 0–1)

Flat type and region are NOT vector dimensions — they are hard pre-filters
in recommender.py (flat type selects the DB query, region restricts the
candidate town list) and add no cosine discrimination.

All values normalised to 0–1.

Design rationale, scoring formula, active criteria rules, and worked
examples are documented in README.md ("Recommendation Scoring" section).
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
# Matches the label distances shown in the UI (5 km/h → 12 min/km).
_AMENITY_MAX_KM: dict[str, float] = {
    "mrt":      1.0,   # ≤1km label (12 min)
    "hawker":   1.0,   # ≤1km label (12 min)
    "mall":     1.5,   # ≤1.5km label (18 min)
    "park":     1.0,   # ≤1km label (12 min)
    "school":   1.0,   # ≤1km label (12 min)
    "hospital": 3.0,   # ≤3km label (36 min)
}

# ── Count cap for normalisation ─────────────────────────────────────
# count_within / cap → clamped to [0, 1].
# Reflects diminishing returns: ≥ cap amenities within threshold ≈ 1.0.
_AMENITY_COUNT_CAP: dict[str, int] = {
    "mrt":      3,    # 3+ MRT stations within 1km is excellent
    "hawker":   5,    # hawker centres are dense in HDB estates
    "mall":     5,    # data shows median=3, p90=4 → raised to 5 for discrimination
    "park":     5,    # data p90=4, p95=5 → raised to 5 for discrimination
    "school":   6,    # data shows p75=4 already at old cap → raised to 6
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
    "BUKIT TIMAH":      "central",
    "CENTRAL AREA":     "central",
    "MARINE PARADE":    "central",
    "QUEENSTOWN":       "central",
    "TOA PAYOH":        "central",
}

# ── Max storey used for floor normalisation ──────────────────────────
_STOREY_MAX = 50.0  # highest HDB block is ~50 storeys

# ── Vector dimension labels (for explainability) ────────────────────
BUYER_VEC_LABELS: list[str] = [
    "floor_pref",
    "has_mrt", "has_hawker", "has_mall", "has_park", "has_school", "has_hospital",
]

FLAT_VEC_LABELS: list[str] = [
    "floor",
    "nearby_mrt", "nearby_hawker", "nearby_mall", "nearby_park", "nearby_school", "nearby_hospital",
]


def buyer_vector(profile: dict, budget: float = 0.0) -> list[float]:
    """Convert a BuyerProfile dict into a 7-dim list of floats in [0, 1].

    Flat type and region are excluded — they are hard pre-filters in
    recommender.py and add no cosine discrimination (all candidates
    share the same flat type and region after filtering).

    Parameters
    ----------
    profile : dict
        The raw BuyerProfile payload (matches ``api/routes.py BuyerProfile``).
        Expected keys: ``floor`` (or ``floor_pref``), ``must_have``.
    budget : float, optional
        Effective budget (unused here but kept for future extensions).

    Returns
    -------
    list[float]
        Length 7, all values in [0.0, 1.0].
    """
    vec: list[float] = [0.0] * 7

    # 0 — floor_pref
    floor = profile.get("floor", profile.get("floor_pref", "any"))
    vec[0] = FLOOR_PREF_ORD.get(floor, 0.5)

    # 1–6 — amenity dims from mustAmenities (mrt, hawker, mall, park, school, hospital)
    # 1.0 = buyer must have this amenity nearby
    # 0.5 = neutral (no preference — not 0.0 so the flat's amenity richness
    #        on these dims doesn't inflate the cosine denominator unfairly)
    must_have: list[str] = profile.get("must_have", [])
    must_set = set(must_have)
    for i, amenity in enumerate(AMENITY_DIMS):
        vec[1 + i] = 1.0 if amenity in must_set else 0.5

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

def flat_vector(price_data: dict, amenities: dict) -> list[float]:
    """Convert a town's data into a 7-dim Eligible Flat Vector in [0, 1].

    This is the flat-side counterpart to ``buyer_vector()``. One vector is
    produced per candidate town (aggregated over all eligible flats in that
    town using the price analysis summary from ``core/prices.py``).

    Flat type and region are handled by hard pre-filters in recommender.py
    (flat type selects the DB query, region restricts the candidate town
    list) and are therefore excluded from the vector.

    Parameters
    ----------
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
        Length 7, all values in [0.0, 1.0].

    Vector layout
    -------------
    0  floor           — midpoint of avg storey_range / 50
    1  nearby_mrt      — count within 1.0km / 3  (cap 3)
    2  nearby_hawker   — count within 1.0km / 5  (cap 5)
    3  nearby_mall     — count within 1.5km / 3  (cap 3)
    4  nearby_park     — count within 1.0km / 5  (cap 5)
    5  nearby_school   — count within 1.0km / 4  (cap 4)
    6  nearby_hospital — count within 3.0km / 2  (cap 2)
    """
    vec: list[float] = [0.0] * 7

    # 0 — floor (midpoint of avg storey_range / 50)
    avg_storey = price_data.get("avg_storey", None)
    if avg_storey is None:
        storey_range_str = price_data.get("storey_range", "")
        avg_storey = _storey_midpoint(storey_range_str)
    vec[0] = min(max(float(avg_storey) / _STOREY_MAX, 0.0), 1.0)

    # 1–6 — amenity count scores (mrt, hawker, mall, park, school, hospital)
    # count_within / cap → 0–1.  Mirrors buyer_vector dims 1–6 (must_have flags).
    for i, amenity in enumerate(AMENITY_DIMS):
        vec[1 + i] = _amenity_count_score(amenity, amenities)

    return vec
