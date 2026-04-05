"""
recommendation_scorer_service/vectorizer.py
=====================
Converts raw user form inputs and flat/town data into normalised
numeric vectors for Content-Based cosine similarity scoring.

Buyer Preference Vector (11-dim):
  [flat_type, region, floor_pref, flat_area, remaining_lease,
   has_mrt, has_hawker, has_mall, has_park, has_school, has_hospital]

Eligible Flat Vector (10-dim):
  [flat_type, region, floor, flat_area, remaining_lease,
   nearby_mrt, nearby_hawker, nearby_mall, nearby_park, nearby_school]

All values normalised to 0–1.

Reference: detectActive() and rawForCriterion() in frontend engine.js
"""

from __future__ import annotations

# ── Flat-type ordinal encoding ──────────────────────────────────────
FLAT_TYPE_ORD: dict[str, float] = {
    "2 ROOM":    0.2,
    "3 ROOM":    0.4,
    "4 ROOM":    0.6,
    "5 ROOM":    0.8,
    "EXECUTIVE": 1.0,
}

# ── Floor preference ordinal encoding ───────────────────────────────
FLOOR_PREF_ORD: dict[str, float] = {
    "low":  0.33,
    "mid":  0.66,
    "high": 1.0,
    "any":  0.5,
}

# ── Expected area midpoints by flat type (sqm) ─────────────────────
# Used to derive a normalised area preference from flat type.
_AREA_MID: dict[str, float] = {
    "2 ROOM":    40.5,   # (36+45)/2
    "3 ROOM":    67.5,   # (60+75)/2
    "4 ROOM":    95.0,   # (85+105)/2
    "5 ROOM":    122.5,  # (110+135)/2
    "EXECUTIVE": 147.5,  # (130+165)/2
}
_AREA_MAX = 165.0  # largest expected area (EXECUTIVE upper bound)

# ── Amenity dimension order (must stay stable) ──────────────────────
AMENITY_DIMS: list[str] = ["mrt", "hawker", "mall", "park", "school", "hospital"]

# ── Flat vector amenity dims (10-dim vector excludes hospital to keep at 10) ──
# Order matches Eligible Flat Vector definition in plan.
FLAT_AMENITY_DIMS: list[str] = ["mrt", "hawker", "mall", "park", "school"]

# ── Max distances used for proximity normalisation (km) ─────────────
# Beyond these distances the amenity scores to 0.
_AMENITY_MAX_KM: dict[str, float] = {
    "mrt":      2.0,
    "hawker":   3.0,
    "mall":     3.0,
    "park":     3.0,
    "school":   3.0,
    "hospital": 5.0,
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
    "flat_type", "region", "floor_pref", "flat_area", "remaining_lease",
    "has_mrt", "has_hawker", "has_mall", "has_park", "has_school", "has_hospital",
]

FLAT_VEC_LABELS: list[str] = [
    "flat_type", "region", "floor", "flat_area", "remaining_lease",
    "nearby_mrt", "nearby_hawker", "nearby_mall", "nearby_park", "nearby_school",
]


