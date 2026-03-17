"""
scoring/serendipity_score.py
============================
Serendipity score — always 20% of total (20 pts).

Purpose
-------
When a buyer sets very tight preferences, the MCDM filter may return
fewer than 10 estates. Serendipity scores estates on the criteria
the buyer did NOT actively set, surfacing genuinely good options
outside the buyer's stated preferences.

Design
------
- Serendipity evaluates the INACTIVE criteria set
- If all 6 criteria are active, it falls back to evaluating all 6
  uniformly (every estate still gets a meaningful serendipity score)
- The score rewards estates that are objectively strong on dimensions
  the buyer didn't think to ask about

Inactive criteria → serendipity sub-scores:
  budget   → how far below budget the median price is (value for money)
  flat     → area generosity (larger than typical for the flat type)
  region   → geographic diversity (non-preferred regions score 0.5 neutral)
  lease    → lease length above 70-year baseline
  mrt      → MRT walk time (independent of buyer's stated threshold)
  amenity  → average proximity across ALL amenity types (not just must-haves)
"""

from scoring import (
    budget_score,
    amenity_score,
    transport_score,
    region_score,
    flat_score,
)
from scoring.weights import (
    SERENDIPITY_TOTAL,
    ALL_CRITERIA,
    CRITERION_BUDGET,
    CRITERION_FLAT,
    CRITERION_REGION,
    CRITERION_LEASE,
    CRITERION_MRT,
    CRITERION_AMENITY,
)

# Baseline lease used when buyer hasn't set a minimum (default 60 yrs)
_LEASE_BASELINE = 70   # serendipity rewards estates above this


def _lease_serendipity(price_data: dict) -> float:
    """Reward generously long leases as a serendipity signal."""
    avg_lease = price_data.get("avg_lease_years", 60)
    if avg_lease >= 90:  return 1.0
    if avg_lease >= 80:  return 0.85
    if avg_lease >= _LEASE_BASELINE: return 0.65
    if avg_lease >= 60:  return 0.40
    return 0.20


def raw(
    inactive_criteria: list,
    price_data: dict,
    amenities: dict,
    budget: float,
    regions: list,
    profile: dict,
) -> float:
    """
    Returns 0.0–1.0 serendipity score based on inactive criteria.

    inactive_criteria: list of criterion IDs not active in MCDM
    """
    criteria_to_score = inactive_criteria if inactive_criteria else ALL_CRITERIA

    sub_scores = {}

    for crit in criteria_to_score:
        if crit == CRITERION_BUDGET:
            sub_scores[crit] = budget_score.raw(price_data, budget)

        elif crit == CRITERION_FLAT:
            sub_scores[crit] = flat_score.area_raw(price_data)

        elif crit == CRITERION_REGION:
            # Neutral 0.5 for all towns — serendipity doesn't penalise
            # for being outside preferred region, but rewards central
            # well-connected towns slightly
            sub_scores[crit] = region_score.raw(
                price_data["town"], regions
            ) if regions else 0.5

        elif crit == CRITERION_LEASE:
            sub_scores[crit] = _lease_serendipity(price_data)

        elif crit == CRITERION_MRT:
            sub_scores[crit] = transport_score.raw(amenities)

        elif crit == CRITERION_AMENITY:
            # Score only selected must-have amenities (align with front-end panel).
            selected = profile.get("must_have", []) or []
            sub_scores[crit] = amenity_score.raw(amenities, must_have=selected)

    if not sub_scores:
        return 0.0

    return sum(sub_scores.values()) / len(sub_scores)


def compute(
    inactive_criteria: list,
    price_data: dict,
    amenities: dict,
    budget: float,
    regions: list,
    profile: dict,
) -> dict:
    """
    Returns serendipity breakdown:
    {
        "raw":        float,          # 0.0–1.0
        "pts":        float,          # scaled to SERENDIPITY_TOTAL (20)
        "criteria_scored": [str],     # which criteria were used
        "sub_scores": {str: float},   # per-criterion raw scores
    }
    """
    criteria_to_score = inactive_criteria if inactive_criteria else ALL_CRITERIA
    sub = {}

    for crit in criteria_to_score:
        if crit == CRITERION_BUDGET:
            sub[crit] = budget_score.raw(price_data, budget)
        elif crit == CRITERION_FLAT:
            sub[crit] = flat_score.area_raw(price_data)
        elif crit == CRITERION_REGION:
            sub[crit] = region_score.raw(price_data["town"], regions) if regions else 0.5
        elif crit == CRITERION_LEASE:
            sub[crit] = _lease_serendipity(price_data)
        elif crit == CRITERION_MRT:
            sub[crit] = transport_score.raw(amenities)
        elif crit == CRITERION_AMENITY:
            selected = profile.get("must_have", []) or []
            sub[crit] = amenity_score.raw(amenities, must_have=selected)

    avg_raw = sum(sub.values()) / len(sub) if sub else 0.0
    pts     = round(avg_raw * SERENDIPITY_TOTAL, 2)

    return {
        "raw":             round(avg_raw, 3),
        "pts":             pts,
        "criteria_scored": list(sub.keys()),
        "sub_scores":      {k: round(v, 3) for k, v in sub.items()},
    }
