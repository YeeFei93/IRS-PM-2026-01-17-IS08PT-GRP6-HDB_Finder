"""
recommendation_scorer_service/amenity_score.py
========================
Proximity to amenities — returns raw score 0.0–1.0.

Threshold-aware scoring:
  Each amenity type has a panel-linked threshold distance.
  Scores reflect actual walk_mins from nearest_amenities().
  Must-have amenities that exceed their threshold are penalised.

Thresholds (matching front-end panel labels):
  MRT      ≤ 500m  (~6 min walk)
  Hawker   ≤ 1km   (~15 min walk)
  Pri Sch  ≤ 1km   (~15 min walk)
  Park     ≤ 1km   (~15 min walk)
  Mall     ≤ 1.5km (~22 min walk)
  Hospital ≤ 3km   (~45 min walk, or short drive)
"""

ALL_AMENITY_KEYS = ["mrt", "hawker", "school", "park", "mall", "hospital"]

# Walk-time scoring curve (minutes → raw score 0.0–1.0)
_WALK_CURVE = [(6, 1.00), (10, 0.85), (15, 0.65), (22, 0.45), (30, 0.25), (45, 0.10)]


def _walk_fraction(walk_mins: int) -> float:
    for threshold, frac in _WALK_CURVE:
        if walk_mins <= threshold:
            return frac
    return 0.0


def raw(amenities: dict, must_have: list) -> float:
    """
    Returns 0.0–1.0 amenity score.
    Scores selected must-have amenities only.
    If no amenity priority is selected, returns 0.0 (no amenity contribution).
    Must-have amenities that exceed their threshold are penalised (×0.3).
    """
    keys = must_have if must_have else []
    if not keys:
        return 0.0

    total = 0.0
    for k in keys:
        a = amenities.get(k, {})
        walk = a.get("walk_mins", 999)
        base = _walk_fraction(walk)
        # Penalise must-haves that don't meet threshold
        if must_have and k in must_have and not a.get("within_threshold", True):
            base *= 0.3
        total += base

    return total / len(keys)
