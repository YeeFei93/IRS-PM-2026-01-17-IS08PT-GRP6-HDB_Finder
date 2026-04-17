"""
recommendation-scorer-service/cosine_scorer.py
========================
Weighted Cosine Similarity scoring for Content-Based filtering.

Computes:  score_cb = cosine_similarity(W ⊙ buyer_vec, W ⊙ flat_vec)

The weight vector W amplifies dimensions the buyer actively configured
(weight 1.0) and dampens dimensions left at defaults (weight 0.25),
so the similarity is driven by what the buyer cares about most while
still allowing serendipitous matches on unconfigured dimensions.

Both buyer_vector and flat_vector are 7-dim (see vectorizer.py).
"""

from __future__ import annotations

import math

from weights import (
    CRITERION_FLOOR,
    CRITERION_MRT,
    CRITERION_HAWKER,
    CRITERION_MALL,
    CRITERION_PARK,
    CRITERION_SCHOOL,
    CRITERION_HOSPITAL,
)

# ── Dimension → criterion mapping (7-dim vectors) ────────────────────────────
# Each vector dimension maps to its own criterion so that only the amenities
# the buyer explicitly marked as must-have receive full weight (1.0).
# "budget", "flat", "region", and "lease" have no vector dimensions — they are
# pre-filters or separate signals.
_DIM_CRITERION: list[str] = [
    CRITERION_FLOOR,    # 0  floor_pref / floor
    CRITERION_MRT,      # 1  has_mrt / nearby_mrt
    CRITERION_HAWKER,   # 2  has_hawker / nearby_hawker
    CRITERION_MALL,     # 3  has_mall / nearby_mall
    CRITERION_PARK,     # 4  has_park / nearby_park
    CRITERION_SCHOOL,   # 5  has_school / nearby_school
    CRITERION_HOSPITAL, # 6  has_hospital / nearby_hospital
]

ACTIVE_WEIGHT   = 1.0
INACTIVE_WEIGHT = 0.25

# ── Criteria coverage scaling ────────────────────────────────────────────────
# Cosine similarity is scale-invariant: when ALL dimensions share the same
# weight the score is identical to the unweighted version, clustering high
# (85-95) for any positive vectors.  The coverage factor compensates by
# scaling the final score down when few vector dimensions are actively
# configured — reflecting lower confidence in the match signal.
#
#   coverage = COVERAGE_FLOOR + (1 - COVERAGE_FLOOR) * (n_active_dims / 7)
#
# With 0 active dims  → factor 0.40 (score capped ~40/100)
# With 7 active dims  → factor 1.00 (no change)
COVERAGE_FLOOR = 0.40   # minimum coverage multiplier (no active dims)


def _coverage_factor(active_criteria: list[str]) -> float:
    """Return a 0.4–1.0 multiplier based on how many vector dims are active.

    Cosine similarity is scale-invariant: uniform weights produce the same
    score regardless of their magnitude.  When the buyer expresses few
    preferences the match signal is weak, so we scale the score down to
    reflect that low confidence.
    """
    active_set = set(active_criteria)
    n_active = sum(1 for c in _DIM_CRITERION if c in active_set)
    n_total = len(_DIM_CRITERION)
    return COVERAGE_FLOOR + (1.0 - COVERAGE_FLOOR) * (n_active / n_total)


def _build_weight_vector(active_criteria: list[str]) -> list[float]:
    """Build 7-dim weight vector from the list of active criterion IDs.

    Parameters
    ----------
    active_criteria : list[str]
        Criterion IDs that the buyer actively configured, e.g.
        ``["budget", "flat", "amenity"]``.  Only the IDs that map to vector
        dimensions are used (``budget``, ``region``, and ``lease`` are
        ignored here since they have no corresponding vector dimensions).

    Returns
    -------
    list[float]
        Length-7 weight vector with 1.0 for active dims, 0.25 for inactive.
    """
    active_set = set(active_criteria)
    return [
        ACTIVE_WEIGHT if crit in active_set else INACTIVE_WEIGHT
        for crit in _DIM_CRITERION
    ]