def buyer_vector(profile: dict, budget: float = 0.0) -> list[float]:
    """Convert a BuyerProfile dict into an 11-dim list of floats in [0, 1].

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
        Length 11, all values in [0.0, 1.0].
    """
    vec: list[float] = [0.0] * 11

    # 0 — flat_type
    ftype = profile.get("ftype", "any")
    vec[0] = FLAT_TYPE_ORD.get(ftype, 0.5)  # "any" → 0.5 (neutral midpoint)

    # 1 — region (ordinal, same scale as flat_vector dim 1)
    # Encodes the buyer's preferred region(s) using the same ordinal values used
    # in flat_vector so cosine can meaningfully compare the two dimensions.
    # If the buyer selected multiple regions, take the mean ordinal.
    # If no preference, use 0.6 (neutral midpoint of the 5 ordinal values).
    _REGION_ORD_B = {"north": 0.2, "east": 0.4, "west": 0.6, "south": 0.8, "central": 1.0}
    regions = profile.get("regions", [])
    if regions:
        ordinals = [_REGION_ORD_B.get(r.lower(), 0.6) for r in regions]
        vec[1] = round(sum(ordinals) / len(ordinals), 4)
    else:
        vec[1] = 0.6  # neutral: no stated preference, mid-scale

    # 2 — floor_pref
    floor = profile.get("floor", profile.get("floor_pref", "any"))
    vec[2] = FLOOR_PREF_ORD.get(floor, 0.5)

    # 3 — flat_area (derived from ftype: expected_area_midpoint / 165)
    vec[3] = _AREA_MID.get(ftype, _AREA_MID["4 ROOM"]) / _AREA_MAX

    # 4 — remaining_lease (min_lease / 99)
    min_lease = profile.get("min_lease", 60)
    vec[4] = min(max(min_lease / 99.0, 0.0), 1.0)

    # 5–10 — amenity binary flags from mustAmenities
    must_have: list[str] = profile.get("must_have", [])
    must_set = set(must_have)
    for i, amenity in enumerate(AMENITY_DIMS):
        vec[5 + i] = 1.0 if amenity in must_set else 0.0

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
    max_km = _AMENITY_MAX_KM.get(amenity_key, 3.0)
    return max(0.0, round(1.0 - dist_km / max_km, 4))


# ── Main function ────────────────────────────────────────────────────────────

def flat_vector(town: str, price_data: dict, amenities: dict) -> list[float]:
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
    0  flat_type       — ordinal: 2RM=0.2 … EXEC=1.0
    1  region          — ordinal: north=0.2, east=0.4, west=0.6, south=0.8, central=1.0
    2  floor           — midpoint of avg storey_range / 50
    3  flat_area       — avg floor_area_sqm / 165
    4  remaining_lease — avg remaining lease years / 99
    5  nearby_mrt      — proximity score (1 - dist/2km)
    6  nearby_hawker   — proximity score (1 - dist/3km)
    7  nearby_mall     — proximity score (1 - dist/3km)
    8  nearby_park     — proximity score (1 - dist/3km)
    9  nearby_school   — proximity score (1 - dist/3km)
    """
    vec: list[float] = [0.0] * 10

    # 0 — flat_type
    ftype = price_data.get("ftype", "4 ROOM")
    vec[0] = FLAT_TYPE_ORD.get(ftype, 0.5)

    # 1 — region (ordinal: encode 5 regions as evenly-spaced 0.2–1.0)
    _REGION_ORD = {
        "north":   0.2,
        "east":    0.4,
        "west":    0.6,
        "south":   0.8,
        "central": 1.0,
    }
    region = _TOWN_TO_REGION.get(town.upper(), "")
    vec[1] = _REGION_ORD.get(region, 0.5)  # 0.5 if town not mapped

    # 2 — floor (midpoint of avg storey_range / 50)
    # price_data may carry 'storey_range' (most common range string) or
    # 'avg_storey_range' (numeric average from queries.py).
    avg_storey = price_data.get("avg_storey", None)
    if avg_storey is None:
        storey_range_str = price_data.get("storey_range", "")
        avg_storey = _storey_midpoint(storey_range_str)
    vec[2] = min(max(float(avg_storey) / _STOREY_MAX, 0.0), 1.0)

    # 3 — flat_area (avg_area / 165)
    avg_area = price_data.get("avg_area", 0)
    vec[3] = min(max(float(avg_area) / _AREA_MAX, 0.0), 1.0)

    # 4 — remaining_lease
    lease_years = _parse_lease_years(price_data.get("avg_lease_years", 0))
    vec[4] = min(max(lease_years / 99.0, 0.0), 1.0)

    # 5–9 — amenity proximity scores (hospital excluded to keep vector at 10-dim)
    for i, amenity in enumerate(FLAT_AMENITY_DIMS):
        vec[5 + i] = _proximity_score(amenity, amenities)

    return vec
