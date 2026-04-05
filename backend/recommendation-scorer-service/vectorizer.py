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

All values normalised to 0–1.

Reference: detectActive() and rawForCriterion() in frontend engine.js
"""

from __future__ import annotations

# ── Flat-type ordinal encoding ──────────────────────────────────────
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
# MRT is excluded here — dim 4 is encoded from max_mrt_mins slider, not must_have.
AMENITY_DIMS: list[str] = ["hawker", "mall", "park", "school", "hospital"]

# ── Max distances used for proximity normalisation (km) ─────────────
# Beyond these distances the amenity scores to 0.
# Based on max acceptable walking distance (~5 km/h pace):
#   1.0 km ≈ 12 min  |  1.5 km ≈ 18 min  |  2.0 km ≈ 24 min
_AMENITY_MAX_KM: dict[str, float] = {
    "mrt":      1.0,   # 12 min walk — standard SG "walking distance" to MRT
    "hawker":   1.0,   # 12 min walk
    "mall":     1.5,   # 18 min walk
    "park":     1.5,   # 18 min walk
    "school":   1.0,   # 12 min walk
    "hospital": 2.0,   # 24 min walk — max plausible walk to a hospital
}

# ── Town → region mapping (mirrors core/recommender.py REGIONS) ─────
# Values are the canonical region keys used in BuyerProfile.regions.
_TOWN_TO_REGION: dict[str, str] = {
    "ANG MO KIO":       "north",
    "SEMBAWANG":        "north",
    "WOODLANDS":        "north",
    "YISHUN":           "north",
    "SENGKANG":         "north",
    "PUNGGOL":          "north",
    "BUONA VISTA":      "south",
    "QUEENSTOWN":       "south",
    "TOA PAYOH":        "south",
    "BISHAN":           "south",
    "GEYLANG":          "south",
    "KALLANG":          "south",
    "KALLANG/WHAMPOA":  "south",
    "BEDOK":            "east",
    "PASIR RIS":        "east",
    "TAMPINES":         "east",
    "HOUGANG":          "east",
    "SERANGOON":        "east",
    "BUKIT BATOK":      "west",
    "BUKIT PANJANG":    "west",
    "CHOA CHU KANG":    "west",
    "CLEMENTI":         "west",
    "JURONG EAST":      "west",
    "JURONG WEST":      "west",
    "CENTRAL AREA":     "central",
    "BUKIT MERAH":      "central",
    "MARINE PARADE":    "central",
}

# ── Max storey used for floor normalisation ──────────────────────────
_STOREY_MAX = 50.0  # highest HDB block is ~50 storeys

# ── Vector dimension labels (for explainability) ────────────────────
BUYER_VEC_LABELS: list[str] = [
    "flat_type", "region", "floor_pref", "remaining_lease",
    "mrt_walk_pref", "has_hawker", "has_mall", "has_park", "has_school", "has_hospital",
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

    # 4 — mrt_walk_pref: derived from max_mrt_mins slider (3–30 min, default 30)
    # Converts walk-time limit to a proximity score matching the flat vector's
    # nearby_mrt dimension (score = 1 - walk_km / 1.0km).
    # Default 30 min → walk_km=2.5 → score=0.0 (inactive/no preference)
    # 3 min → walk_km=0.25 → score=0.75 (wants very close MRT)
    max_mrt = profile.get("max_mrt_mins", 30)
    walk_km = (max_mrt / 60.0) * 5.0
    vec[4] = max(0.0, round(1.0 - walk_km / _AMENITY_MAX_KM["mrt"], 4))

    # 5–9 — amenity dims from mustAmenities (excludes MRT, handled above)
    # 1.0 = buyer must have this amenity nearby
    # 0.5 = neutral (no preference — not 0.0 so the flat's amenity richness
    #        on these dims doesn’t inflate the cosine denominator unfairly)
    must_have: list[str] = profile.get("must_have", [])
    must_set = set(must_have)
    for i, amenity in enumerate(AMENITY_DIMS):
        vec[5 + i] = 1.0 if amenity in must_set else 0.5

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


# ── Helper: proximity score from dist_km ────────────────────────────────────

def _proximity_score(amenity_key: str, amenities: dict) -> float:
    """
    Convert nearest-amenity distance to a 0–1 proximity score.

    geo/distances.nearest_amenities() only returns the *nearest* amenity,
    not a count. We approximate the flat's amenity richness via:
        score = 1 - (dist_km / max_km)   clipped to [0, 1]

    A flat at dist=0 scores 1.0; at dist≥max_km scores 0.0.
    """
    entry = amenities.get(amenity_key, {})
    dist_km = entry.get("dist_km")
    if dist_km is None:
        return 0.0
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
    4  nearby_mrt      — proximity score (1 - dist/1km)
    5  nearby_hawker   — proximity score (1 - dist/1km)
    6  nearby_mall     — proximity score (1 - dist/1.5km)
    7  nearby_park     — proximity score (1 - dist/1.5km)
    8  nearby_school   — proximity score (1 - dist/1km)
    9  nearby_hospital — proximity score (1 - dist/2km)
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

    # 4 — nearby_mrt (matches buyer_vector dim 4: mrt_walk_pref)
    vec[4] = _proximity_score("mrt", amenities)

    # 5–9 — other amenity proximity scores
    for i, amenity in enumerate(AMENITY_DIMS):
        vec[5 + i] = _proximity_score(amenity, amenities)

    return vec
