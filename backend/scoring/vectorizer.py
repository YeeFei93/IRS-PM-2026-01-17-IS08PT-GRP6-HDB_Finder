"""
scoring/vectorizer.py
=====================
Converts raw user form inputs and flat/town data into normalised
numeric vectors for Content-Based cosine similarity scoring.

Buyer Preference Vector (11-dim):
  [flat_type, region, floor_pref, flat_area, remaining_lease,
   has_mrt, has_hawker, has_mall, has_park, has_school, has_hospital]

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

# ── Vector dimension labels (for explainability) ────────────────────
BUYER_VEC_LABELS: list[str] = [
    "flat_type", "region", "floor_pref", "flat_area", "remaining_lease",
    "has_mrt", "has_hawker", "has_mall", "has_park", "has_school", "has_hospital",
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

    # 1 — region (1.0 if user selected regions, 0.0 if no preference)
    regions = profile.get("regions", [])
    vec[1] = 1.0 if regions else 0.0

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
