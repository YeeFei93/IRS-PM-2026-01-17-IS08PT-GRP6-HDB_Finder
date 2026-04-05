"""
recommendation_scorer_service/aggregator.py
=====================
MCDM + Serendipity scoring aggregator.

Formula
-------
Total (100 pts) = MCDM (80 pts) + Serendipity (20 pts)

Step 1 — Detect active criteria
  For each of the 6 panel criteria, check whether the buyer made
  a meaningful choice vs leaving it at the default value.

Step 2 — MCDM weight allocation
  active_weight = MCDM_TOTAL / max(len(active_criteria), 1)
  Each active criterion receives equal weight.
  If NO criteria are active → all 6 treated as active (80/6 each).

Step 3 — MCDM score
  For each active criterion:
    component_pts = raw_score (0.0–1.0) × active_weight

Step 4 — Serendipity score
  Evaluated on INACTIVE criteria (or all if all active).
  Always contributes SERENDIPITY_TOTAL (20 pts) max.

Step 5 — Total
  Sum of all MCDM component pts + serendipity pts.

This module is the ONLY place that calls across component modules.
To change scoring behaviour: edit the relevant component file.
To change weights/allocation: edit recommendation_scorer_service/weights.py.
"""

from recommendation_scorer_service.weights import (
    MCDM_TOTAL,
    ALL_CRITERIA,
    CRITERION_BUDGET,
    CRITERION_FLAT,
    CRITERION_REGION,
    CRITERION_LEASE,
    CRITERION_MRT,
    CRITERION_AMENITY,
    DEFAULTS,
)
from recommendation_scorer_service import (
    budget_score,
    amenity_score,
    transport_score,
    region_score,
    flat_score,
)
from recommendation_scorer_service.MCDM.serendipity_score import compute as compute_serendipity


# ── Step 1: Detect which criteria the buyer actively set ─────────────────────

def detect_active_criteria(profile: dict, budget: float,
                            must_have: list, regions: list) -> list:
    """
    Returns list of criterion IDs the buyer actively configured.
    A criterion is ACTIVE when its value differs meaningfully from default.
    """
    active = []

    # Budget: active if buyer has any purchasing power
    if budget > 0:
        active.append(CRITERION_BUDGET)

    # Flat type: active if buyer chose something specific (not "any")
    ftype = profile.get("ftype", DEFAULTS[CRITERION_FLAT])
    if ftype != DEFAULTS[CRITERION_FLAT]:
        active.append(CRITERION_FLAT)

    # Region: active if buyer selected ≥1 region
    if regions and len(regions) > 0:
        active.append(CRITERION_REGION)

    # Lease: active if buyer raised the minimum above baseline (60 yrs)
    min_lease = profile.get("min_lease", DEFAULTS[CRITERION_LEASE])
    if min_lease > DEFAULTS[CRITERION_LEASE]:
        active.append(CRITERION_LEASE)

    # MRT: active if buyer tightened the walk time below ceiling (30 min)
    max_mrt = profile.get("max_mrt_mins", DEFAULTS[CRITERION_MRT])
    if max_mrt < DEFAULTS[CRITERION_MRT]:
        active.append(CRITERION_MRT)

    # Amenity: active if buyer selected ≥1 must-have
    if must_have and len(must_have) > 0:
        active.append(CRITERION_AMENITY)

    return active


# ── Step 2–3: MCDM scoring ────────────────────────────────────────────────────

def compute_mcdm(active_criteria: list, price_data: dict, amenities: dict,
                 profile: dict, budget: float,
                 must_have: list, regions: list) -> dict:
    """
    Returns MCDM breakdown:
    {
        "active_criteria": [str],
        "weight_per_criterion": float,   # pts each active criterion gets
        "components": {
            criterion_id: {
                "raw":  float,    # 0.0–1.0 component score
                "pts":  float,    # raw × weight
                "weight": float,
            }
        },
        "total_pts": float,   # sum of all component pts (≤ MCDM_TOTAL)
    }
    """
    criteria = active_criteria if active_criteria else ALL_CRITERIA
    weight   = MCDM_TOTAL / len(criteria)

    components = {}
    total_pts  = 0.0

    for crit in criteria:
        r = _raw_for_criterion(
            crit, price_data, amenities, profile, budget, must_have, regions
        )
        pts = round(r * weight, 2)
        total_pts += pts
        components[crit] = {
            "raw":    round(r, 3),
            "pts":    pts,
            "weight": round(weight, 2),
        }

    return {
        "active_criteria":       criteria,
        "weight_per_criterion":  round(weight, 2),
        "components":            components,
        "total_pts":             round(total_pts, 2),
    }


def _raw_for_criterion(crit: str, price_data: dict, amenities: dict,
                        profile: dict, budget: float,
                        must_have: list, regions: list) -> float:
    """Dispatch to the correct component scorer for each criterion."""
    if crit == CRITERION_BUDGET:
        return budget_score.raw(price_data, budget)

    elif crit == CRITERION_FLAT:
        return flat_score.area_raw(price_data)

    elif crit == CRITERION_REGION:
        return region_score.raw(price_data["town"], regions)

    elif crit == CRITERION_LEASE:
        buyer_age = profile.get("age", 35)
        min_lease = profile.get("min_lease", 60)
        return flat_score.lease_raw(price_data, min_lease, buyer_age)

    elif crit == CRITERION_MRT:
        return transport_score.raw(amenities)

    elif crit == CRITERION_AMENITY:
        return amenity_score.raw(amenities, must_have)

    return 0.0


# ── Public entry point ────────────────────────────────────────────────────────

def compute_score(price_data: dict, amenities: dict, profile: dict,
                  budget: float, must_have: list, regions: list) -> dict:
    """
    Full MCDM + Serendipity score for one estate.

    Returns:
    {
        "total":       float,    # 0–100 final score
        "mcdm":        dict,     # MCDM breakdown (see compute_mcdm)
        "serendipity": dict,     # serendipity breakdown
        "active_criteria": [str],
        "inactive_criteria": [str],
        "weight_per_criterion": float,
        "label": str,            # human-readable score tier
    }
    """
    # Step 1: detect active criteria
    active   = detect_active_criteria(profile, budget, must_have, regions)
    inactive = [c for c in ALL_CRITERIA if c not in active]

    # Step 2–3: MCDM
    mcdm = compute_mcdm(active, price_data, amenities, profile,
                         budget, must_have, regions)

    # Step 4: Serendipity
    seren = compute_serendipity(
        inactive_criteria = inactive,
        price_data        = price_data,
        amenities         = amenities,
        budget            = budget,
        regions           = regions,
        profile           = profile,
    )

    # Step 5: Total
    total = round(mcdm["total_pts"] + seren["pts"], 1)

    return {
        "total":                 total,
        "mcdm":                  mcdm,
        "serendipity":           seren,
        "active_criteria":       active,
        "inactive_criteria":     inactive,
        "weight_per_criterion":  mcdm["weight_per_criterion"],
        "label":                 _score_label(total),
    }


def _score_label(total: float) -> str:
    if   total >= 85: return "Excellent Match"
    elif total >= 70: return "Strong Match"
    elif total >= 55: return "Good Match"
    elif total >= 40: return "Fair Match"
    else:             return "Exploratory"