def _align_buyer_vector(buyer_vec: list[float]) -> list[float]:
    """Return buyer vector unchanged — both buyer and flat vectors are 7-dim."""
    return list(buyer_vec)


def _weighted_cosine(a: list[float], b: list[float],
                     w: list[float]) -> float:
    """Compute cosine similarity of weight-scaled vectors W⊙a and W⊙b.

    Returns a score in [0, 1].  If either weighted vector has zero
    magnitude the similarity is 0.0 (no meaningful comparison).
    """
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for ai, bi, wi in zip(a, b, w):
        wa = wi * ai
        wb = wi * bi
        dot += wa * wb
        norm_a += wa * wa
        norm_b += wb * wb

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


# ── Public API ───────────────────────────────────────────────────────────────

def score_cb(buyer_vec: list[float],
             flat_vec: list[float],
             active_criteria: list[str]) -> float:
    """Compute Content-Based cosine similarity score between buyer and flat.

    Parameters
    ----------
    buyer_vec : list[float]
        7-dim buyer preference vector from ``vectorizer.buyer_vector()``.
    flat_vec : list[float]
        7-dim eligible flat vector from ``vectorizer.flat_vector()``.
    active_criteria : list[str]
        Criterion IDs the buyer actively configured (from
        ``app.detect_active_criteria()``).

    Returns
    -------
    float
        Similarity score in [0.0, 1.0].
    """
    aligned = _align_buyer_vector(buyer_vec)
    w = _build_weight_vector(active_criteria)
    raw = _weighted_cosine(aligned, flat_vec, w)
    return round(raw * _coverage_factor(active_criteria), 4)


# ── Dimension labels for explainability ──────────────────────────────────────
_DIM_LABELS: list[str] = [
    "floor", "mrt", "hawker", "mall", "park", "school", "hospital",
]

_DIM_ICONS: list[str] = [
    "🏢", "🚇", "🍜", "🛍️", "🌳", "🏫", "🏥",
]


def score_cb_breakdown(buyer_vec: list[float],
                       flat_vec: list[float],
                       active_criteria: list[str]) -> list[dict]:
    """Return per-dimension contribution breakdown for explainability.

    Each entry contains the dimension label, buyer/flat values,
    whether this dimension is priority (active), and its weighted
    contribution as a fraction of the total cosine similarity.
    """
    aligned = _align_buyer_vector(buyer_vec)
    w = _build_weight_vector(active_criteria)
    active_set = set(active_criteria)

    # Compute weighted dot products per dimension
    dot_total = 0.0
    norm_a = 0.0
    norm_b = 0.0
    dim_dots = []
    for ai, bi, wi in zip(aligned, flat_vec, w):
        wa = wi * ai
        wb = wi * bi
        d = wa * wb
        dim_dots.append(d)
        dot_total += d
        norm_a += wa * wa
        norm_b += wb * wb

    import math as _math
    denom = (_math.sqrt(norm_a) * _math.sqrt(norm_b)) if (norm_a > 0 and norm_b > 0) else 0.0
    coverage = _coverage_factor(active_criteria)

    breakdown = []
    for i, (label, icon) in enumerate(zip(_DIM_LABELS, _DIM_ICONS)):
        crit = _DIM_CRITERION[i]
        is_priority = crit in active_set
        # Contribution: (dim_dot / denominator) × coverage gives the fraction of final score
        contrib = round(dim_dots[i] / denom * coverage, 4) if denom > 0 else 0.0
        breakdown.append({
            "dim":      label,
            "icon":     icon,
            "buyer":    round(aligned[i], 4),
            "flat":     round(flat_vec[i], 4),
            "weight":   round(w[i], 2),
            "priority": is_priority,
            "contrib":  contrib,
        })

    return breakdown
